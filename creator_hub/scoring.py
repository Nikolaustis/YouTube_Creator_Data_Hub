from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(x, hi))


def days_since_publish(published_at: str | None, now: datetime | None = None) -> int:
    if not published_at:
        return 1
    try:
        d = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        n = now or datetime.now(timezone.utc)
        return max(1, int(((n - d).total_seconds() + 86399) // 86400))
    except Exception:
        return 1


def subscriber_fit(subscribers: int) -> float:
    if 3000 <= subscribers < 8000:
        return 0.7
    if 8000 <= subscribers <= 30000:
        return 1.0
    if 30000 < subscribers <= 50000:
        return 0.8
    if 50000 < subscribers <= 100000:
        return 0.5
    return 0.0


def opportunity_tier(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def pre_score(*, views: int = 0, likes: int = 0, comments: int = 0, subscribers: int = 0, published_at: str | None = None) -> dict[str, Any]:
    days = days_since_publish(published_at)
    engagement = (likes + comments * 2) / max(views, 1)
    comment_rate = comments / max(views, 1)
    view_sub_ratio = views / max(subscribers, 1)
    relative_velocity = views / max(days, 1) / max(subscribers, 1)
    s_sub = subscriber_fit(subscribers)
    s_vs = clamp(view_sub_ratio / 0.4, 0, 1)
    s_eng = clamp(engagement / 0.05, 0, 1)
    s_com = clamp(comment_rate / 0.005, 0, 1)
    s_vel = clamp(relative_velocity / 0.02, 0, 1)
    score = 30 * s_sub + 30 * s_vs + 20 * s_eng + 10 * s_com + 10 * s_vel
    return {
        "days_since_publish": days,
        "engagement_rate": engagement,
        "comment_rate": comment_rate,
        "view_sub_ratio": view_sub_ratio,
        "relative_velocity": relative_velocity,
        "sub_fit_score": s_sub,
        "view_sub_score": s_vs,
        "engagement_score": s_eng,
        "comment_score": s_com,
        "relative_velocity_score": s_vel,
        "pre_score": score,
        "opportunity_tier": opportunity_tier(score),
    }


def contactability_score(*, email: bool, social: bool, website: bool) -> int:
    if email:
        return 100
    if social:
        return 70
    if website:
        return 50
    return 0


def outreach_priority(final_score: float) -> str:
    if final_score >= 85:
        return "P1"
    if final_score >= 70:
        return "P2"
    if final_score >= 55:
        return "P3"
    return "P4"


def final_score(*, pre_score_value: float, contactability_score_value: float, content_fit_score: float, audience_fit_score: float, brand_safety_score: float) -> dict[str, Any]:
    """Deterministic backend-owned final-score formula.

    The Data Hub does not fabricate content/audience/brand-safety inputs. This helper is
    available for a later deep-analysis provider; the discovery UI currently shows the
    deterministic pre-score until those three inputs actually exist.
    """
    breakdown = {
        "pre_score_norm": clamp(pre_score_value / 100, 0, 1),
        "contactability_norm": clamp(contactability_score_value / 100, 0, 1),
        "content_fit_norm": clamp(content_fit_score / 100, 0, 1),
        "audience_fit_norm": clamp(audience_fit_score / 100, 0, 1),
        "brand_safety_norm": clamp(brand_safety_score / 100, 0, 1),
    }
    score = 100 * (
        0.4 * breakdown["pre_score_norm"]
        + 0.2 * breakdown["contactability_norm"]
        + 0.2 * breakdown["content_fit_norm"]
        + 0.1 * breakdown["audience_fit_norm"]
        + 0.1 * breakdown["brand_safety_norm"]
    )
    return {"final_score": score, "final_score_breakdown": breakdown, "outreach_priority": outreach_priority(score)}
