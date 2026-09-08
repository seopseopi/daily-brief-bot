"""여러 도메인 모듈이 공유하는 것들.

- KST: 타임존
- _FAILURES/_fail()/get_failures(): 이번 실행에서 실패한 항목 이름 추적.
  main.py가 헤더 하단에 "⚠️ 오늘 실패: ..." 한 줄로 보여준다.
- tr(): 영→한 번역 + 실패 시 원문 폴백 (섹션 하나 때문에 전체가 죽지 않게)
"""

from datetime import timedelta, timezone

from sources import _translate

KST = timezone(timedelta(hours=9))

# 프로세스가 한 번 뜨고 끝나는 배치 스크립트라 모듈 전역 리스트로 충분하다.
_FAILURES = []


def fail(label):
    _FAILURES.append(label)


def get_failures():
    """이번 실행에서 쌓인 실패 라벨을 반환하고 비운다."""
    global _FAILURES
    out = _FAILURES
    _FAILURES = []
    return out


def tr(text, cap=180):
    """번역 실패해도 원문(영어)으로 폴백."""
    if not text:
        return ""
    try:
        return _translate.translate_en_ko(text, max_len=cap)
    except Exception:
        return text
