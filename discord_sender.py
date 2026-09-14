"""디스코드 웹훅으로 브리핑을 전송한다."""

from bisect import bisect_right
from copy import deepcopy
import json
import os
import re
import time
import urllib.error
import urllib.request

from http_client import open_url

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 디스코드(Cloudflare)가 urllib 기본 User-Agent를 봇으로 간주해 403으로
# 차단하는 경우가 있어 명시적으로 지정한다.
USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"

# 섹션별 왼쪽 색 띠 (10진수)
COLORS = {
    "header": 0x5865F2,
    "weather": 0x3498DB,
    "schedule": 0x248046,
    "notice": 0x1ABC9C,
    "market": 0xC27C0E,
    "news": 0x5C5E66,
    "sports": 0xC0392B,
    "study": 0x7B4FCF,
    "community": 0xE67E22,
}

EMBED_LIMIT = 4096  # description 최대 길이
TITLE_LIMIT = 256
MAX_EMBEDS_PER_MESSAGE = 10
MAX_EMBED_CHARS_PER_MESSAGE = 6000
REQUEST_TIMEOUT = 15
MAX_ATTEMPTS = 4
RETRY_BASE_SECONDS = 1.0


class WebhookHTTPError(RuntimeError):
    """재시도 후에도 Discord가 거부한 응답."""

    def __init__(self, code, reason, body):
        super().__init__(f"HTTP {code} {reason}")
        self.code = code
        self.reason = reason
        self.body = body


def make_embed(title, description, color_key):
    """원문을 보존한 embed를 만든다. 전송/미리보기 직전에 페이지로 나눈다."""
    return {
        "title": title,
        "description": description,
        "color": COLORS.get(color_key, 0x5865F2),
    }


def _env_truthy(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _embed_char_count(embed):
    """Discord가 메시지당 6,000자 제한에 포함하는 embed 텍스트 수."""
    total = _text_length(embed.get("title", "")) + _text_length(embed.get("description", ""))
    total += _text_length(embed.get("author", {}).get("name", ""))
    total += _text_length(embed.get("footer", {}).get("text", ""))
    for field in embed.get("fields", []):
        total += _text_length(field.get("name", "")) + _text_length(field.get("value", ""))
    return total


def _text_length(value):
    """이모지도 안전한 UTF-16 단위로 보수적으로 길이를 계산한다."""
    return len(str(value).encode("utf-16-le")) // 2


def _title_prefix(title, limit):
    if _text_length(title) <= limit:
        return title
    result = []
    used = 0
    for char in title:
        width = _text_length(char)
        if used + width > limit - 1:
            break
        result.append(char)
        used += width
    return "".join(result) + "…"


# 일반 Markdown 링크, 괄호가 포함된 URL, 자동 링크를 페이지 경계에서 보호한다.
# 링크 자체가 한 페이지보다 길면 원문 보존을 우선해 글자 경계로 나눈다.
_LINK_PATTERN = re.compile(
    r"\[[^\]\n]+\]\((?:[^()\s]|\([^()\s]*\))*\)"
    r"|<https?://[^\s>]+>|https?://[^\s<>()]+"
)


def _split_description(description, limit):
    """문단 → 줄 → 단어 순으로 나누며 공백과 원문을 그대로 보존한다."""
    if limit < 2:
        raise ValueError("embed 메타데이터가 너무 길어 본문을 나눌 공간이 없습니다")
    lengths = [0]
    for char in description:
        lengths.append(lengths[-1] + (2 if ord(char) > 0xFFFF else 1))
    spans = [match.span() for match in _LINK_PATTERN.finditer(description)]
    starts = [start for start, _ in spans]

    def safe_boundary(point, start, allow_oversized_link=False):
        index = bisect_right(starts, point) - 1
        if index >= 0:
            link_start, link_end = spans[index]
            if link_start < point < link_end:
                if allow_oversized_link and link_start <= start:
                    return point
                return max(start, link_start)
        return point

    pages = []
    start = 0
    while start < len(description):
        end = bisect_right(lengths, lengths[start] + limit) - 1
        if end >= len(description):
            pages.append(description[start:])
            break
        end = safe_boundary(end, start, allow_oversized_link=True)
        cut = end
        for separator in ("\n\n", "\n", " "):
            boundary = description.rfind(separator, start, end)
            if boundary >= start:
                candidate = safe_boundary(boundary + len(separator), start)
                if candidate > start and description[start:candidate].strip():
                    cut = candidate
                    break
        pages.append(description[start:cut])
        start = cut
    return pages


def _validate_metadata(embed):
    """자동으로 나눌 수 없는 필드는 Discord에 요청하기 전에 검증한다."""
    fields = embed.get("fields", [])
    if len(fields) > 25:
        raise ValueError("Discord embed fields는 25개를 초과할 수 없습니다")
    limited_text = [
        ("title", embed.get("title", ""), TITLE_LIMIT),
        ("author.name", embed.get("author", {}).get("name", ""), 256),
        ("footer.text", embed.get("footer", {}).get("text", ""), 2048),
    ]
    for field in fields:
        limited_text.extend([
            ("field.name", field.get("name", ""), 256),
            ("field.value", field.get("value", ""), 1024),
        ])
    for name, value, limit in limited_text:
        if _text_length(value) > limit:
            raise ValueError(f"Discord embed {name}이 {limit}자 제한을 초과했습니다")


def prepare_embeds(embeds):
    """전송과 미리보기 공용 페이지를 반환한다. 입력과 중첩 메타는 변경하지 않는다.

    본문을 생략하지 않고 출처·시각·색상 등 메타데이터를 각 페이지에 유지한다.
    이미 준비한 페이지를 다시 전달해도 결과가 바뀌지 않는다.
    """
    prepared = []
    for original in embeds:
        embed = deepcopy(original)
        _validate_metadata(embed)
        description = embed.get("description", "")
        metadata_chars = _embed_char_count(embed) - _text_length(description)
        if metadata_chars > MAX_EMBED_CHARS_PER_MESSAGE:
            raise ValueError("embed 메타데이터가 Discord 총 6,000자 제한을 초과했습니다")
        budget = min(EMBED_LIMIT, MAX_EMBED_CHARS_PER_MESSAGE - metadata_chars)
        if _text_length(description) <= budget:
            prepared.append(embed)
            continue

        original_title = embed.get("title", "")
        page_count = 2
        while True:
            suffix = f" · {page_count}/{page_count}"
            title = _title_prefix(original_title or "브리핑", TITLE_LIMIT - _text_length(suffix))
            overhead = metadata_chars - _text_length(original_title) + _text_length(title + suffix)
            budget = min(EMBED_LIMIT, MAX_EMBED_CHARS_PER_MESSAGE - overhead)
            parts = _split_description(description, budget)
            if len(str(len(parts))) <= len(str(page_count)):
                break
            page_count = len(parts)

        for index, part in enumerate(parts, 1):
            page = deepcopy(embed)
            page["title"] = f"{title} · {index}/{len(parts)}"
            page["description"] = part
            prepared.append(page)
    return prepared


def _batch_embeds(embeds):
    """Discord의 메시지당 embed 10개/총 6,000자 제한에 맞춰 묶는다."""
    batches = []
    current = []
    current_chars = 0
    for embed in embeds:
        char_count = _embed_char_count(embed)
        if char_count > MAX_EMBED_CHARS_PER_MESSAGE:
            raise ValueError(f"embed 하나가 Discord 총 글자 제한을 초과했습니다: {char_count}자")
        if current and (
            len(current) >= MAX_EMBEDS_PER_MESSAGE
            or current_chars + char_count > MAX_EMBED_CHARS_PER_MESSAGE
            # Discord는 한 메시지에서 URL이 같은 embed를 하나만 표시한다.
            or (embed.get("url") and any(item.get("url") == embed["url"] for item in current))
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(embed)
        current_chars += char_count
    if current:
        batches.append(current)
    return batches


def _retry_after_seconds(error, body, attempt):
    """429 응답 힌트를 우선하고, 없으면 지수 백오프를 쓴다."""
    if error.code == 429:
        try:
            value = json.loads(body).get("retry_after")
            if value is not None:
                return max(0.0, float(value))
        except (ValueError, TypeError, AttributeError):
            pass
        if error.headers:
            try:
                return max(0.0, float(error.headers.get("Retry-After")))
            except (ValueError, TypeError):
                pass
    return RETRY_BASE_SECONDS * (2 ** attempt)


def _post_batch(webhook_url, embeds):
    payload = {"embeds": embeds, "allowed_mentions": {"parse": []}}
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )

    for attempt in range(MAX_ATTEMPTS):
        try:
            with open_url(req, timeout=REQUEST_TIMEOUT) as res:
                return res.status
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == MAX_ATTEMPTS - 1:
                raise WebhookHTTPError(error.code, error.reason, body) from error
            delay = _retry_after_seconds(error, body, attempt)
            print(f"[경고] Discord HTTP {error.code}; {delay:g}초 후 재시도")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = RETRY_BASE_SECONDS * (2 ** attempt)
            print(f"[경고] Discord 연결 실패; {delay:g}초 후 재시도: {type(error).__name__}")
            time.sleep(delay)
    raise RuntimeError("Discord 전송 재시도 상태 오류")


def _print_dry_run(embeds):
    print("[DRY RUN] Discord 전송 없이 콘솔에 출력합니다.\n")
    for embed in embeds:
        print("=" * 50)
        print(embed.get("title", ""))
        print(embed.get("description", ""))
        footer = embed.get("footer", {}).get("text")
        if footer:
            print(f"[기준] {footer}")


def send(embeds):
    """embed를 Discord 제한에 맞춰 여러 메시지로 나누어 전송한다."""
    embeds = prepare_embeds(embeds)
    batches = _batch_embeds(embeds)
    if _env_truthy("DISCORD_DRY_RUN"):
        _print_dry_run(embeds)
        print(f"\n[DRY RUN] Discord 메시지 {len(batches)}개로 분할 예정")
        return

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or WEBHOOK_URL
    if not webhook_url:
        print("[에러] DISCORD_WEBHOOK_URL 없음. 콘솔 테스트는 DISCORD_DRY_RUN=1을 설정하세요.")
        raise SystemExit(1)

    try:
        for index, batch in enumerate(batches, 1):
            status = _post_batch(webhook_url, batch)
            print(f"전송 완료 (status {status}, batch {index}/{len(batches)})")
    except WebhookHTTPError as error:
        # Discord 오류 본문은 사용자 입력이나 요청 정보를 되비출 수 있어
        # 공개 CI 로그에 출력하지 않는다.
        print(f"[에러] 전송 실패: HTTP {error.code} {error.reason}")
        raise SystemExit(1) from error
    except Exception as error:
        # InvalidURL 같은 예외 문자열에는 웹후크 전체 경로(토큰 포함)가
        # 들어갈 수 있으므로 예외 종류만 기록한다.
        print(f"[에러] 전송 실패: {type(error).__name__}")
        raise SystemExit(1) from error
