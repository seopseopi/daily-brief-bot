"""Public, fictional fixtures. Never reads private configuration or the network."""

from datetime import datetime, timedelta
from sources._shared import KST

DEMO_NOW = datetime(2026, 9, 14, 7, 30, tzinfo=KST)


def demo_data(now=DEMO_NOW):
    def at(hour, minute=0):
        return now.replace(hour=hour, minute=minute)

    def event(name, start, end, location):
        return {"name": name, "start": start, "end": end, "location": location,
                "all_day": False, "transparent": False, "calendar": "예시 캘린더"}

    return {
        "schedule": {"status": "fresh", "calendar_configured": True,
                     "source": "예시 캘린더 · 실제 일정 아님", "as_of": now,
                     "events": [event("프로젝트 회의", at(9), at(10), "온라인"),
                                event("스터디", at(9, 30), at(10, 30), "도서관"),
                                event("실습 수업", at(14), at(16), "예시 강의실")]},
        "assignments": [(0, "실습 보고서 제출", "23:59 마감 · PDF 확인"),
                        (2, "발표 자료 초안", "핵심 결과 3장 정리"),
                        (6, "팀 프로젝트 중간 점검", "진행 상황 공유")],
        "weather": {"status": "fresh", "location": "서울 · 예시 예보", "condition": "구름 많음",
                    "temperature": 22.0, "apparent_temperature": 23.0, "low": 20.0,
                    "high": 28.0, "rain_probability": 70, "wind_speed": 9.0,
                    "advice": ["오후 외출에는 우산을 챙기세요", "일교차에 대비해 얇은 겉옷 준비"],
                    "source": "가상 날씨 데이터", "source_url": "https://open-meteo.com/en/docs", "as_of": now,
                    "periods": [{"label": label, "start": at(start), "end": at(end),
                                 "temperature_min": low, "temperature_max": high,
                                 "rain_probability": rain}
                                for label, start, end, low, high, rain in
                                [("오전", 8, 11, 22, 25, 10), ("오후", 12, 17, 25, 28, 70), ("저녁", 18, 23, 21, 24, 30)]],
                    "next_rain": {"start": at(15), "end": at(17), "probability": 70, "ongoing": False},
                    "hourly_status": "available"},
        "notices": [("예시 학사공지", [("비교과 프로그램 신청 안내 · 가상 공지", "https://example.com/notice")])],
        "news": [{"label": "🔬 과기", "title": "공개 데이터 활용 교육 프로그램 안내 · 예시 기사",
                  "detail": "공공 데이터를 분석하고 결과를 발표하는 교육 프로그램의 구성 예시입니다. 실제 뉴스가 아닙니다.",
                  "url": "https://example.com/news", "publisher": "예시 매체", "published_at": now - timedelta(hours=1),
                  "status": "fresh", "summary_kind": "publisher_lead"}],
        "market": {"kr_index": "KOSPI · 예시 2,700.00 (+0.50%)", "kr_note": "직전 거래일 종가 · 가상 수치",
                   "us_index": "S&P 500 · 예시 5,500.00 (+0.30%)", "us_note": "정규장 종가 · 가상 수치",
                   "fx": "USD/KRW · 예시 1,350.00", "outlook_kr": ("예시 흐름", "실제 시장 데이터가 아닙니다."),
                   "outlook_us": ("예시 지표", "표시 형식을 확인하기 위한 가상 값입니다."),
                   "source_note": "데모 전용 가상 수치", "as_of": now},
        "sports": {"doosan": ("⚾ 예시 경기", "예시 홈팀 4–3 예시 원정팀", "순위 미제공 · 가상 데이터", "다음 경기: 예시 18:30"),
                   "football": "관심 리그 소식을 이곳에서 확인합니다. 실제 경기 정보가 아닙니다."},
        "study": {"paper_title": "예시: 작은 모델의 추론 효율을 비교하는 방법", "paper_url": "https://example.com/paper",
                  "paper_meta": "가상 논문 · 레이아웃 예시", "summary_kind": "excerpt",
                  "paper_sections": [("다루는 문제", "정확도와 처리 시간의 균형을 살펴보는 가상 예시입니다."),
                                     ("읽을 포인트", "비교 조건과 측정 지표를 먼저 확인합니다.")],
                  "concept": ("지연 시간", "입력 후 결과를 받기까지 걸린 시간입니다."), "terms": []},
        "community": [{"source": "예시 개발 커뮤니티", "kind": "정보글", "stat": "가상 반응",
                       "title": "반복 작업을 줄인 작은 자동화 사례 · 예시 게시물",
                       "detail": "토론 링크와 요약이 표시되는 위치입니다. 실제 게시물이 아닙니다.",
                       "url": "https://example.com/discussion", "published_at": now - timedelta(hours=2)}],
    }
