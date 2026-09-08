"""과제 섹션 — 수동 목록(assignments_data.py) + #과제입력 채널 자동 파싱.

채널에 타이핑하면 LLM이 "새 과제 등록"인지 "완료 처리"인지 판단한다.
완료 처리는 메시지 속 과제명을 기존에 쌓아둔 과제들과 느슨하게(부분
일치) 매칭해서 지운다 — 정확한 이름을 안 써도 대략 맞으면 지워진다.
수동 목록(assignments_data.py)은 완료 처리 대상이 아니다 — 그건 파일을
직접 고치는 방식이라 채널 명령으로 지우는 대상이 아니라고 봤다.
"""

import json
import os
from datetime import date, datetime

from sources import _discord, _llm
from sources._shared import KST, fail
from sources.assignments_data import ASSIGNMENTS

DISCORD_ASSIGNMENTS_PATH = "data/discord_assignments.json"


def _load_state():
    try:
        with open(DISCORD_ASSIGNMENTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_message_id": None, "assignments": []}


def _save_state(state):
    os.makedirs(os.path.dirname(DISCORD_ASSIGNMENTS_PATH), exist_ok=True)
    with open(DISCORD_ASSIGNMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _normalize(text):
    return "".join(text.lower().split())


def _remove_matching(assignments, name_hint):
    """name_hint와 부분일치하는 과제를 찾아 지운다.

    여러 개 걸리면 마감이 가장 가까운 것 하나만 지운다(가장 최근에
    화제였을 가능성이 높다고 보고). 하나도 안 걸리면 그대로 둔다.
    """
    hint = _normalize(name_hint)
    if not hint:
        return assignments
    matches = [a for a in assignments if hint in _normalize(a["name"]) or _normalize(a["name"]) in hint]
    if not matches:
        return assignments
    to_remove = min(matches, key=lambda a: a["deadline"])
    return [a for a in assignments if a is not to_remove]


def _fetch_discord_assignments():
    """#과제입력 채널의 새 메시지를 LLM으로 파싱해 과제 목록을 갱신한다.

    data/discord_assignments.json에 마지막으로 읽은 메시지 ID와 지금까지
    쌓인 과제를 저장해둔다 — 매번 채널 전체를 다시 파싱하지 않기 위해서.
    이 파일도 워크플로우가 매번 커밋해줘야 상태가 유지된다.
    봇 토큰/채널 ID가 설정 안 돼 있으면(아직 안 만든 사용자) 조용히
    빈 목록을 반환한다 — 에러 취급 안 함.
    """
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel_id = os.environ.get("ASSIGNMENT_CHANNEL_ID", "")
    if not bot_token or not channel_id:
        return []

    state = _load_state()
    messages = _discord.fetch_channel_messages(channel_id, bot_token, after_id=state.get("last_message_id"))
    messages = [m for m in messages if m.get("content") and not m.get("author", {}).get("bot")]

    if not messages:
        return state["assignments"]

    try:
        today_str = datetime.now(KST).date().isoformat()
        parsed = _llm.parse_assignments([m["content"] for m in messages], today_str)
    except Exception as e:
        print(f"[경고] 과제 메시지 파싱(LLM) 실패: {type(e).__name__}: {e}")
        fail("과제 자동파싱(LLM)")
        # 파싱은 실패해도 last_message_id는 갱신 — 같은 메시지를 계속
        # 재시도하며 실패를 반복하는 것보다, 다음 새 메시지부터 다시
        # 시도하는 편이 낫다고 판단.
        parsed = [None] * len(messages)

    assignments = list(state["assignments"])
    for msg, item in zip(messages, parsed):
        if not item:
            continue
        if item.get("action") == "add":
            assignments.append({
                "message_id": msg["id"],
                "deadline": item["deadline"],
                "name": item["name"],
                "note": item.get("note", ""),
            })
        elif item.get("action") == "complete":
            assignments = _remove_matching(assignments, item.get("name_hint", ""))

    _save_state({"last_message_id": messages[-1]["id"], "assignments": assignments})
    return assignments


def get_assignments():
    """수동 목록 + 채널 자동파싱 결과를 합쳐 D-day로 변환.

    마감이 지난 항목은 두 소스 모두 자동으로 제외되니 지울 필요 없음.
    """
    today = datetime.now(KST).date()
    result = []
    for deadline_str, name, note in ASSIGNMENTS:
        y, m, d = (int(x) for x in deadline_str.split("-"))
        days = (date(y, m, d) - today).days
        if days < 0:
            continue
        result.append((days, name, note))

    try:
        discord_items = _fetch_discord_assignments()
    except Exception as e:
        print(f"[경고] 과제 채널 조회 실패: {type(e).__name__}: {e}")
        fail("과제채널")
        discord_items = []

    for item in discord_items:
        try:
            y, m, d = (int(x) for x in item["deadline"].split("-"))
        except Exception:
            continue
        days = (date(y, m, d) - today).days
        if days < 0:
            continue
        result.append((days, item["name"], item.get("note", "")))

    result.sort(key=lambda x: x[0])
    return result
