"""Anthropic API 호출 (stdlib만 사용, SDK 없이 REST 직접 호출).

get_highlights() / get_news() / get_study() / get_community()에서 쓴다.
API 키 없으면(로컬 테스트 등) 바로 예외를 던져서 호출부가 비-LLM
폴백으로 넘어가게 한다. 전부 JSON으로만 답하게 프롬프트를 짜고,
실제 데이터(초록·리드문·발췌)에 없는 내용은 지어내지 말라고 명시한다.
"""

import json
import os
import urllib.request

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # 매일 짧은 요약 몇 번 — 가장 저렴한 모델로 충분
TIMEOUT = 30


def _call(prompt, max_tokens=800):
    """공용 호출부. 응답 텍스트(코드펜스 제거)를 그대로 반환한다."""
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
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
    return text


def _call_json(prompt, max_tokens=800):
    return json.loads(_call(prompt, max_tokens))


HIGHLIGHTS_PROMPT = """다음은 오늘 아침 브리핑에 들어갈 6개 섹션(일정·과제, 마켓, 뉴스, 스포츠, 공부 피드, 커뮤니티)의 실제 내용이다.

{context}

이 내용을 바탕으로 "오늘의 세 줄"을 뽑아라 — 사용자가 아침에 가장 먼저 알아야 할 것 3가지.
각 항목은 (제목, 왜 중요한지 한 줄) 형태.

반드시 아래 JSON 배열 형식으로만, 다른 말 없이 정확히 3개 항목으로 답하라:
[{{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}]
"""


def summarize_highlights(context_text):
    items = _call_json(HIGHLIGHTS_PROMPT.format(context=context_text), max_tokens=500)
    return [(it["title"], it["reason"]) for it in items[:3]]


NEWS_PROMPT = """다음은 오늘 아침 뉴스 헤드라인 {n}개다. 각 기사 제목과 원문 리드문(있으면)을 준다.

{items}

각 기사가 왜 중요한지/무슨 배경인지 한국어로 한 문장씩 설명하라.
반드시 지켜야 할 것:
- 논평·의견 넣지 말고 사실 기반으로만 (누가 옳다/그르다 같은 판단 금지)
- 주어진 제목·리드문에 없는 내용을 지어내지 말 것. 리드문이 부실해서 배경을 알 수 없으면
  그냥 리드문을 자연스럽게 다듬어서 써라
- 각 문장은 80자 이내

반드시 JSON 배열로만, 다른 말 없이 정확히 {n}개 항목, 입력 순서 그대로 답하라:
["설명1", "설명2", ...]
"""


def explain_news(items):
    """items: [{"label","title","lead"}, ...]. 반환: 같은 순서의 설명 문자열 리스트."""
    lines = "\n".join(f"{i + 1}. [{it['label']}] {it['title']} — {it['lead']}" for i, it in enumerate(items))
    result = _call_json(NEWS_PROMPT.format(n=len(items), items=lines), max_tokens=600)
    if len(result) != len(items):
        raise ValueError(f"응답 개수 불일치: {len(result)} != {len(items)}")
    return result


PAPER_PROMPT = """다음은 논문 제목과 초록(영어)이다.

제목: {title}
초록: {abstract}

이 사람의 연구분야는 "{field}"이고 관심 키워드는 {keywords}이다.

아래 5개 항목으로 한국어 요약을 만들어라. 각 항목 1~2문장, 초록에 실제로 있는
내용만 써라(지어내지 말 것):
- problem: 이 논문이 다루는 문제/문제의식
- method: 어떻게 접근했는지(방법)
- result: 무엇을 알아냈는지(결과)
- limitation: 초록에 명시된 한계나 향후 과제. 초록에 그런 언급이 없으면
  정확히 "초록에 명시된 한계 없음"이라고 써라(지어내지 말 것)
- connection: 위 연구분야/키워드와 이 논문의 실제 접점. 억지로 엮지 말고,
  직접적인 관련이 없으면 정확히 "직접적 접점 없음"이라고 솔직하게 써라

반드시 아래 JSON 객체 형식으로만 답하라:
{{"problem": "...", "method": "...", "result": "...", "limitation": "...", "connection": "..."}}
"""


def summarize_paper(title, abstract, field, keywords):
    return _call_json(
        PAPER_PROMPT.format(title=title, abstract=abstract, field=field, keywords=", ".join(keywords)),
        max_tokens=700,
    )


COMMUNITY_PROMPT = """다음은 커뮤니티(디시인사이드/레딧) 화제글 {n}개다. 각 글의 제목과, 있으면 본문
발췌(목록/상세 페이지에서 긁어온 것이라 문장 중간에 잘려 있을 수 있음)를 준다.

{items}

각 글에 대해 한국어로 한 문장짜리 "디깅 요약"을 써라.
반드시 지켜야 할 것:
- 발췌가 문장 중간에 잘려 있으면 잘린 부분을 지어내지 말고, 있는 내용만 자연스럽게 정리
- 발췌가 없거나 의미 없으면(이미지만 있는 글 등) 제목만 보고 짧게 정리하되,
  모르는 내용을 지어내지 말 것
- 자극적/혐오 표현이 있으면 순화해서 사실만 전달, 논쟁적 어조 쓰지 말 것
- 각 문장 70자 이내

반드시 JSON 배열로만, 다른 말 없이 정확히 {n}개 항목, 입력 순서 그대로 답하라:
["요약1", "요약2", ...]
"""


def explain_community(items):
    """items: [{"label","title","excerpt"}, ...]. 반환: 같은 순서의 요약 문자열 리스트."""
    lines = "\n".join(
        f"{i + 1}. [{it['label']}] {it['title']} — 발췌: {it['excerpt'] or '(없음)'}"
        for i, it in enumerate(items)
    )
    result = _call_json(COMMUNITY_PROMPT.format(n=len(items), items=lines), max_tokens=600)
    if len(result) != len(items):
        raise ValueError(f"응답 개수 불일치: {len(result)} != {len(items)}")
    return result


ASSIGNMENT_PROMPT = """다음은 디스코드 #과제입력 채널에 올라온 메시지 {n}개다. 오늘 날짜는 {today}(KST)다.

{items}

각 메시지를 아래 세 종류 중 하나로 분류하라:
1. 새 과제 등록 — 과제명과 마감일이 있는 경우
2. 과제 완료 처리 — "완료", "끝", "다 함", "제출함" 등으로 이미 등록된 과제를
   끝냈다고 알리는 경우 (마감일 언급 없이 과제명만 나올 수도 있음)
3. 그 외 — 잡담·질문 등 과제와 무관

반드시 지켜야 할 것:
- 새 과제의 상대적 날짜("내일", "이번주 금요일", "9/20", "다음주까지")는 오늘
  날짜 기준으로 계산해서 절대 날짜(YYYY-MM-DD)로 변환하라
- 연도가 안 적혀 있으면 오늘 기준 가장 가까운 미래 날짜로 추정하라
  (그 날짜가 이미 지난 달/일이면 내년으로)
- 새 과제인데 마감일을 알 수 없으면 3번(그 외)으로 처리
- 완료 처리는 메시지에서 언급한 과제명 그대로 name_hint에 넣어라(정규화하지 말 것 —
  나중에 기존 목록과 느슨하게 매칭한다)
- 없는 내용을 지어내지 말 것

반드시 JSON 배열로만, 다른 말 없이 정확히 {n}개 항목(입력 순서 유지):
- 1번(새 과제): {{"action": "add", "name": "...", "deadline": "YYYY-MM-DD", "note": "..."}}
- 2번(완료): {{"action": "complete", "name_hint": "..."}}
- 3번(그 외): null
"""


def parse_assignments(messages, today_str):
    """messages: 원문 문자열 리스트. 반환: 같은 순서로 dict 또는 None 리스트."""
    lines = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(messages))
    result = _call_json(ASSIGNMENT_PROMPT.format(n=len(messages), today=today_str, items=lines), max_tokens=900)
    if len(result) != len(messages):
        raise ValueError(f"응답 개수 불일치: {len(result)} != {len(messages)}")
    return result


GLOSSARY_PROMPT = """다음은 오늘 소개할 논문의 제목과 초록이다.

제목: {title}
초록: {abstract}

이 논문에 실제로 나오는(또는 이 논문을 이해하려면 필요한) ML/AI 개념 중에서:
- concept: 가장 핵심적인 개념 하나를 골라 깊게 설명(2~3문장, 정확해야 함)
- terms: 그 다음으로 자주 나오거나 알아두면 좋은 용어 3개를 짧게 설명(각 1문장)

반드시 지켜야 할 것:
- 이 논문과 무관한 개념을 억지로 넣지 말 것 — 실제로 초록에 등장하거나
  초록 내용을 이해하는 데 직접 필요한 것만
- 설명은 정확한 정의여야 하고, 초록에 없는 세부사항을 지어내지 말 것
- 한국어로 작성

반드시 JSON 객체로만 답하라:
{{"concept": {{"name": "...", "desc": "..."}}, "terms": [{{"term": "...", "desc": "..."}}, {{"term": "...", "desc": "..."}}, {{"term": "...", "desc": "..."}}]}}
"""


def generate_glossary(title, abstract):
    """오늘 논문에서 실제로 뽑은 개념 1개 + 용어 3개. 논문과 무관한 내용 지어내지 않음."""
    return _call_json(GLOSSARY_PROMPT.format(title=title, abstract=abstract), max_tokens=600)
