"""Anthropic API 호출 (stdlib만 사용, SDK 없이 REST 직접 호출).

get_highlights() 전용. API 키 없으면(로컬 테스트 등) 바로 예외를 던져서
호출부가 비-LLM 폴백으로 넘어가게 한다.
"""

import json
import os
import urllib.request

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # 매일 짧은 요약 1번 — 가장 저렴한 모델로 충분
TIMEOUT = 30

PROMPT_TEMPLATE = """다음은 오늘 아침 브리핑에 들어갈 6개 섹션(일정·과제, 마켓, 뉴스, 스포츠, 공부 피드, 커뮤니티)의 실제 내용이다.

{context}

이 내용을 바탕으로 "오늘의 세 줄"을 뽑아라 — 사용자가 아침에 가장 먼저 알아야 할 것 3가지.
각 항목은 (제목, 왜 중요한지 한 줄) 형태.

반드시 아래 JSON 배열 형식으로만, 다른 말 없이 정확히 3개 항목으로 답하라:
[{{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}]
"""


def summarize_highlights(context_text):
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    prompt = PROMPT_TEMPLATE.format(context=context_text)
    payload = {
        "model": MODEL,
        "max_tokens": 500,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read())

    text = data["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    items = json.loads(text)
    return [(it["title"], it["reason"]) for it in items[:3]]
