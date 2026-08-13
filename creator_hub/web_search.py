from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"


def _get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _extract_balanced_json(text: str, marker: str) -> dict[str, Any] | None:
    pos = text.find(marker)
    if pos < 0:
        return None
    brace = text.find("{", pos + len(marker))
    if brace < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(brace, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace:i+1])
                except Exception:
                    return None
    return None


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _text(node: Any) -> str:
    if isinstance(node, dict):
        if isinstance(node.get("simpleText"), str):
            return node["simpleText"]
        runs = node.get("runs")
        if isinstance(runs, list):
            return "".join(str(r.get("text") or "") for r in runs if isinstance(r, dict)).strip()
    return ""


def youtube_web_search(query: str, max_results: int = 100, timeout: int = 30) -> list[dict[str, Any]]:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgIQAQ%253D%253D"
    html = _get(url, timeout)
    data = _extract_balanced_json(html, "ytInitialData") or _extract_balanced_json(html, "var ytInitialData =")
    if not data:
        raise RuntimeError("无法解析 YouTube 网页搜索结果；可改用 API 搜索。")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in _walk(data):
        vr = node.get("videoRenderer") if isinstance(node, dict) else None
        if not isinstance(vr, dict):
            continue
        vid = str(vr.get("videoId") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        owner = vr.get("ownerText") or vr.get("shortBylineText") or {}
        channel_id = ""
        channel_url = ""
        runs = owner.get("runs") if isinstance(owner, dict) else None
        if isinstance(runs, list) and runs:
            nav = (runs[0].get("navigationEndpoint") or {}) if isinstance(runs[0], dict) else {}
            browse = nav.get("browseEndpoint") or {}
            channel_id = str(browse.get("browseId") or "")
            canonical = str(browse.get("canonicalBaseUrl") or "")
            if canonical:
                channel_url = "https://www.youtube.com" + canonical
            elif channel_id:
                channel_url = "https://www.youtube.com/channel/" + channel_id
        out.append({
            "video_id": vid,
            "video_url": "https://www.youtube.com/watch?v=" + vid,
            "title": _text(vr.get("title")),
            "published_at_text": _text(vr.get("publishedTimeText")),
            "raw_search_rank": len(out) + 1,
            "search_page": 1,
            "search_source": "youtube_web_search",
            "channel_id": channel_id,
            "channel_title": _text(owner),
            "channel_url": channel_url,
        })
        if len(out) >= max_results:
            break
    return out
