"""디스코드 웹훅으로 브리핑을 전송한다."""

import os
import json
import urllib.request

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 섹션별 왼쪽 색 띠 (10진수)
COLORS = {
    "header": 0x5865F2,
    "schedule": 0x248046,
    "market": 0xC27C0E,
    "news": 0x5C5E66,
    "sports": 0xC0392B,
    "study": 0x7B4FCF,
    "community": 0xE67E22,
}

EMBED_LIMIT = 4096  # description 최대 길이


def make_embed(title, description, color_key):
    """embed 하나를 만든다. 길이 초과 시 잘라낸다."""
    if len(description) > EMBED_LIMIT:
        description = description[: EMBED_LIMIT - 20] + "\n...(생략)"
    return {
        "title": title,
        "description": description,
        "color": COLORS.get(color_key, 0x5865F2),
    }


def send(embeds):
    """embed 리스트를 한 메시지로 전송한다. 최대 10개."""
    if not WEBHOOK_URL:
        print("[경고] DISCORD_WEBHOOK_URL 없음. 콘솔 출력으로 대체합니다.\n")
        for e in embeds:
            print("=" * 50)
            print(e["title"])
            print(e["description"])
        return

    payload = {"embeds": embeds[:10]}
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            print(f"전송 완료 (status {res.status})")
    except Exception as e:
        print(f"[에러] 전송 실패: {e}")
