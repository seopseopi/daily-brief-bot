"""커뮤니티 펄스 — DC/Reddit 반응 신호 + Hacker News 정보 링크.

``get_community()``는 main.py와의 호환성을 위해 여전히 아래 5튜플을
반환한다::

    (표시용 소스·신호 라벨, 게시시각·참여 메타, 제목,
     사실성 한계가 명시된 요약, 원문 URL)

커뮤니티 글의 주장은 검증된 사실로 승격하지 않는다. LLM은 원문 발췌가 있는
항목만 요약하며, 모든 출력에는 ``사실 확인 필요`` 또는 ``원문 미검증``
표시가 붙는다.
"""

import os
import re
from datetime import datetime, timezone

import settings
from sources import _community, _llm
from sources._shared import KST, fail, tr

DC_GALLERIES = [
    ("thesingularity", "특이점이 온다 갤"),
    ("claude", "클로드 갤"),
    ("chatgpt", "챗지피티 갤"),
    ("chatgptpro", "GPT프로 갤"),
    ("aiinformation", "AI 정보 갤"),
]
REDDIT_SUBS = [("LocalLLaMA", "r/LocalLLaMA"), ("ClaudeAI", "r/ClaudeAI")]
DEFAULT_MAX_AGE_HOURS = _community.DEFAULT_MAX_AGE_HOURS
MAX_ITEMS = 5
NO_EXCERPT_NOTE = "제목과 참여 메타만 확인됨 — 원문 내용은 직접 확인해주세요"
REACTION_PREFIX = "⚠️ 커뮤니티 반응 요약(사실 확인 필요) — "
INFO_PREFIX = "⚠️ 링크 소개(원문 미검증) — "
DISPLAY_REDACTIONS = ("시발", "ㅅㅂ", "병신", "지랄", "새끼", "좆", "fuck", "nigger", "retard")


def _dc_excerpt_raw(post):
    """선택된 디시 글만 상세페이지를 한 번 더 열어 발췌를 가져온다. 실패 시 빈 문자열."""
    try:
        return _community.fetch_dc_post_excerpt(post["url"])
    except Exception:
        return ""


def _resolve_max_age_hours(value=None):
    """인자 또는 COMMUNITY_MAX_AGE_HOURS 환경변수에서 freshness를 읽는다."""
    raw = value if value is not None else os.environ.get("COMMUNITY_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_MAX_AGE_HOURS)
    # 잘못된 설정으로 모든 항목이 통과하거나 영구 보관되는 것을 막는다.
    if hours <= 0:
        return float(DEFAULT_MAX_AGE_HOURS)
    return min(hours, 168.0)


def _display_title(post):
    title = post["title"]
    if post["source_kind"] in {"reddit", "hn"}:
        title = tr(title, cap=120)
    return _redact(title)


def _format_stat(post):
    """게시 시각과 소스가 실제 제공한 참여 메타만 표시한다."""
    published_at = post.get("published_at")
    if isinstance(published_at, datetime) and published_at.tzinfo is not None:
        when = published_at.astimezone(KST).strftime("%m/%d %H:%M KST")
        parts = [f"게시 {when}"]
    else:
        # 수집 단계에서 걸러지므로 정상 경로에는 도달하지 않는다.
        parts = ["게시 시각 미확인"]

    if post.get("score") is not None:
        parts.append(f"{post['score']:,}점")
    if post.get("views") is not None:
        parts.append(f"조회 {post['views']:,}")
    if post.get("comments") is not None:
        parts.append(f"댓글 {post['comments']:,}")
    if post["source_kind"] == "reddit" and post.get("score") is None and post.get("comments") is None:
        parts.append("점수·댓글 RSS 미제공")
    return " · ".join(parts)


def _qualified_detail(signal_type, text):
    prefix = INFO_PREFIX if signal_type == "정보 링크" else REACTION_PREFIX
    clean = _redact((text or NO_EXCERPT_NOTE).strip())
    return prefix + clean


def _redact(text):
    clean = str(text or "")
    for word in DISPLAY_REDACTIONS:
        clean = re.sub(re.escape(word), "***", clean, flags=re.I)
    return clean


def _label(source_label, post):
    if post["signal_type"] == "정보 링크":
        return f"🧭 정보 링크 · {source_label}"
    return f"💬 반응 신호 · {source_label}"


def _select_diverse(groups, limit=MAX_ITEMS):
    """가용한 각 플랫폼에서 최소 한 건을 먼저 뽑고 나머지는 라운드로빈."""
    order = ("hn", "reddit", "dc")
    queues = {key: list(groups.get(key, [])) for key in order}
    selected = []
    while len(selected) < limit and any(queues.values()):
        for key in order:
            if queues[key] and len(selected) < limit:
                selected.append(queues[key].pop(0))
    return selected


def _collect(max_age_hours, now):
    """플랫폼별 후보를 모은다. 한 플랫폼 실패가 다른 플랫폼을 막지 않는다."""
    groups = {"dc": [], "reddit": [], "hn": []}

    dc_errors = 0
    for gallery_id, label in DC_GALLERIES:
        try:
            post = _community.fetch_dc_top_post(
                gallery_id, max_age_hours=max_age_hours, now=now,
            )
        except Exception:
            dc_errors += 1
            continue
        if post:
            groups["dc"].append((label, post))
    groups["dc"].sort(key=lambda item: (item[1].get("views") or 0, item[1].get("comments") or 0), reverse=True)
    if dc_errors == len(DC_GALLERIES):
        fail("커뮤니티-DC")

    reddit_errors = 0
    for sub_id, label in REDDIT_SUBS:
        try:
            post = _community.fetch_reddit_top_post(
                sub_id, max_age_hours=max_age_hours, now=now,
            )
        except Exception:
            reddit_errors += 1
            continue
        if post:
            groups["reddit"].append((label, post))
    if reddit_errors == len(REDDIT_SUBS):
        fail("커뮤니티-Reddit")

    try:
        hn_post = _community.fetch_hn_top_post(max_age_hours=max_age_hours, now=now)
    except Exception:
        fail("커뮤니티-Hacker News")
        hn_post = None
    if hn_post:
        groups["hn"].append(("Hacker News", hn_post))

    return groups


def get_community(max_age_hours=None, now=None):
    """최근 글만 골라 플랫폼 다양성을 보장한 5튜플 목록을 반환한다.

    디시는 선택된 글의 상세페이지에서 JSON-LD articleBody(검색용 요약,
    이미 짧게 잘려있음)를 발췌로 쓴다. 레딧은 추가 요청 없이 목록 RSS의
    content 필드에서 자체 글 본문만 최대한 걸러낸다 — 레딧이 이미 IP
    차단이 잦아서 요청을 늘리지 않으려는 의도.

    HN은 공식 Firebase API의 점수·댓글·게시 시각을 쓴다. 기본 freshness는
    24시간이며 COMMUNITY_MAX_AGE_HOURS 또는 함수 인자로 바꿀 수 있다.

    LLM은 발췌가 있는 글만 요약한다. 발췌가 없거나 호출이 실패하면 제목/원문
    발췌 기반 폴백을 사용하며, 어떤 경우에도 게시글 주장을 사실로 단정하지
    않는 한계 문구가 붙는다.
    """
    hours = _resolve_max_age_hours(max_age_hours)
    now = now or datetime.now(timezone.utc)
    groups = _collect(hours, now)
    selected = _select_diverse(groups)

    # entries: [label, stat, title, qualified detail, url, raw excerpt, signal type]
    entries = []
    for source_label, post in selected:
        raw = _dc_excerpt_raw(post) if post["source_kind"] == "dc" else post.get("excerpt", "")
        fallback = raw
        if raw and post["source_kind"] in {"reddit", "hn"}:
            fallback = tr(raw, cap=160)
        entries.append([
            _label(source_label, post),
            _format_stat(post),
            _display_title(post),
            _qualified_detail(post["signal_type"], fallback),
            post["url"],
            raw,
            post["signal_type"],
        ])

    if not entries:
        return [(
            "(최근 커뮤니티 항목 없음)",
            f"최근 {hours:g}시간 기준",
            "신선도 기준을 만족한 글이 없거나 모든 소스 조회에 실패했습니다",
            "⚠️ 데이터 없음 — 커뮤니티 동향을 사실 정보로 대체하지 않습니다",
            None,
        )]

    # 제목밖에 없는 글은 LLM이 빈칸을 추론하게 하지 않는다.
    summarized_indices = [i for i, entry in enumerate(entries) if entry[5].strip()]
    if summarized_indices and settings.USE_LLM_COMMUNITY_SUMMARIES:
        try:
            items_for_llm = [
                {"label": entries[i][0], "title": entries[i][2], "excerpt": entries[i][5]}
                for i in summarized_indices
            ]
            digests = _llm.explain_community(items_for_llm)
            if len(digests) != len(summarized_indices) or not all(isinstance(d, str) and d.strip() for d in digests):
                raise ValueError("커뮤니티 LLM 응답 형식 불일치")
            for idx, digest in zip(summarized_indices, digests):
                entries[idx][3] = _qualified_detail(entries[idx][6], digest[:180])
        except Exception as e:
            print(f"[경고] 커뮤니티 디깅(LLM) 실패: {type(e).__name__}")
            fail("커뮤니티 디깅(LLM)")
            # entries[i][3]에는 이미 한계가 표시된 원문 기반 폴백이 있다.

    return [tuple(e[:5]) for e in entries]
