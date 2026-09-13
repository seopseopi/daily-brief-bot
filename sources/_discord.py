"""디스코드 봇 REST API 호출 (stdlib만 사용).

get_assignments()의 #과제입력 채널 자동 파싱 전용. 웹훅(discord_sender.py)과
는 별개로, 이건 채널 메시지를 '읽기' 위한 봇 토큰 기반 호출이다.
"""

import json
import urllib.parse
import urllib.request

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
API_BASE = "https://discord.com/api/v10"
TIMEOUT = 15


def fetch_channel_messages(channel_id, bot_token, after_id=None, before_id=None, limit=100):
    """channel_id의 최신 메시지를 시간순(오래된 것부터)으로 반환한다.

    after_id를 주면 그 메시지 ID 이후 것만 가져온다 (증분 조회용).
    before_id는 전체 기록을 과거 방향으로 페이지네이션할 때 쓴다.
    """
    if after_id and before_id:
        raise ValueError("after_id와 before_id는 동시에 사용할 수 없습니다")
    if not str(channel_id).isdigit():
        raise ValueError("Discord channel ID must be numeric")
    limit = max(1, min(int(limit), 100))
    query = {"limit": limit}
    if after_id:
        query["after"] = str(after_id)
    if before_id:
        query["before"] = str(before_id)
    url = f"{API_BASE}/channels/{channel_id}/messages?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bot {bot_token}",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read())
    if not isinstance(data, list):
        raise ValueError("Discord messages response is not a list")
    return sorted(data, key=lambda m: int(m["id"]))


def fetch_channel_history(channel_id, bot_token, max_messages=2000):
    """채널 기록을 오래된 순서로 반환한다.

    상태 파일이 없는 일회성 runner에서도 추가/완료 메시지를 처음부터 재생할
    수 있게 최신 페이지에서 과거 방향으로 이동한다. 상한에 걸렸는데 더 오래된
    기록이 있을 수 있으면 불완전한 과제 목록을 만들지 않고 명시적으로 실패한다.
    """
    max_messages = max(100, int(max_messages))
    collected = []
    before_id = None
    while len(collected) < max_messages:
        page_limit = min(100, max_messages - len(collected))
        page = fetch_channel_messages(
            channel_id,
            bot_token,
            before_id=before_id,
            limit=page_limit,
        )
        if not page:
            break
        collected.extend(page)
        before_id = min(page, key=lambda message: int(message["id"]))["id"]
        if len(page) < page_limit:
            break
    else:
        raise RuntimeError(
            f"Discord assignment history reached ASSIGNMENT_HISTORY_LIMIT={max_messages}"
        )

    deduplicated = {str(message["id"]): message for message in collected}
    return sorted(deduplicated.values(), key=lambda message: int(message["id"]))
