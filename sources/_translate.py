"""영→한 번역 공용 유틸리티 (stdlib만 사용, 키 불필요).

구글 번역 웹 클라이언트가 쓰는 비공식 엔드포인트. 무료·키 불필요지만
문서화된 공식 API가 아니라 언제든 막힐 수 있다 — 실패하면 호출부가
원문(영어)으로 폴백해야 한다.
"""

import json
import urllib.parse
import urllib.request

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8


def translate_en_ko(text, max_len=None):
    if not text or not text.strip():
        return text
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({
        "client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text
    })
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read())
    translated = "".join(seg[0] for seg in data[0] if seg[0])
    if max_len and len(translated) > max_len:
        translated = translated[: max_len - 1].rstrip() + "…"
    return translated
