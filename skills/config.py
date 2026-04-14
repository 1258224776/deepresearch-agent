"""
Lightweight runtime config for skill governance.

Stage C (v2) only introduces global enabled/disabled state. Missing
entries default to enabled so local development does not break when new
skills are added before the config file is updated.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def get_skills_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "skills_config.yaml"


def load_skills_config() -> dict:
    path = get_skills_config_path()
    if not path.exists():
        return {"skills": {}}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {"skills": {}}
    return raw


def get_skill_state_map(skill_names: list[str] | None = None) -> dict[str, bool]:
    config = load_skills_config()
    raw_skills = config.get("skills", {})
    if not isinstance(raw_skills, dict):
        raw_skills = {}

    names = list(skill_names or raw_skills.keys())
    state_map: dict[str, bool] = {}

    for name in names:
        entry = raw_skills.get(name, {})
        if isinstance(entry, dict):
            enabled = entry.get("enabled", True)
        elif isinstance(entry, bool):
            enabled = entry
        else:
            enabled = True
        state_map[name] = bool(enabled)

    return state_map


def get_enabled_skill_names(skill_names: list[str] | None = None) -> list[str]:
    state_map = get_skill_state_map(skill_names)
    return [name for name, enabled in state_map.items() if enabled]
