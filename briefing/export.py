"""Portable, escaped previews using the same pages as Discord delivery."""

import html
import json
import re

import discord_sender as ds


def markdown(embeds):
    blocks = []
    for embed in embeds:
        blocks.append(f"## {embed.get('title', '')}\n\n{embed.get('description', '')}")
        for field in embed.get("fields", []):
            blocks.append(f"**{field['name']}**\n\n{field['value']}")
        if embed.get("footer"):
            blocks.append(f"*{embed['footer']['text']}*")
    return "\n\n".join(blocks) + "\n"


_INLINE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`|__([^_\n]+)__")


def _inline(text):
    parts, cursor = [], 0
    for match in _INLINE.finditer(text):
        parts.append(html.escape(text[cursor:match.start()]))
        label, url, bold, code, underline = match.groups()
        if url:
            parts.append(f'<a href="{html.escape(url, quote=True)}" rel="noreferrer noopener">{html.escape(label)}</a>')
        elif bold:
            parts.append(f"<strong>{html.escape(bold)}</strong>")
        elif code:
            parts.append(f"<code>{html.escape(code)}</code>")
        else:
            parts.append(f"<strong>{html.escape(underline)}</strong>")
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _body(text):
    output = []
    for line in text.splitlines():
        if not line.strip():
            output.append('<div class="space"></div>')
        elif line.startswith("-# "):
            output.append(f'<p class="meta">{_inline(line[3:])}</p>')
        elif line.startswith("> "):
            output.append(f'<p class="detail">{_inline(line[2:])}</p>')
        else:
            output.append(f"<p>{_inline(line)}</p>")
    return "\n".join(output)


def html_preview(embeds):
    cards = []
    for index, embed in enumerate(embeds):
        color = f"#{int(embed.get('color', 0x5865F2)):06x}"
        cards.append(f'<article id="section-{index}" style="--accent:{color}"><h2>{html.escape(embed.get("title", ""))}</h2>'
                     + _body(embed.get("description", ""))
                     + ''.join(f'<h3>{html.escape(field["name"])}</h3>{_body(field["value"])}' for field in embed.get("fields", []))
                     + f'<footer>{html.escape(embed.get("footer", {}).get("text", ""))}</footer></article>')
    nav = ' '.join(f'<a href="#section-{index}">{html.escape(embed.get("title", ""))}</a>' for index, embed in enumerate(embeds))
    return '''<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Daily Brief · 미리보기</title><style>
:root{color-scheme:light;--ink:#26332e;--muted:#60716a;--paper:#f5f3ec;--line:#e1e6df}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:820px;margin:auto;padding:48px 22px 70px}.eyebrow{font-size:12px;letter-spacing:.16em;color:#697b68;font-weight:700}h1{font-size:40px;line-height:1.2;margin:12px 0}header>p{color:var(--muted)}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 30px}nav a{font-size:12px;border:1px solid #d6ddd4;border-radius:20px;padding:5px 12px;background:#fff;text-decoration:none}
article{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:12px;padding:26px 30px;margin:18px 0;overflow-wrap:anywhere;scroll-margin:16px}
h2{font-size:21px;line-height:1.5;margin:0 0 20px}h3{font-size:17px}p{margin:5px 0}.detail{color:#53655b;padding-left:12px;border-left:2px solid var(--line)}.space{height:16px}.meta,footer{font-size:12px;color:var(--muted)}footer{border-top:1px solid var(--line);margin-top:22px;padding-top:13px}a{color:#2d6657;text-underline-offset:3px}code{background:#eff3ed;padding:2px 5px;border-radius:4px}
@media(max-width:520px){main{padding:26px 14px}h1{font-size:32px}article{padding:20px 18px}h2{font-size:19px}}
@media print{body{background:#fff}main{padding:0;max-width:none}nav{display:none}article{break-inside:avoid;border:1px solid #ccc}a{color:inherit}}
</style><main><header><div class="eyebrow">DAILY BRIEF / MORNING NOTES</div><h1>오늘을 여는 짧은 정리</h1>
<p>핵심부터 읽고, 오늘 할 일을 정한 뒤, 관심 있는 소식으로.</p></header><nav aria-label="브리핑 섹션">''' + nav + '</nav>' + '\n'.join(cards) + '</main></html>\n'


def export_brief(embeds, format="text"):
    pages = ds.prepare_embeds(embeds)
    if format == "json":
        return json.dumps({"embeds": pages}, ensure_ascii=False, indent=2) + "\n"
    if format == "html":
        return html_preview(pages)
    if format == "markdown":
        return markdown(pages)
    return "\n\n".join(f"{page.get('title', '')}\n{page.get('description', '')}\n"
                        f"[기준] {page.get('footer', {}).get('text', '')}" for page in pages) + "\n"
