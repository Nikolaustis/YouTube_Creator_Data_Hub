from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GEO_PATH = ROOT / 'config' / 'geography.json'

@lru_cache(maxsize=1)
def geography() -> dict[str, Any]:
    return json.loads(GEO_PATH.read_text(encoding='utf-8'))

def country_by_code(code: str | None) -> dict[str, Any] | None:
    c=(code or '').upper().strip()
    if not c:return None
    for row in geography().get('countries',[]):
        if row.get('code')==c:return row
    return None

def group_codes(group_id: str | None) -> set[str]:
    g=(group_id or '').strip()
    if not g:return set()
    return {x['code'] for x in geography().get('countries',[]) if x.get('group')==g}

def resolve_country_query(value: str | None) -> dict[str, Any] | None:
    q=(value or '').strip()
    if not q:return None
    qlow=q.casefold()
    for row in geography().get('countries',[]):
        vals={str(row.get('code') or '').casefold(),str(row.get('name_zh') or '').casefold(),str(row.get('name_en') or '').casefold()}
        if qlow in vals:return row
    return None

def aliases_for_country(code: str | None) -> list[str]:
    row=country_by_code(code)
    if not row:return []
    return [str(row.get('name_zh') or ''),str(row.get('name_en') or '')]
