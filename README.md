# 아침 비서 봇

매일 오전 7:30(KST) 디스코드로 브리핑을 보낸다.
일정 · 과제 · 마켓 · 뉴스 · 스포츠 · 공부 피드 · 커뮤니티 펄스.

## 지금 상태

뼈대 완성. 모든 데이터는 `sources/dummy.py`의 더미값이다.
소스를 하나씩 실제 API로 교체하면 된다.

## 셋업 (10분)

### 1. 디스코드 웹훅 만들기

1. 브리핑 받을 채널 → 톱니바퀴(채널 편집) → **연동** → **웹후크**
2. **새 웹후크** → 이름 "아침 비서" → **웹후크 URL 복사**

### 2. GitHub 저장소

1. 새 저장소 생성 (**Private 권장** — 웹훅 URL 유출 방지)
2. 이 폴더 전체를 push

### 3. 시크릿 등록

저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

- Name: `DISCORD_WEBHOOK_URL`
- Secret: 1번에서 복사한 URL

### 4. 테스트

저장소 → **Actions** 탭 → "아침 브리핑" → **Run workflow**
디스코드에 브리핑이 오면 성공.

## 주의: cron 시간

GitHub Actions cron은 UTC 기준이다. `30 22 * * *` = KST 07:30.
무료 러너는 부하에 따라 **5~15분 지연**될 수 있다.
정시성이 중요하면 `20 22 * * *`(07:20)로 당겨두는 것도 방법.

## 로컬 테스트

```bash
python main.py                              # 콘솔 출력
DISCORD_WEBHOOK_URL="..." python main.py    # 실제 전송
```

## 다음 단계 (소스 붙이기)

`sources/dummy.py`의 함수를 하나씩 교체한다. 쉬운 순서:

| 순서 | 함수 | 소스 |
|---|---|---|
| 1 | `get_schedule()` | Google Calendar API |
| 2 | `get_news()` | 연합뉴스/한경 RSS + LLM 분류 |
| 3 | `get_market()` | 네이버금융 · 야후파이낸스 |
| 4 | `get_sports()` | KBO · EPL 스코어 |
| 5 | `get_assignments()` | `#과제입력` 채널 REST 조회 + LLM 파싱 |
| 6 | `get_study()` | arXiv API + HF Daily + LLM 요약 |
| 7 | `get_community()` | 디시 스크래핑 + Reddit API |
| 8 | `get_highlights()` | 위 결과를 LLM이 3줄 요약 |

한 번에 하나씩. 교체해도 `main.py`는 건드릴 필요 없다.

## 구조

```
main.py              섹션 조립 + 전송
discord_sender.py    웹훅 전송, embed 생성
sources/dummy.py     데이터 소스 (교체 대상)
.github/workflows/   cron 스케줄
```
