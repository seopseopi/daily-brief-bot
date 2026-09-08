"""커뮤니티 펄스 섹션 — 디시(5개 갤러리) + 레딧(2개 서브) 화제글."""

from sources import _community, _llm
from sources._shared import fail, tr

DC_GALLERIES = [
    ("thesingularity", "특이점이 온다 갤"),
    ("claude", "클로드 갤"),
    ("chatgpt", "챗지피티 갤"),
    ("chatgptpro", "GPT프로 갤"),
    ("aiinformation", "AI 정보 갤"),
]
REDDIT_SUBS = [("LocalLLaMA", "r/LocalLLaMA"), ("ClaudeAI", "r/ClaudeAI")]
NO_EXCERPT_NOTE = "(본문 요약 없음 — 더보기 참고)"


def _dc_excerpt_raw(post):
    """선택된 디시 글만 상세페이지를 한 번 더 열어 발췌를 가져온다. 실패 시 빈 문자열."""
    try:
        return _community.fetch_dc_post_excerpt(post["url"])
    except Exception:
        return ""


def get_community():
    """조회수/댓글수 상위, 최소한의 혐오·자극 필터.

    디시는 선택된 글의 상세페이지에서 JSON-LD articleBody(검색용 요약,
    이미 짧게 잘려있음)를 발췌로 쓴다. 레딧은 추가 요청 없이 목록 RSS의
    content 필드에서 자체 글 본문만 최대한 걸러낸다 — 레딧이 이미 IP
    차단이 잦아서 요청을 늘리지 않으려는 의도.

    최종 선정된 글들은 한 번의 LLM 호출로 "디깅 요약"을 받는다 — 잘린
    발췌를 자연스럽게 다듬고, 발췌가 없으면 제목만으로 짧게 정리한다.
    LLM이 없거나 실패하면 원본 발췌(또는 "본문 요약 없음")를 그대로 쓴다.
    갤러리/서브레딧 하나가 막혀도 나머지는 정상 출력된다.
    """
    dc_hits = []
    for gallery_id, label in DC_GALLERIES:
        try:
            post = _community.fetch_dc_top_post(gallery_id)
        except Exception:
            post = None
        if post:
            dc_hits.append((label, post))
    dc_hits.sort(key=lambda x: -x[1]["views"])

    reddit_hits = []
    for sub_id, label in REDDIT_SUBS:
        try:
            post = _community.fetch_reddit_top_post(sub_id)
        except Exception:
            post = None
        if post:
            reddit_hits.append((label, post))

    # entries의 각 원소: [label, stat, title, fallback_detail, url, raw_excerpt(LLM 입력용)]
    entries = []
    for label, post in dc_hits[:3]:
        stat = f"조회 {post['views']:,} · 댓글 {post['replies']}"
        raw = _dc_excerpt_raw(post)
        entries.append([label, stat, post["title"], raw or NO_EXCERPT_NOTE, post["url"], raw])

    for label, post in reddit_hits:
        raw = post.get("excerpt") or ""
        fallback = tr(raw, cap=140) if raw else NO_EXCERPT_NOTE
        entries.append([label, "레딧 오늘의 인기글", tr(post["title"], cap=100), fallback, post["url"], raw])

    for label, post in dc_hits[3:]:
        if len(entries) >= 5:
            break
        stat = f"조회 {post['views']:,} · 댓글 {post['replies']}"
        raw = _dc_excerpt_raw(post)
        entries.append([label, stat, post["title"], raw or NO_EXCERPT_NOTE, post["url"], raw])

    if not entries:
        fail("커뮤니티 전체")
        return [("(커뮤니티 조회 실패)", "", "잠시 후 다시 시도해주세요", "", None)]

    try:
        items_for_llm = [{"label": e[0], "title": e[2], "excerpt": e[5]} for e in entries]
        digests = _llm.explain_community(items_for_llm)
        for e, d in zip(entries, digests):
            e[3] = d
    except Exception as e:
        print(f"[경고] 커뮤니티 디깅(LLM) 실패: {type(e).__name__}: {e}")
        fail("커뮤니티 디깅(LLM)")
        # 실패해도 entries[i][3]엔 이미 원본 발췌/요약없음 폴백이 들어있음

    return [tuple(e[:5]) for e in entries]
