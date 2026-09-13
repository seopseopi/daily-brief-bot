"""Environment-backed configuration for the morning brief.

Secrets (Discord tokens and private calendar URLs) stay in environment variables.
Non-secret defaults keep a local dry-run useful without pretending that optional
integrations are configured.
"""

from __future__ import annotations

import json
import os
import re


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    """Read a JSON array or a newline/semicolon separated environment value.

    Commas are deliberately not separators because signed/private URLs may
    legitimately contain them.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default)
    if raw.startswith("["):
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [part.strip() for line in raw.splitlines() for part in line.split(";") if part.strip()]


def env_symbols(name: str, market: str) -> list[str]:
    """Read and validate a private holding-symbol list without logging values.

    Accepted forms are a JSON string array or newline/semicolon-separated
    symbols. A malformed JSON-looking value fails closed instead of being
    reinterpreted as a literal ticker. Duplicates are removed in input order.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []

    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            return []
        candidates = parsed
    else:
        candidates = [part for line in raw.splitlines() for part in line.split(";")]

    market = market.upper()
    if market == "KR":
        pattern = re.compile(r"\d{6}")
        normalize = lambda value: value.strip()
    elif market == "US":
        # Covers ordinary tickers plus class/dash/index-style Yahoo symbols.
        pattern = re.compile(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}")
        normalize = lambda value: value.strip().upper()
    else:
        raise ValueError("market must be KR or US")

    symbols = []
    seen = set()
    for candidate in candidates:
        symbol = normalize(candidate)
        if not symbol or not pattern.fullmatch(symbol) or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        if len(symbols) >= 50:
            break
    return symbols


LOCATION_NAME = os.environ.get("BRIEF_LOCATION_NAME", "서울").strip() or "서울"
LOCATION_LATITUDE = env_float("BRIEF_LATITUDE", 37.5665)
LOCATION_LONGITUDE = env_float("BRIEF_LONGITUDE", 126.9780)

# A Google Calendar "Secret address in iCal format" works here. Treat every
# value as a password: only store it in GitHub Actions secrets.
CALENDAR_ICS_URLS = env_list("CALENDAR_ICS_URLS")
FIXED_TIMETABLE_JSON = os.environ.get("FIXED_TIMETABLE_JSON", "").strip()
INCLUDE_FIXED_TIMETABLE = env_bool(
    "INCLUDE_FIXED_TIMETABLE",
    default=bool(FIXED_TIMETABLE_JSON) and not CALENDAR_ICS_URLS,
)

# Holdings are private user configuration. Public source defaults are empty.
MARKET_HOLDINGS_KR = env_symbols("MARKET_HOLDINGS_KR", "KR")
MARKET_HOLDINGS_US = env_symbols("MARKET_HOLDINGS_US", "US")

NEWS_MAX_AGE_HOURS = max(1, env_int("NEWS_MAX_AGE_HOURS", 36))
COMMUNITY_MAX_AGE_HOURS = max(1, env_int("COMMUNITY_MAX_AGE_HOURS", 24))

DEFAULT_SECTIONS = ("weather", "schedule", "notices", "news", "market", "sports", "study", "community")
ENABLED_SECTIONS = set(env_list("BRIEF_SECTIONS", DEFAULT_SECTIONS))
BRIEF_MODE = os.environ.get("BRIEF_MODE", "full").strip().lower() or "full"

# Generative summaries are opt-in for fact-sensitive sections. The paper feed
# still uses the existing Anthropic integration and always links its source.
USE_LLM_NEWS_SUMMARIES = env_bool("USE_LLM_NEWS_SUMMARIES", False)
USE_LLM_COMMUNITY_SUMMARIES = env_bool("USE_LLM_COMMUNITY_SUMMARIES", True)
