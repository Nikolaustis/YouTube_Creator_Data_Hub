from __future__ import annotations

from typing import Any, Iterable

from .util import extract_urls, host_matches, host_of, now_utc


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _text_has(text: str, terms: Iterable[str]) -> bool:
    low = (text or '').lower()
    return any(_clean(term).lower() in low for term in terms if _clean(term))


def _matching_terms(text: str, terms: Iterable[str]) -> list[str]:
    low = (text or '').lower()
    out: list[str] = []
    for term in terms:
        clean = _clean(term)
        if clean and clean.lower() in low and clean not in out:
            out.append(clean)
    return out


def _brand_evidence(title: str, description: str, tags: list[str], urls: list[str], brand: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    aliases = brand.get('aliases', [])
    title_hit = _text_has(title, aliases)
    desc_hit = _text_has(description, aliases)
    tags_hit = _text_has(' '.join(tags), aliases)
    classification = cfg.get('classification') or {}
    entity_terms = classification.get('cloud_entity_terms') or classification.get('cloud_context_terms') or cfg.get('cloud_context_terms') or []
    entity_context = _text_has(f"{title}\n{description}\n{' '.join(tags)}", entity_terms)
    cta_terms = classification.get('cta_terms') or []
    product_link_terms = list(classification.get('product_link_terms') or []) + list(brand.get('web_patterns') or []) + list(brand.get('referral_patterns') or [])
    official_links = [u for u in urls if host_matches(host_of(u), brand.get('official_domains', []))]
    known_short = [u for u in urls if u.lower() in {_clean(x).lower() for x in brand.get('known_short_links', [])}]
    official_product_link = bool(official_links) and (
        _text_has(' '.join(official_links), product_link_terms) or _text_has(description, cta_terms)
    )
    evidence: list[str] = []
    confidence = 'none'

    # Deterministic public-metadata evidence. Generic use-case terms such as AFK or
    # Auto Farm are intentionally NOT cloud-phone evidence; they are discovery signals.
    if title_hit and (brand.get('role') == 'target' or entity_context or official_links):
        confidence = 'confirmed'
        evidence.append('brand_alias_in_title')
    if desc_hit and (official_links or known_short):
        confidence = 'confirmed'
        evidence.append('brand_alias_with_brand_link')
    elif desc_hit and entity_context and confidence != 'confirmed':
        confidence = 'probable'
        evidence.append('brand_alias_with_cloud_entity_context')
    if official_product_link and confidence == 'none':
        confidence = 'probable'
        evidence.append('official_domain_with_product_context')
    elif official_links and entity_context and confidence == 'none':
        confidence = 'probable'
        evidence.append('official_domain_with_cloud_entity_context')
    if known_short and (desc_hit or entity_context) and confidence == 'none':
        confidence = 'probable'
        evidence.append('known_short_link_with_context')
    if tags_hit and confidence == 'none':
        confidence = 'review'
        evidence.append('brand_alias_in_tags_only')
    if official_links and confidence == 'none':
        confidence = 'review'
        evidence.append('bare_official_domain')

    return {
        'brand_key': brand.get('key', ''),
        'role': brand.get('role', 'competitor'),
        'confidence': confidence,
        'evidence': evidence,
    }


def suggest_label(video: dict[str, Any], brand_cfg: dict[str, Any]) -> dict[str, Any]:
    """Classify a video from public YouTube metadata.

    This is the system's deterministic classification layer. It is not a human
    confirmation workflow. Manual labels, when present, are optional corrections
    stored separately in video_labels.

    Important distinction: discovery/use-case terms (AFK, Auto Farm, 24/7,
    multi-instance) never establish cloud-phone content by themselves.
    """
    title = video.get('title') or ''
    description = video.get('description') or ''
    tags = [str(x) for x in (video.get('tags') or []) if str(x).strip()]
    full_text = f"{title}\n{description}\n{' '.join(tags)}"
    urls = extract_urls(description)
    evidences = [_brand_evidence(title, description, tags, urls, b, brand_cfg) for b in brand_cfg.get('brands', [])]
    relevant = [e for e in evidences if e['confidence'] in {'confirmed', 'probable', 'review'}]
    strong = [e for e in relevant if e['confidence'] in {'confirmed', 'probable'}]
    target_strong = [e for e in strong if e['role'] == 'target']
    competitor_strong = [e for e in strong if e['role'] == 'competitor']
    strong_brand_keys = {e['brand_key'] for e in strong if e.get('brand_key')}
    classification = brand_cfg.get('classification') or {}
    entity_terms = classification.get('cloud_entity_terms') or classification.get('cloud_context_terms') or brand_cfg.get('cloud_context_terms') or []
    use_case_terms = classification.get('use_case_terms') or []
    entity_hits = _matching_terms(full_text, entity_terms)
    use_case_hits = _matching_terms(full_text, use_case_terms)
    cloud_entity_context = bool(entity_hits)

    # Multi-brand means multiple strongly identified cloud-phone brands, regardless
    # of whether UgPhone is one of them.
    if len(strong_brand_keys) >= 2:
        role = 'multi_brand'
    elif target_strong:
        role = 'ugphone'
    elif competitor_strong:
        role = 'competitor'
    elif cloud_entity_context:
        role = 'other_cloud_phone'
    elif relevant:
        # Weak evidence about a KNOWN brand is not evidence for an unknown/other brand.
        role = 'pending'
    else:
        role = 'daily'

    rank = {'none': 0, 'review': 1, 'probable': 2, 'confirmed': 3}
    best = max((e['confidence'] for e in relevant), key=lambda x: rank[x], default='none')
    confidence = {'confirmed': 'high', 'probable': 'medium', 'review': 'review', 'none': 'low'}[best]
    evidence = [f"{e['brand_key']}:{ev}" for e in relevant for ev in e['evidence']]

    if role == 'other_cloud_phone':
        confidence = 'medium' if best == 'none' else confidence
        evidence.extend(f"cloud_entity_term:{term}" for term in entity_hits)
    elif role == 'daily' and use_case_hits:
        # Keep an audit trace explaining why a tempting discovery signal was ignored.
        evidence.extend(f"use_case_not_cloud_evidence:{term}" for term in use_case_hits)
    elif role == 'daily' and not evidence:
        evidence = ['no_brand_or_cloud_entity_evidence_in_public_metadata']

    return {
        'video_id': video.get('video_id'),
        'suggested_role': role,
        'brands': sorted({e['brand_key'] for e in relevant}),
        'confidence': confidence,
        'evidence': evidence,
        'generated_at': now_utc(),
        'rule_version': brand_cfg.get('rule_version', ''),
    }
