"""
Lightweight route smoke tests for Stage C.

Usage:
    python scripts/validate_routes.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills import BUILTIN_SKILL_REGISTRY
from skills.config import get_enabled_skill_names
from skills.profiles import get_profile_allowlist
from skills.router import build_route_decision
from report import QuestionType


@dataclass(frozen=True)
class RouteCase:
    name: str
    question: str
    qtype: QuestionType
    profile: str
    expect_starter: str
    expect_preferred: tuple[str, ...] = ()
    expect_signals: tuple[str, ...] = ()


CASES: tuple[RouteCase, ...] = (
    RouteCase(
        name="docs_api",
        question="OpenAI Responses API background mode how to use",
        qtype=QuestionType.RESEARCH,
        profile="react_default",
        expect_starter="search_docs",
        expect_preferred=("search_docs", "search_site"),
        expect_signals=("docs",),
    ),
    RouteCase(
        name="company_update",
        question="Nvidia earnings investor relations update",
        qtype=QuestionType.FINANCIAL,
        profile="web_research_heavy",
        expect_starter="search_company",
        expect_preferred=("search_company", "search_recent", "search_news"),
        expect_signals=("company", "news"),
    ),
    RouteCase(
        name="recent_news",
        question="OpenAI latest announcement this month",
        qtype=QuestionType.TREND,
        profile="api_safe",
        expect_starter="search_news",
        expect_preferred=("search_news", "search_recent"),
        expect_signals=("news",),
    ),
)


def main() -> int:
    all_skills = BUILTIN_SKILL_REGISTRY.names()
    enabled_skills = get_enabled_skill_names(all_skills)
    failures: list[str] = []

    for case in CASES:
        resolved_profile, visible_skills = get_profile_allowlist(case.profile, enabled_skills)
        decision = build_route_decision(
            case.qtype,
            visible_skills,
            question=case.question,
            profile_name=resolved_profile,
        )

        print(f"[{case.name}] type={decision.qtype.value} starter={decision.starter}")
        print(f"  allowed={decision.allowed}")
        print(f"  preferred={decision.preferred}")
        print(f"  signals={decision.signals}")

        if decision.starter != case.expect_starter:
            failures.append(
                f"{case.name}: expected starter {case.expect_starter}, got {decision.starter}"
            )

        for expected in case.expect_preferred:
            if expected not in decision.preferred:
                failures.append(
                    f"{case.name}: expected preferred skill {expected}, got {decision.preferred}"
                )

        for expected in case.expect_signals:
            if expected not in decision.signals:
                failures.append(
                    f"{case.name}: expected signal {expected}, got {decision.signals}"
                )

    if failures:
        print("\nRoute validation failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("\nRoute validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
