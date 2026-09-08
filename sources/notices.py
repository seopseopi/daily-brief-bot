"""학사 공지 섹션 — 지난 실행 이후 새로 올라온 공지만."""

import json
import os

from sources import _notices
from sources._shared import fail

SEEN_NOTICES_PATH = "data/seen_notices.json"
NOTICE_SITES = [
    ("cs", "컴공 학사공지", _notices.fetch_cs_notices),
    ("sw", "SW중심대 공지", _notices.fetch_sw_notices),
]


def _load_seen():
    try:
        with open(SEEN_NOTICES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_seen(state):
    os.makedirs(os.path.dirname(SEEN_NOTICES_PATH), exist_ok=True)
    with open(SEEN_NOTICES_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_notices():
    """국민대 컴공/SW 공지 중 지난번 확인 이후 새로 올라온 것만.

    data/seen_notices.json에 마지막으로 본 글 ID를 저장해두고 비교한다.
    이 파일은 main.py 실행 후 워크플로우가 매번 커밋해줘야 상태가
    유지된다 — 안 그러면 매일 "전부 새 글"로 나옴.
    사이트를 처음 추가한 시점(state에 그 키가 아예 없음)에는 기존 글을
    전부 새 글로 쏟아내지 않도록, 그 회차엔 목록만 저장하고 넘어간다.
    """
    state = _load_seen()
    new_state = {}
    new_by_site = []

    for key, label, fetch_fn in NOTICE_SITES:
        try:
            current = fetch_fn()
        except Exception as e:
            print(f"[경고] {label} 조회 실패: {type(e).__name__}: {e}")
            fail(label)
            new_state[key] = state.get(key, [])
            continue

        is_first_run = key not in state
        seen_ids = set(state.get(key, []))
        if not is_first_run:
            new_items = [(title, url) for (post_id, title, url) in current if post_id not in seen_ids]
            if new_items:
                new_by_site.append((label, new_items))

        new_state[key] = [post_id for post_id, _title, _url in current[:60]]

    _save_seen(new_state)
    return new_by_site
