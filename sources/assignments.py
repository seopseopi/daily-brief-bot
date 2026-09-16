"""과제 섹션 — 수동 목록(assignments_data.py) + #과제입력 채널 자동 파싱.

명시적 명령은 LLM 없이 먼저 처리한다::

    추가 | YYYY-MM-DD [HH:MM] | 과제명 | 비고
    완료 | 정확한 과제명

나머지 자연어 메시지만 LLM에 맡긴다. 외부 조회나 LLM 파싱이 실패하면
로컬 비공개 캐시와 메시지 커서를 보존해 일시적인 장애가 과제 유실로 이어지지
않게 한다. 새 실행 환경에서는 Discord 채널 기록을 다시 재생한다. 수동
목록(assignments_data.py)은 완료 명령의 대상이 아니다.
"""

import json
import os
import re
from datetime import date, datetime

import settings
from sources import _discord, _llm
from sources._shared import KST, fail
from sources.assignments_data import ASSIGNMENTS

DISCORD_ASSIGNMENTS_PATH = ".private/discord_assignments.json"
_DEADLINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s+([01]\d|2[0-3]):([0-5]\d))?$")


def _load_state():
    try:
        with open(DISCORD_ASSIGNMENTS_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict) or not isinstance(state.get("assignments", []), list):
            raise ValueError("invalid assignment state")
        state.setdefault("last_message_id", None)
        state.setdefault("assignments", [])
        return state
    except Exception:
        return {"last_message_id": None, "assignments": []}


def _save_state(state):
    if settings.env_bool("BRIEF_READ_ONLY") or settings.env_bool("DISCORD_DRY_RUN"):
        return
    state_dir = os.path.dirname(DISCORD_ASSIGNMENTS_PATH)
    if state_dir:
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        os.chmod(state_dir, 0o700)
    tmp_path = DISCORD_ASSIGNMENTS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, DISCORD_ASSIGNMENTS_PATH)


def _normalize(text):
    return "".join(str(text or "").lower().split())


def _remove_matching(assignments, name_hint, exact_only=False):
    """정확히 일치하거나, 유일하게 부분 일치하는 과제만 지운다.

    부분 일치 후보가 여러 개면 어느 과제를 뜻하는지 확정할 수 없으므로
    아무것도 지우지 않는다. 명시적 ``완료 | 이름`` 명령은 exact_only로
    호출해 정확한 이름 외에는 절대 삭제하지 않는다.
    """
    hint = _normalize(name_hint)
    if not hint:
        return assignments

    exact = [i for i, item in enumerate(assignments) if _normalize(item.get("name", "")) == hint]
    if len(exact) == 1:
        return [item for i, item in enumerate(assignments) if i != exact[0]]
    if exact_only or len(exact) > 1:
        return assignments

    partial = [
        i
        for i, item in enumerate(assignments)
        if hint in _normalize(item.get("name", "")) or _normalize(item.get("name", "")) in hint
    ]
    if len(partial) != 1:
        return assignments
    return [item for i, item in enumerate(assignments) if i != partial[0]]


def _parse_explicit_message(content):
    """명시적 추가/완료 명령을 파싱한다.

    명시적 명령이 아니면 ``None``을 반환한다. 명령으로 시작했지만 문법이
    틀리면 LLM이 임의로 보정하지 않도록 ``ValueError``를 낸다.
    """
    text = (content or "").strip()
    command = text.split("|", 1)[0].strip()
    if command not in {"추가", "완료"}:
        return None

    parts = [part.strip() for part in text.split("|", 3)]
    if command == "완료":
        if len(parts) != 2 or not parts[1]:
            raise ValueError("완료 문법: 완료 | 정확한 이름")
        return {"action": "complete", "name_hint": parts[1], "_explicit": True}

    if len(parts) not in {3, 4} or not parts[2]:
        raise ValueError("추가 문법: 추가 | YYYY-MM-DD [HH:MM] | 이름 | 비고")
    match = _DEADLINE_RE.fullmatch(parts[1])
    if not match:
        raise ValueError("마감은 YYYY-MM-DD 또는 YYYY-MM-DD HH:MM 형식이어야 합니다")
    deadline, hour, minute = match.groups()
    date.fromisoformat(deadline)  # 윤년·월별 일수까지 검증
    item = {
        "action": "add",
        "deadline": deadline,
        "name": parts[2],
        "note": parts[3] if len(parts) == 4 else "",
        "_explicit": True,
    }
    if hour is not None:
        item["deadline_time"] = f"{hour}:{minute}"
    return item


def _validate_parsed_item(item):
    """LLM/명시적 파서 결과를 저장 가능한 최소 스키마로 검증한다."""
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError("과제 파싱 결과가 객체가 아닙니다")
    action = item.get("action")
    if action == "add":
        deadline = item.get("deadline")
        name = item.get("name")
        if not isinstance(deadline, str) or not isinstance(name, str) or not name.strip():
            raise ValueError("추가 결과에 마감일 또는 이름이 없습니다")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline):
            raise ValueError("마감일 형식이 YYYY-MM-DD가 아닙니다")
        date.fromisoformat(deadline)
        deadline_time = item.get("deadline_time")
        if deadline_time is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", deadline_time):
            raise ValueError("잘못된 마감 시간입니다")
    elif action == "complete":
        if not isinstance(item.get("name_hint"), str) or not item["name_hint"].strip():
            raise ValueError("완료 결과에 과제명이 없습니다")
    else:
        raise ValueError(f"알 수 없는 과제 동작: {action!r}")
    return item


def _apply_parsed(assignments, messages, parsed):
    """파싱 결과를 복사본에 적용한다. 추가 명령은 message_id로 멱등 처리한다."""
    result = list(assignments)
    for msg, raw_item in zip(messages, parsed):
        item = _validate_parsed_item(raw_item)
        if not item:
            continue
        if item["action"] == "add":
            message_id = str(msg["id"])
            if any(str(existing.get("message_id")) == message_id for existing in result):
                continue
            saved = {
                "message_id": message_id,
                "deadline": item["deadline"],
                "name": item["name"].strip(),
                "note": item.get("note", "") if isinstance(item.get("note", ""), str) else "",
            }
            if item.get("deadline_time"):
                saved["deadline_time"] = item["deadline_time"]
            result.append(saved)
        else:
            result = _remove_matching(
                result,
                item["name_hint"],
                exact_only=bool(item.get("_explicit")),
            )
    return result


def _fetch_discord_assignments():
    """#과제입력 채널의 새 메시지를 LLM으로 파싱해 과제 목록을 갱신한다.

    로컬 개발에서는 .private/ 캐시에 마지막으로 읽은 메시지 ID와 과제 목록을
    저장한다. GitHub Actions처럼 캐시가 없는 실행 환경에서는 Discord 기록을
    오래된 순서로 다시 읽어 현재 목록을 재구성하므로 개인 과제 내용을 Git
    저장소에 커밋할 필요가 없다.
    봇 토큰/채널 ID가 없거나 조회가 실패하면 마지막 저장 목록을 반환한다.
    LLM 파싱 실패 시 명시적 명령만 멱등 적용하고 커서는 전진시키지 않는다.
    """
    state = _load_state()
    cached = list(state["assignments"])
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel_id = os.environ.get("ASSIGNMENT_CHANNEL_ID", "")
    if not bot_token or not channel_id:
        return cached

    try:
        if state.get("last_message_id"):
            messages = _discord.fetch_channel_messages(
                channel_id,
                bot_token,
                after_id=state["last_message_id"],
            )
        else:
            messages = _discord.fetch_channel_history(
                channel_id,
                bot_token,
                max_messages=max(100, settings.env_int("ASSIGNMENT_HISTORY_LIMIT", 2000)),
            )
    except Exception as e:
        # Discord 오류 문자열에는 요청 URL/채널 ID가 들어갈 수 있으므로
        # 공개 Actions 로그에는 예외 종류만 남긴다.
        print(f"[경고] 과제 채널 조회 실패(저장 목록 사용): {type(e).__name__}")
        fail("과제채널")
        return cached
    messages = [m for m in messages if m.get("content") and not m.get("author", {}).get("bot")]

    if not messages:
        return cached

    parsed = [None] * len(messages)
    llm_indices = []
    for i, message in enumerate(messages):
        try:
            item = _parse_explicit_message(message["content"])
        except Exception as e:
            # 한 메시지의 오타가 앞뒤의 정상 명령과 이후 모든 실행을 막지
            # 않도록 해당 메시지만 건너뛴다. 본문/ID는 로그에 남기지 않는다.
            print(f"[경고] 과제 명령 1건 문법 오류(건너뜀): {type(e).__name__}")
            fail("과제 명령 문법")
            continue
        if item is None:
            llm_indices.append(i)
        else:
            parsed[i] = item

    if llm_indices:
        try:
            batch_size = max(1, min(settings.env_int("ASSIGNMENT_LLM_BATCH_SIZE", 10), 20))
            by_date = {}
            for i in llm_indices:
                # A fresh Actions runner replays history daily. "Tomorrow"
                # belongs to the message's creation date, not today's run.
                stamp = messages[i].get("timestamp")
                sent_at = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else datetime.now(KST)
                if sent_at.tzinfo is None:
                    raise ValueError("message timestamp must include timezone")
                by_date.setdefault(sent_at.astimezone(KST).date().isoformat(), []).append(i)
            for message_date, indices in by_date.items():
                for offset in range(0, len(indices), batch_size):
                    batch_indices = indices[offset : offset + batch_size]
                    llm_items = _llm.parse_assignments(
                        [messages[i]["content"] for i in batch_indices], message_date,
                    )
                    if len(llm_items) != len(batch_indices):
                        raise ValueError("LLM 응답 개수 불일치")
                    for i, item in zip(batch_indices, llm_items):
                        parsed[i] = item
        except Exception as e:
            print(f"[경고] 과제 메시지 파싱(LLM) 실패(커서 유지): {type(e).__name__}")
            fail("과제 자동파싱(LLM)")
            # 명시적 명령은 LLM 장애와 무관하게 적용하되 message_id로
            # 중복을 막는다. 커서는 그대로여서 자연어 메시지는 다음 실행에 재시도된다.
            try:
                assignments = _apply_parsed(cached, messages, parsed)
            except Exception:
                return cached
            if assignments != cached:
                _save_state({"last_message_id": state.get("last_message_id"), "assignments": assignments})
            return assignments

    try:
        assignments = _apply_parsed(cached, messages, parsed)
    except Exception as e:
        print(f"[경고] 과제 파싱 결과 검증 실패(커서 유지): {type(e).__name__}")
        fail("과제 자동파싱 검증")
        return cached

    _save_state({"last_message_id": messages[-1]["id"], "assignments": assignments})
    return assignments


def get_assignments(now=None):
    """수동 목록 + 채널 자동파싱 결과를 합쳐 D-day로 변환.

    연체 항목도 음수 D-day로 그대로 반환해 해야 할 일을 숨기지 않는다.
    """
    today = (now or datetime.now(KST)).astimezone(KST).date()
    result = []
    for deadline_str, name, note in ASSIGNMENTS:
        y, m, d = (int(x) for x in deadline_str.split("-"))
        days = (date(y, m, d) - today).days
        result.append((days, name, note))

    try:
        discord_items = _fetch_discord_assignments()
    except Exception as e:
        print(f"[경고] 과제 채널 조회 실패: {type(e).__name__}")
        fail("과제채널")
        discord_items = _load_state()["assignments"]

    for item in discord_items:
        try:
            y, m, d = (int(x) for x in item["deadline"].split("-"))
        except Exception:
            continue
        days = (date(y, m, d) - today).days
        note = item.get("note", "")
        if item.get("deadline_time"):
            time_note = f"{item['deadline_time']} 마감"
            note = f"{time_note} · {note}" if note else time_note
        result.append((days, item["name"], note))

    result.sort(key=lambda x: x[0])
    return result
