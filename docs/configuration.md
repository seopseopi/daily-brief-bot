# 설정 안내

[처음으로](../README.md) · [운영·문제 해결](operations.md) · [데이터 소스](sources.md)

GitHub에서 `Settings → Secrets and variables → Actions`를 엽니다. 로컬에서는 같은 이름의 환경 변수를 설정합니다. `.env` 파일을 자동으로 읽지는 않습니다.

## 먼저 연결할 항목

| 이름 | 저장 위치 | 용도 |
| :--- | :--- | :--- |
| `DISCORD_WEBHOOK_URL` | Secret | 브리핑을 받을 Discord 웹후크. **실제 전송에 필수** |
| `CALENDAR_ICS_URLS` | Secret | 개인 일정의 비공개 iCal 주소. 여러 개면 줄바꿈으로 구분 |
| `DISCORD_BOT_TOKEN` | Secret | 과제를 입력하는 Discord 채널을 읽는 봇 토큰 |
| `ASSIGNMENT_CHANNEL_ID` | Secret | 과제 입력 채널 ID. 봇 토큰과 함께 설정 |
| `ANTHROPIC_API_KEY` | Secret | 자연어 과제 해석·논문 설명·선택적 뉴스/커뮤니티 요약 |

개인 일정·과제 채널·AI 요약은 선택 연결입니다. 웹후크가 없으면 실제 전송은 실패 종료합니다. API 키가 없어도 명시적 과제 명령과 공개 사실 데이터는 사용할 수 있지만, 자연어 과제 해석 등 AI가 필요한 작업은 실패 또는 대체 표시됩니다.

## 개인 캘린더

Google Calendar 웹의 `설정 → 내 캘린더 → 캘린더 통합 → iCal 형식의 비밀 주소`를 복사해 `CALENDAR_ICS_URLS` **Secret**에 넣습니다. 여러 캘린더는 한 줄에 하나씩 넣습니다. [Google 공식 안내](https://support.google.com/calendar/answer/37648?hl=ko)

반복·취소·종일 일정과 반복 일정의 예외를 반영합니다. 캘린더가 연결되지 않았거나 조회에 실패하면 해당 상태를 브리핑에 표시합니다.

비공개 iCal 주소는 해당 캘린더에 접근할 수 있는 비밀값입니다. 코드·로그·일반 Variables에 넣지 마세요. 주소가 노출되면 캘린더 설정에서 재설정합니다.

### 고정 시간표

반복되는 주간 일정은 `FIXED_TIMETABLE_JSON` **Secret**으로 설정할 수 있습니다. 아래는 실제 개인정보가 없는 형식 예시입니다.

```json
{
  "0": [["09:00", "10:30", "일정 이름", "장소 또는 메모"]],
  "6": []
}
```

요일 키는 월요일 `0`부터 일요일 `6`까지입니다. 고정 시간표의 시각 오류나 겹침은 `일정 소스 오류`로 표시합니다. 캘린더 없이 고정 시간표만 설정하면 기본으로 사용합니다. **캘린더와 함께 표시하려면** `INCLUDE_FIXED_TIMETABLE=true`를 Variable로 지정합니다. `false`는 고정 시간표를 끕니다.

## 위치와 섹션

| 이름 | 기본값 | 설정 내용 |
| :--- | :--- | :--- |
| `BRIEF_LOCATION_NAME` | `서울` | 날씨에 표시할 지역명 |
| `BRIEF_LATITUDE` | `37.5665` | 예보 위치의 위도 |
| `BRIEF_LONGITUDE` | `126.9780` | 예보 위치의 경도 |
| `BRIEF_SECTIONS` | 아래 8개 전체 | 표시할 섹션을 세미콜론으로 구분 |
| `BRIEF_MODE` | `full` | `compact`로 핵심 위주의 짧은 브리핑, `full`로 전체 브리핑 |
| `NEWS_MAX_AGE_HOURS` | `36` | 뉴스의 최대 발행 경과시간 |
| `COMMUNITY_MAX_AGE_HOURS` | `24` | 커뮤니티 게시물의 최대 경과시간 |
| `USE_LLM_NEWS_SUMMARIES` | `false` | 매체 리드문 기반 AI 압축 요약 |
| `USE_LLM_COMMUNITY_SUMMARIES` | `true` | 커뮤니티 본문 일부를 AI로 요약 |

기본 섹션은 `weather;schedule;notices;news;market;sports;study;community`입니다. 개인 일정을 중심으로 간결하게 받으려면 다음과 같이 설정합니다.

```text
BRIEF_SECTIONS=weather;schedule;notices;news
```

과제는 `schedule` 섹션에 포함됩니다. 불리언 값은 `true`/`false`를 권장하며 `1`, `yes`, `on`, `y`도 참으로 인식합니다.

위치 3개 항목은 같은 이름의 **Secret을 Variable보다 우선**합니다. 집처럼 정밀한 위치는 Secret에 넣으세요. 나머지 공개 설정은 Variables로 지정할 수 있습니다.

## 과제 입력

과제 채널에는 아래 명령을 **메시지 하나에 하나씩** 보냅니다. 날짜만 입력할 수도 있으며, 마감 시각을 알면 함께 넣습니다.

```text
추가 | 2026-09-15 23:59 | 데이터과학 보고서 | PDF 제출
완료 | 데이터과학 보고서
```

- 명시적 명령은 LLM 없이 날짜·시각을 검증합니다. 이름은 필수, 비고는 선택입니다.
- 완료 명령은 공백·대소문자 정규화 후 이름이 유일하게 정확히 일치할 때 처리합니다.
- 날짜 오타는 해당 메시지만 건너뛰고, 정상인 다른 메시지는 계속 처리합니다. 잘못 입력한 명령은 올바른 **새 메시지**로 다시 보내세요.
- 자연어 메시지만 LLM에 전달합니다. 기본 10개씩 나누고, 실패하면 실패 상태를 표시하며 읽기 위치를 유지해 다음 실행에 재시도합니다.
- 미완료 과제는 마감이 지나도 삭제하지 않고 `N일 연체`로 표시합니다.
- 로컬 캐시가 없는 Actions runner는 채널 기록을 오래된 순서로 재생합니다. `ASSIGNMENT_HISTORY_LIMIT` Variable의 기본값은 `2000`개입니다. 그 범위를 벗어난 오래된 미완료 과제는 새 환경에서 복원되지 않을 수 있습니다.

수동 목록은 [`sources/assignments_data.py`](../sources/assignments_data.py)의 `ASSIGNMENTS`에 `(마감일, 이름, 비고)` 형태로 넣습니다. 이 목록의 완료 처리는 파일에서 직접 해야 합니다. 공개 저장소에는 개인 과제 내용을 넣지 마세요.

## 관심 종목

| 이름 | 저장 위치 | 형식 |
| :--- | :--- | :--- |
| `MARKET_HOLDINGS_KR` | Secret | 6자리 국내 종목코드 목록 |
| `MARKET_HOLDINGS_US` | Secret | Yahoo Finance 티커 목록 |

JSON 문자열 배열, 세미콜론 또는 줄바꿈 구분을 지원합니다. 중복은 제거하고 각 시장 최대 50개를 읽습니다. 종목 표시명은 공급자 응답에서 가져옵니다. 기본 보유 목록은 비어 있습니다.

```text
MARKET_HOLDINGS_KR=["005930","000660"]
MARKET_HOLDINGS_US=AAPL;MSFT
```

위 코드는 **설정 형식 예시**입니다. 실제 보유종목은 Secret에 등록합니다.

## 로컬 실행 옵션

| 이름 | 역할 |
| :--- | :--- |
| `BRIEF_READ_ONLY=1` | 공지·과제 수집 중 상태 파일 저장을 생략 |
| `DISCORD_DRY_RUN=1` | Discord 웹후크 요청을 생략 |
| `ASSIGNMENT_LLM_BATCH_SIZE` | 자연어 과제 해석의 배치 크기. 기본 `10`, 범위 `1`–`20` |

`ASSIGNMENT_LLM_BATCH_SIZE`는 현재 워크플로가 전달하지 않는 로컬/사용자 정의 실행용 설정입니다. 실제 전송 없이 안전하게 내용을 확인하는 실행법은 [README](../README.md)의 미리보기를 참고하세요.

```bash
python main.py --doctor
python main.py --preview --sections weather,schedule,news --compact
python main.py --demo --format markdown --output /tmp/morning-brief-demo.md
```

`--doctor`는 설정의 존재·형식을 로컬에서 점검합니다. API 키 유효성, 캘린더 접근 권한 또는 Discord 도착 여부를 확인하는 네트워크 연결 검사는 아닙니다. `--preview`는 설정한 외부 데이터·AI API를 호출할 수 있으나 Discord 전송과 상태 파일 저장은 생략합니다.
