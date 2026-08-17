from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"


def _request(url: str, *, timeout: int = 30, data: bytes | None = None, headers: dict[str, str] | None = None) -> str:
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
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
                    return json.loads(text[brace:i + 1])
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


def _renderer_to_row(vr: dict[str, Any], rank: int, page: int) -> dict[str, Any] | None:
    vid = str(vr.get("videoId") or "")
    if not vid:
        return None
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
    return {
        "video_id": vid,
        "video_url": "https://www.youtube.com/watch?v=" + vid,
        "title": _text(vr.get("title")),
        "published_at_text": _text(vr.get("publishedTimeText")),
        "raw_search_rank": rank,
        "search_page": page,
        "search_source": "youtube_web_search",
        "channel_id": channel_id,
        "channel_title": _text(owner),
        "channel_url": channel_url,
    }


def _collect_videos(data: dict[str, Any], out: list[dict[str, Any]], seen: set[str], max_results: int, page: int) -> None:
    for node in _walk(data):
        vr = node.get("videoRenderer") if isinstance(node, dict) else None
        if not isinstance(vr, dict):
            continue
        vid = str(vr.get("videoId") or "")
        if not vid or vid in seen:
            continue
        row = _renderer_to_row(vr, len(out) + 1, page)
        if row:
            seen.add(vid)
            out.append(row)
        if len(out) >= max_results:
            return


def _find_continuation(data: dict[str, Any]) -> str | None:
    # YouTube has used several equivalent continuation wrappers over time.
    for node in _walk(data):
        if not isinstance(node, dict):
            continue
        cmd = node.get("continuationCommand")
        if isinstance(cmd, dict) and cmd.get("token"):
            return str(cmd["token"])
        ep = node.get("continuationEndpoint")
        if isinstance(ep, dict):
            cmd = ep.get("continuationCommand") or {}
            if isinstance(cmd, dict) and cmd.get("token"):
                return str(cmd["token"])
    return None


def _innertube_context(cfg: dict[str, Any], language: str | None, region: str | None) -> dict[str, Any]:
    client = dict((cfg.get("INNERTUBE_CONTEXT") or {}).get("client") or {})
    # Keep only JSON-serializable public web client values; provide safe defaults if YouTube changes its page config.
    client.setdefault("clientName", "WEB")
    client.setdefault("clientVersion", str(cfg.get("INNERTUBE_CLIENT_VERSION") or "2.20260801.00.00"))
    if language:
        client["hl"] = language
    else:
        client.setdefault("hl", "en")
    if region:
        client["gl"] = region.upper()
    return {"client": client}


def youtube_web_search(
    query: str,
    max_results: int = 100,
    timeout: int = 30,
    *,
    region: str | None = None,
    language: str | None = None,
    max_continuations: int = 20,
) -> list[dict[str, Any]]:
    """Search YouTube's public web result page and follow continuation tokens.

    This path does not spend search.list quota. Metric/channel hydration is still performed by
    the Data Hub after discovery. If YouTube changes continuation internals, the initial page
    remains usable and the caller can fall back to API search.
    """
    max_results = max(1, min(int(max_results), 500))
    params = {"search_query": query, "sp": "EgIQAQ=="}
    if region:
        params["gl"] = region.upper()
    if language:
        params["hl"] = language
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(params)
    html = _request(url, timeout=timeout)
    data = _extract_balanced_json(html, "ytInitialData") or _extract_balanced_json(html, "var ytInitialData =")
    if not data:
        raise RuntimeError("无法解析 YouTube 网页搜索结果；可改用 API 搜索。")

    cfg = _extract_balanced_json(html, "ytcfg.set(") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    _collect_videos(data, out, seen, max_results, 1)
    if len(out) >= max_results:
        return out[:max_results]

    api_key = str(cfg.get("INNERTUBE_API_KEY") or "")
    continuation = _find_continuation(data)
    if not api_key or not continuation:
        return out[:max_results]

    endpoint = "https://www.youtube.com/youtubei/v1/search?key=" + urllib.parse.quote(api_key)
    client_name = str(cfg.get("INNERTUBE_CONTEXT_CLIENT_NAME") or "1")
    client_version = str(cfg.get("INNERTUBE_CLIENT_VERSION") or "")
    headers = {"Content-Type": "application/json", "X-YouTube-Client-Name": client_name}
    if client_version:
        headers["X-YouTube-Client-Version"] = client_version

    page = 1
    used_tokens: set[str] = set()
    while continuation and len(out) < max_results and page <= max_continuations:
        if continuation in used_tokens:
            break
        used_tokens.add(continuation)
        payload = {
            "context": _innertube_context(cfg, language, region),
            "continuation": continuation,
        }
        try:
            raw = _request(endpoint, timeout=timeout, data=json.dumps(payload).encode("utf-8"), headers=headers)
            nxt = json.loads(raw)
        except Exception:
            break
        page += 1
        before = len(out)
        _collect_videos(nxt, out, seen, max_results, page)
        continuation = _find_continuation(nxt)
        if len(out) == before and not continuation:
            break
    return out[:max_results]
