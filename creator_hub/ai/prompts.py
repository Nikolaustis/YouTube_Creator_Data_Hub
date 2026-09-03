from __future__ import annotations

import json
from typing import Any

PROMPT_VERSIONS = {
    "creator_brief": "creator-brief-v1",
    "creator_compare": "creator-compare-v1",
    "query_planner": "query-planner-v9",
    "ask_hub": "ask-hub-plan-v2",
    "weekly_brief": "weekly-brief-v3",
}

BASE_RULES = """You are the read-only AI copilot for a local YouTube Creator Intelligence database.
Use ONLY the supplied structured facts. Never invent revenue, contracts, demographics, private contact details, or facts not present in the input.
Do not modify data. Keep deterministic system scores and AI judgments separate. Answer in concise Simplified Chinese unless the requested query language requires otherwise.
When giving a judgment, ground it in named evidence fields and data timestamps."""


def _payload(label: str, data: Any) -> str:
    return f"\n\n{label}:\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def creator_brief(context: dict[str, Any]) -> str:
    return BASE_RULES + "\nCreate an evidence-grounded Creator Brief: positioning, recent performance, Workspace brand/relationship context, opportunity, risks, and recommended next step." + _payload("CREATOR_CONTEXT", context)


def creator_compare(contexts: list[dict[str, Any]]) -> str:
    return BASE_RULES + "\nCompare the supplied creators for outreach priority. Rank only these creators. Explain tradeoffs and cite evidence keys from each context." + _payload("CREATORS", contexts)


def query_planner(query: str, language: str, objective: str, query_packs: dict[str, Any], max_queries: int = 12) -> str:
    return BASE_RULES + f"""
Plan a high-recall YouTube Creator discovery search for base topic: {query!r}. Language: {language}. User search requirements: {objective}. Query budget: AT MOST {max_queries} executable queries total.
Return BOTH (1) the final prioritized queries that should actually be executed within that budget and (2) explicit fit_criteria that the local system can apply after discovery. Do not output a large brainstorming list for another layer to re-compose. Do not leave important requirements only in strategy prose.
Rules:
- queries: return no more than {max_queries} FINAL executable YouTube search phrases, already ranked by expected information gain. Cover every meaningful operational concept in the requirements when feasible (for example AFK, auto farm, multi-account, multi-instance, alt accounts/alts, multi-client, overnight, farm while sleeping, 24/7). Avoid duplicate wording such as repeating the base topic twice.
- fit_criteria.search_concepts: short concepts that MUST receive query coverage.
- fit_criteria.preferred_terms: title-level evidence terms that should appear in the best hit or recent uploads for a candidate to satisfy the user's stated content/use-case requirement. Do not treat them as proof of cloud-phone usage; they are only Creator-fit evidence.
- fit_criteria.continuity_terms: terms used to measure whether the creator repeatedly produces the desired kind of content. The local system first establishes channel-level base-topic context; individual continuity uploads do NOT need to repeat the full base-topic name in every title.
- fit_criteria.exclude_terms: only explicit negative requirements; otherwise return [].
- subscriber_min/subscriber_max: use numeric hard constraints only when the user expresses a size requirement. If the wording is vague, use null; the local system may apply a documented default heuristic.
- require_topic_match should normally be true so unrelated search noise is filtered.
- prefer_long_term should be true when the user asks for long-term/repeated/ongoing production. The local system will treat that as a continuity gate, not merely a bonus.
- For Creator sourcing, official cloud-phone brand accounts, official game/developer channels, and channels primarily focused on cheats/scripts/exploits are normally unsuitable and will be removed by deterministic brand-safety rules unless the user explicitly asks to include them.
The selected query language is also treated by the local system as the desired dominant Creator content language when sufficient recent-title evidence exists. The local system will immediately execute the queries through YouTube API, then sample recent uploads and apply the fit criteria. Do not claim you executed anything yourself. Use Query Pack vocabulary as guidance, not as a requirement.""" + _payload("QUERY_PACKS", query_packs)

def ask_hub(question: str, field_catalog: dict[str, Any]) -> str:
    return BASE_RULES + f"\nTranslate the user's question into a SAFE, READ-ONLY Creator query plan using only fields/operators in FIELD_CATALOG. Do not answer from memory. The local database will execute your plan. Set result_limit to null unless the user explicitly asks for a Top N / exact maximum number of results. Dashboard pagination is separate and is always handled locally. Question: {question}" + _payload("FIELD_CATALOG", field_catalog)


def weekly_brief(context: dict[str, Any]) -> str:
    return BASE_RULES + "\nCreate the explanatory prose for a seven-day Creator Intelligence Brief. The deterministic headline and all numeric KPI values in WEEK_CONTEXT are authoritative and MUST NOT be changed, recomputed, rounded to different counts, or relabeled. Do not call current-state workflow counts changes. Explain discoveries, commercial snapshot movement, monitoring/data-health risks, recent AI sourcing pools, and prioritized actions using only supplied facts. Use the supplied deterministic_headline verbatim as headline." + _payload("WEEK_CONTEXT", context)
