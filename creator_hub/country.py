from __future__ import annotations

import re
from typing import Any

from .geography import aliases_for_country

SOURCE_PRIORITY = {
    "youtube_about_popup": 4,
    "youtube_api": 3,
    "metadata_keyword": 2,
    "language_hint": 1,
    "unknown": 0,
}

COUNTRY_CONFIG: dict[str, dict[str, Any]] = {
    "PH": {"aliases": ["philippines", "philippine", "filipino", "pinoy", "tagalog", "菲律宾", "菲律賓"], "lang": r"^(tl|fil)(-|$)|^(en)(-|$)", "allow_en": True},
    "ID": {"aliases": ["indonesia", "indonesian", "indo", "bahasa indonesia", "印度尼西亚", "印尼", "印度尼西亞"], "lang": r"^(id)(-|$)"},
    "TH": {"aliases": ["thailand", "thai", "ประเทศไทย", "泰国", "泰國"], "lang": r"^(th)(-|$)"},
    "BR": {"aliases": ["brazil", "brasil", "brazilian", "portuguese brazil", "巴西"], "lang": r"^(pt-br|pt)(-|$)"},
    "SG": {"aliases": ["singapore", "singaporean", "新加坡"]},
    "MY": {"aliases": ["malaysia", "malaysian", "bahasa melayu", "马来西亚", "馬來西亞"], "lang": r"^(ms)(-|$)"},
    "VN": {"aliases": ["vietnam", "vietnamese", "越南"], "lang": r"^(vi)(-|$)"},
    "KR": {"aliases": ["korea", "south korea", "korean", "韩国", "韓國"], "lang": r"^(ko)(-|$)"},
    "JP": {"aliases": ["japan", "japanese", "日本"], "lang": r"^(ja)(-|$)"},
    "TW": {"aliases": ["taiwan", "taiwanese", "台湾", "臺灣"], "lang": r"^(zh-tw)(-|$)|^(zh-hant)(-|$)"},
    "US": {"aliases": ["united states", "usa", "u.s.", "america", "american", "美国", "美國"]},
    "ES": {"aliases": ["spain", "spanish", "西班牙"]},
    "UA": {"aliases": ["ukraine", "ukrainian", "乌克兰", "烏克蘭"]},
}


def metadata_evidence(text: str, target: str) -> bool:
    code=target.upper()
    cfg = COUNTRY_CONFIG.get(code) or {}
    low = (text or "").lower()
    aliases=list(cfg.get("aliases", [])) + aliases_for_country(code)
    return any(a and a.lower() in low for a in aliases)


def language_evidence(language: str, target: str, conflicting_country: str | None = None) -> bool:
    cfg = COUNTRY_CONFIG.get(target.upper())
    if not cfg:
        return False
    lang = language or ""
    if cfg.get("lang") and re.search(cfg["lang"], lang, re.I):
        return True
    if cfg.get("allow_en") and re.search(r"^(en)(-|$)", lang, re.I) and not conflicting_country:
        return True
    return False


def best_country(*, api_country: str | None, about_country: str | None = None, metadata_text: str = "", language: str = "", target_country: str | None = None) -> dict[str, Any]:
    evidence: list[dict[str, str]] = []
    if about_country:
        evidence.append({"country": about_country.upper(), "source": "youtube_about_popup"})
    if api_country:
        evidence.append({"country": api_country.upper(), "source": "youtube_api"})
    if target_country:
        t = target_country.upper()
        if metadata_evidence(metadata_text, t):
            evidence.append({"country": t, "source": "metadata_keyword"})
        if language_evidence(language, t, api_country if api_country and api_country.upper() != t else None):
            evidence.append({"country": t, "source": "language_hint"})
    evidence.sort(key=lambda x: SOURCE_PRIORITY.get(x["source"], 0), reverse=True)
    best = evidence[0] if evidence else {"country": "", "source": "unknown"}
    return {"country": best["country"], "source": best["source"], "evidence": evidence}


def extract_country_from_text(text: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not normalized:
        return None, None
    for code, cfg in COUNTRY_CONFIG.items():
        for alias in cfg.get("aliases", []):
            if alias.lower() in normalized:
                return code, "youtube_about_popup"
    return None, None
