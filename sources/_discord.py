"""디스코드 봇 REST API 호출 (stdlib만 사용).

get_assignments()의 #과제입력 채널 자동 파싱 전용. 웹훅(discord_sender.py)과
는 별개로, 이건 채널 메시지를 '읽기' 위한 봇 토큰 기반 호출이다.
"""

import json
import urllib.request

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
API_BASE = "https://discord.com/api/v10"
TIMEOUT = 15


def fetch_channel_messages(channel_id, bot_token, after_id=None, limit=100):
    """channel_id의 최신 메시지를 시간순(오래된 것부터)으로 반환한다.

    after_id를 주면 그 메시지 ID 이후 것만 가져온다 (증분 조회용).
    """
    url = f"{API_BASE}/channels/{channel_id}/messages?limit={limit}"
    if after_id:
        url += f"&after={after_id}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bot {bot_token}",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read())
    return sorted(data, key=lambda m: int(m["id"]))
