"""
Profile-level skill filtering.

Profiles are a governance layer above the executable skill registry. They
let different entry points expose different subsets of enabled skills.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import load_skills_config


DEFAULT_SKILL_PROFILE = "react_default"

_PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "react_default": {
        "description": "Balanced interactive profile for the ReAct UI.",
        "allow": [
            "search",
            "search_multi",
            "search_docs",
            "search_company",
            "search_recent",
            "search_news",
            "search_site",
            "scrape",
            "extract_links",
            "extract",
            "summarize",
            "rag_retrieve",
        ],
    },
    "planner": {
        "description": "Bounded profile for planner sub-questions.",
        "allow": [
            "search",
            "search_multi",
            "search_docs",
            "search_company",
            "search_recent",
            "search_news",
            "scrape",
            "extract",
            "summarize",
            "rag_retrieve",
        ],
    },
    "api_safe": {
        "description": "Safer API profile without deep or recursive crawling.",
        "allow": [
            "search",
            "search_multi",
            "search_docs",
            "search_company",
            "search_recent",
            "search_news",
            "scrape",
            "extract",
            "summarize",
            "rag_retrieve",
        ],
    },
    "web_research_heavy": {
        "description": "Web-heavy profile with batch and deep crawling enabled.",
        "allow": [
            "search",
            "search_multi",
            "search_docs",
            "search_company",
            "search_site",
            "scrape",
            "extract_links",
            "extract",
            "summarize",
            "rag_retrieve",
            "search_recent",
            "search_news",
            "scrape_batch",
            "scrape_deep",
        ],
    },
}


@dataclass(frozen=True, slots=True)
class SkillProfile:
    name: str
    description: str
    allow: list[str]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def _filter_registered(allowed: list[str], skill_names: list[str]) -> list[str]:
    registered = set(skill_names)
    return [name for name in _dedupe_keep_order(allowed) if name in registered]


def get_skill_profiles(skill_names: list[str]) -> dict[str, SkillProfile]:
    raw_profiles = load_skills_config().get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raw_profiles = {}

    profile_names = list(_PROFILE_DEFAULTS.keys()) + [
        name for name in raw_profiles.keys()
        if name not in _PROFILE_DEFAULTS
    ]

    profiles: dict[str, SkillProfile] = {}
    for name in profile_names:
        default_entry = _PROFILE_DEFAULTS.get(name, {})
        raw_entry = raw_profiles.get(name, {})

        description = str(default_entry.get("description", "")).strip()
        allow = list(default_entry.get("allow", []))

        if isinstance(raw_entry, dict):
            raw_desc = raw_entry.get("description", "")
            if isinstance(raw_desc, str) and raw_desc.strip():
                description = raw_desc.strip()
            raw_allow = raw_entry.get("allow", allow)
            if isinstance(raw_allow, list):
                allow = raw_allow

        profiles[name] = SkillProfile(
            name=name,
            description=description,
            allow=_filter_registered(allow, skill_names),
        )

    return profiles


def get_profile_allowlist(profile_name: str | None, skill_names: list[str]) -> tuple[str, list[str]]:
    profiles = get_skill_profiles(skill_names)
    requested = (profile_name or DEFAULT_SKILL_PROFILE).strip() or DEFAULT_SKILL_PROFILE
    resolved = requested if requested in profiles else DEFAULT_SKILL_PROFILE

    if resolved not in profiles:
        return requested, list(skill_names)

    return resolved, list(profiles[resolved].allow)


def get_profile_metadata_list(skill_names: list[str]) -> list[dict]:
    profiles = get_skill_profiles(skill_names)
    return [
        {
            "name": profile.name,
            "description": profile.description,
            "allowed_skills": list(profile.allow),
            "allowed_count": len(profile.allow),
        }
        for profile in profiles.values()
    ]
