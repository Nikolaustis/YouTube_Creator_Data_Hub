from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

UTC = dt.timezone.utc
ISO_DURATION_RE = re.compile(r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$")
URL_RE = re.compile(r"https?://[^\s<>\]\[(){}\"']+|www\.[^\s<>\]\[(){}\"']+", re.I)


def now_utc() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_utc() -> str:
    return dt.datetime.now(UTC).date().isoformat()


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def parse_duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    m = ISO_DURATION_RE.match(value)
    if not m:
        return None
    parts = {k: int(v or 0) for k, v in m.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def extract_urls(text: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?。，；：！？)")
        if u.startswith("www."):
            u = "https://" + u
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def host_matches(host: str, domains: Iterable[str]) -> bool:
    h = host.lower()
    return any(h == d.lower() or h.endswith("." + d.lower()) for d in domains if d)


def video_id_from_ref(ref: str) -> str | None:
    s = ref.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    try:
        p = urlparse(s)
    except Exception:
        return None
    host = p.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        vid = p.path.strip("/").split("/")[0]
        return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or "") else None
    if "youtube.com" in host:
        if p.path == "/watch":
            vid = parse_qs(p.query).get("v", [None])[0]
            return vid if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None
        m = re.search(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", p.path)
        if m:
            return m.group(1)
    return None


def channel_id_from_ref(ref: str) -> str | None:
    s = ref.strip()
    if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", s):
        return s
    m = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", s)
    return m.group(1) if m else None


def handle_from_ref(ref: str) -> str | None:
    s = ref.strip()
    if re.fullmatch(r"@[A-Za-z0-9._-]+", s):
        return s
    m = re.search(r"youtube\.com/(@[A-Za-z0-9._-]+)", s, re.I)
    return m.group(1) if m else None


def username_from_ref(ref: str) -> str | None:
    m = re.search(r"youtube\.com/user/([^/?#]+)", ref, re.I)
    return m.group(1) if m else None


def custom_path_from_ref(ref: str) -> str | None:
    m = re.search(r"youtube\.com/(?:c/)?([^/?#]+)", ref, re.I)
    if not m:
        return None
    val = m.group(1)
    if val.lower() in {"watch", "channel", "user", "shorts", "live"} or val.startswith("@"): return None
    return val


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:120] or "item"


def load_json(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def dump_json(path: str | Path, value: Any, *, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=indent), encoding="utf-8")


def fmt_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]
