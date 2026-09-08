"""데이터 소스 패키지.

구조:
  - 밑줄로 시작하는 모듈(_rss, _market, _arxiv, _community, _notices,
    _discord, _translate, _llm)은 순수 네트워크/파싱 계층 — 사이트
    구조나 API 스펙이 바뀌면 이 안에서만 고친다.
  - 밑줄 없는 모듈(schedule, assignments, notices, market, news, sports,
    study, community, highlights)은 섹션별 비즈니스 로직 — 각각 정확히
    get_*() 하나를 노출하고 main.py가 그걸 부른다.
  - _shared.py: KST, 실패추적(fail/get_failures), 번역 폴백(tr) 등 공용.

원칙:
  - 소스 하나가 실패해도 브리핑 전체가 깨지면 안 된다 — 각 get_*()가
    자기 안에서 try/except로 fallback 값을 만들고, _shared.fail()로
    실패를 기록한다. main.py가 그걸 모아 헤더 하단에 한 줄로 보여준다.
"""
