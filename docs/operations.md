# 운영과 문제 해결

[처음으로](../README.md) · [설정 안내](configuration.md) · [데이터 소스](sources.md)

## 예약 발송

[`morning.yml`](../.github/workflows/morning.yml)의 발송 목표는 **매일 08:00 KST**입니다. `Asia/Seoul` 시간대로 05:17·05:47·06:17·06:47·07:17에 실행 기회를 만듭니다. 최근 약 2시간의 예약 지연에 대비해 runner를 일찍 시작하고, 07:57까지 대기한 뒤 최신 데이터를 수집합니다. 수집이 끝나면 08:00까지 기다렸다가 전송합니다. 최대 대기 시간을 포함해 작업 제한은 180분입니다.

같은 실행 그룹은 직렬로 처리하고, 첫 성공 날짜와 실제 전송 완료 시각을 `data/delivery_state.json`에 기록합니다. 같은 날짜의 후속 **예약 실행**은 수집·대기·전송을 건너뜁니다. 08:00 이후에 시작하거나 수집이 늦어진 복구 실행은 다음 날까지 기다리지 않고 즉시 전송합니다.

GitHub Actions 예약은 [정시 실행 SLA가 없어 혼잡 시 늦거나 누락될 수 있습니다](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). 미리 시작하는 대기 방식은 지연을 흡수하지만 정시를 보장하지는 않습니다. 08:00 정시가 필수인 환경은 상시 서버 또는 별도 스케줄러가 필요합니다. 대기 중 runner 실행 시간도 사용량에 포함되므로 비공개 저장소로 옮길 경우 비용·분 한도를 확인하세요.

수동 `workflow_dispatch`는 예약 중복 방지를 적용하지 않아 다시 전송할 수 있습니다. GitHub의 `Actions → 아침 브리핑 → Run workflow`는 **실제 Discord 전송**입니다.

## 전송 실패와 재시도

Discord 메시지는 embed 개수와 글자 수 제한에 맞춰 나눕니다. HTTP `429`와 `5xx`는 재시도하고, 웹후크 누락·전송 실패는 프로세스 실패로 남깁니다. 전송이 끝나면 공개 공지 상태와 전송 날짜만 Git에 저장합니다.

로컬 실행에서도 공지 읽음 상태는 전체 전송 성공 후 확정합니다. `--preview`·`--demo`는 Discord로 보내거나 상태 파일을 저장하지 않습니다.

여러 Discord 요청과 Git 커밋은 하나의 원자적 작업이 아닙니다. 일부 메시지를 보낸 뒤 후속 전송에 실패하거나, 전송 후 Git push만 실패하면 복구 실행에서 앞선 메시지가 중복될 수 있습니다. 재실행 전 Discord 채널과 Actions 결과를 함께 확인하세요.

## 상태 파일

| 파일 | 내용 | 보관 방식 |
| :--- | :--- | :--- |
| `data/seen_notices.json` | 이미 확인한 공개 공지 ID | 전송 성공 뒤 Git 저장 |
| `data/delivery_state.json` | 최근 성공한 예약 전송 날짜 | 전송 성공 뒤 Git 저장 |
| `.private/discord_assignments.json` | 개인 과제와 Discord 메시지 읽기 위치 | Git 제외. 로컬 비공개 캐시 |

개인 일정은 Secret 또는 비공개 iCal에, 보유종목은 Secret에 둡니다. 로컬 캐시 없는 Actions runner는 Discord 채널 기록에서 과제를 다시 구성하므로, 오래된 과제 복원 범위는 `ASSIGNMENT_HISTORY_LIMIT`의 영향을 받습니다.

기존 버전에서 개인 과제·시간표·보유종목을 이미 커밋했다면 현재 파일을 삭제해도 과거 Git 이력은 남습니다. 공개 저장소에 노출된 경우 저장소 공개 범위를 먼저 확인하고, 노출된 접근 키·캘린더 주소를 재설정한 뒤 이력 정리 또는 비공개 저장소 이전을 진행하세요.

## 증상별 확인

연결이 의심되면 먼저 아래의 [실제 연결 점검](#실제-연결-점검)으로 실패한 소스를 확인합니다.

| 증상 | 확인할 항목 |
| :--- | :--- |
| 브리핑이 도착하지 않음 | Actions 실행 시작 여부 → 테스트 결과 → 웹후크 설정 → 전송 단계 로그 |
| 08:00보다 늦게 도착 | 조기 예약의 실제 시작 시각, 07:57 수집 시작과 완료 시각. cron은 정시 보장 없음 |
| `개인 일정 미연결` | `CALENDAR_ICS_URLS` 또는 `FIXED_TIMETABLE_JSON` Secret 설정 |
| `일정 소스 오류` / 부분 조회 | 캘린더 접근 가능 여부·고정 시간표 JSON 형식·시각 겹침 |
| 등록한 과제가 보이지 않음 | 봇의 채널 읽기 권한·채널 ID·명령 날짜 형식·이력 조회 한도 |
| 자연어 과제 해석 실패 | API 키·API 이용 상태. 명시적 `추가`/`완료` 명령 사용 가능 |
| 뉴스·스포츠·시장 일부 실패 | 원본 서비스 응답·데이터 최신성·HTML/API 구조 변화 |
| macOS 등에서 `SSLCertVerificationError` | 기본 CA 저장소가 비어 있으면 사용 가능한 OS 인증서 묶음을 자동으로 사용. 계속 실패하면 Python CA 설치 상태 또는 `SSL_CERT_FILE`의 신뢰할 수 있는 인증서 묶음 확인. TLS 검증은 유지 |
| 전송은 됐는데 workflow 실패 | 상태 저장 단계의 Git push 실패 여부. 수동 재실행 시 중복 가능 |

이슈를 만들 때는 실행 시각·증상·실패한 섹션과 비밀값을 제거한 로그를 첨부합니다. 웹후크·토큰·비공개 캘린더 URL·실제 과제 내용은 첨부하지 않습니다.

## 실제 연결 점검

```bash
python main.py --check-connections
python main.py --check-connections --sections weather,schedule,news --format json
```

`--doctor`는 설정값의 존재·형식을 확인합니다. `--check-connections`는 선택한 데이터 소스를 실제로 조회하고 **수집 내용 없이 상태만** 출력합니다. `text`와 `json` 형식을 지원하며, 미설정·부분 실패·전체 실패가 있으면 종료 코드 `1`을 반환합니다.

JSON의 `coverage`에는 실제 기사 분야 수, 일정 수, 설정 대비 보유종목 수, 논문·개념·용어 존재 여부 등을 포함합니다. `optional_unconfigured`는 고정 시간표를 사용해도 개인 캘린더가 별도로 연결되지 않았음을 구분합니다. 정상 0건인 학사공지는 브리핑에서 숨기지 않고 새 공지 없음으로 표시합니다.

이 검사는 Discord로 메시지를 보내거나 상태 파일을 저장하지 않습니다. 선택한 소스에 필요한 외부 API와 AI API는 호출할 수 있습니다. 데이터 수집 상태를 확인하는 검사이므로 웹후크 전송 성공이나 실제 메시지 도착을 확인한 것으로 해석하지 않습니다.

GitHub Actions의 운영 설정으로 확인하려면 [`connections.yml`](../.github/workflows/connections.yml)을 선택해 `Run workflow`로 수동 실행합니다. 저장소의 Secrets·Variables를 적용해 연결을 검사하며 브리핑은 발송하지 않습니다. GitHub Secret을 설정해도 로컬 환경 변수에는 자동으로 반영되지 않습니다.

## 개발 검증

```bash
python3 -m unittest discover -s tests -v
```

회귀 테스트는 외부 응답을 대체해 날짜·마감·일정 반복/예외·기사 신선도·전송 제한·재시도·개인정보와 상태 보존을 검증합니다. 통과 결과는 현재 외부 사이트 응답이나 실제 Discord 도착을 보장하지 않습니다. 실제 전송 확인은 웹후크가 연결된 운영 실행 결과로 별도 판단합니다.
