"""헤더의 "오늘의 세 줄" — 다른 6개 섹션 실제 내용을 LLM(Claude Haiku)이 요약."""

import urllib.error

from sources import _llm
from sources._shared import fail


def get_highlights(context_text=""):
    """ANTHROPIC_API_KEY가 없거나 호출이 실패하면 조용히 비-LLM 폴백으로
    내려간다 — 브리핑 자체는 항상 나가야 하므로.
    """
    try:
        return _llm.summarize_highlights(context_text)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[경고] LLM 요약 실패: HTTP {e.code}\n{body}")
        fail("오늘의 세 줄(LLM)")
        return [("오늘의 세 줄 요약 실패", "아래 섹션을 직접 확인해주세요 — LLM 호출이 안 됐습니다")]
    except Exception as e:
        print(f"[경고] LLM 요약 실패: {type(e).__name__}: {e}")
        fail("오늘의 세 줄(LLM)")
        return [("오늘의 세 줄 요약 실패", "아래 섹션을 직접 확인해주세요 — LLM 호출이 안 됐습니다")]
