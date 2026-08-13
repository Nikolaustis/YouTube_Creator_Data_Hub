from __future__ import annotations

import html as htmlmod
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .country import extract_country_from_text
from .scoring import contactability_score
from .util import now_utc
from .web_search import UA

SOCIAL_HOSTS = {
    "instagram.com", "x.com", "twitter.com", "tiktok.com", "facebook.com", "threads.net",
    "linkedin.com", "discord.gg", "discord.com", "twitch.tv", "patreon.com"
}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.text: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
    def handle_data(self, data):
        if data and data.strip():
            self.text.append(data.strip())


def _normalize_link(href: str) -> str:
    href = htmlmod.unescape(href)
    if href.startswith("/redirect?"):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        return (qs.get("q") or qs.get("url") or [href])[0]
    if href.startswith("http"):
        return href
    return ""


def scrape_public_channel_contact(channel_url: str, timeout: int = 30) -> dict[str, Any]:
    base = channel_url.rstrip("/")
    about_url = base + "/about"
    req = urllib.request.Request(about_url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    parser = LinkParser(); parser.feed(raw)
    body = "\n".join(parser.text) + "\n" + re.sub(r"<[^>]+>", " ", raw)
    emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", body, re.I)))
    links = []
    for href in parser.links:
        u = _normalize_link(href)
        if u and u not in links:
            links.append(u)
    social, websites = [], []
    for u in links:
        try:
            host = urllib.parse.urlparse(u).hostname or ""
            host = host.lower().removeprefix("www.")
        except Exception:
            continue
        if host in {"youtube.com", "youtu.be"}:
            continue
        if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
            social.append(u)
        else:
            websites.append(u)
    country, source = extract_country_from_text(body)
    gated = bool(re.search(r"view email address|business email|captcha|recaptcha|verify", body, re.I)) and not emails
    status = "found" if emails or social or websites else ("gated" if gated else "not_found")
    return {
        "public_email": emails[0] if emails else "",
        "social_links": social[:20],
        "website_url": websites[0] if websites else "",
        "about_page_country": country or "",
        "about_page_country_source": source or "",
        "contact_status": status,
        "contactability_score": contactability_score(email=bool(emails), social=bool(social), website=bool(websites)),
        "manual_action_required": gated,
        "scraped_at": now_utc(),
        "about_url": about_url,
    }
