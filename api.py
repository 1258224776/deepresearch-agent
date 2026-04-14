"""
FastAPI wrapper for the DeepResearch Agent.

Exposes the ReAct workflow over HTTP so external tools can consume
the final report, step trace, structured observations, and references.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_loop import run_agent
from skills import BUILTIN_SKILL_REGISTRY
from skills.config import get_enabled_skill_names, get_skill_state_map
from skills.profiles import (
    DEFAULT_SKILL_PROFILE,
    get_profile_allowlist,
    get_profile_metadata_list,
    get_skill_profiles,
)
from skills.router import preview_route


app = FastAPI(
    title="DeepResearch Agent API",
    description=(
        "AI research agent with search, scraping, local RAG, structured "
        "observations, cited final reports, and inspectable skill metadata."
    ),
    version="1.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    question: str = Field(..., description="Research question")
    engine: str = Field(
        default="",
        description='Engine preset: "deep", "fast", or empty for auto.',
    )
    max_steps: int = Field(
        default=8,
        ge=3,
        le=15,
        description="Maximum number of ReAct steps",
    )
    skill_profile: str = Field(
        default="api_safe",
        description=(
            'Skill exposure profile. Examples: "api_safe", "react_default", '
            '"planner", "web_research_heavy".'
        ),
    )


class SourceInfo(BaseModel):
    url: str = ""
    title: str = ""
    snippet: str = ""


class StepInfo(BaseModel):
    thought: str = ""
    tool: str = ""
    args: dict = Field(default_factory=dict)
    observation: str = ""
    sources: list[SourceInfo] = Field(default_factory=list)
    cite_ids: list[int] = Field(default_factory=list)
    error_type: str | None = None


class ObservationInfo(BaseModel):
    content: str = ""
    sources: list[SourceInfo] = Field(default_factory=list)
    tool: str = ""
    args: dict = Field(default_factory=dict)
    cite_ids: list[int] = Field(default_factory=list)


class ReferenceInfo(BaseModel):
    cite_id: int
    url: str
    title: str = ""
    snippet: str = ""


class RunResponse(BaseModel):
    answer: str = Field(..., description="Final markdown report")
    steps: list[StepInfo] = Field(default_factory=list, description="Per-step trace")
    observations: list[ObservationInfo] = Field(
        default_factory=list,
        description="Structured observations collected during execution",
    )
    references: list[ReferenceInfo] = Field(
        default_factory=list,
        description="Deduplicated references derived from cite ids",
    )
    references_md: str = Field(
        default="",
        description="Markdown reference section for direct rendering",
    )
    skill_profile: str = Field(
        default=DEFAULT_SKILL_PROFILE,
        description="Resolved skill profile used during execution",
    )
    step_count: int = Field(..., description="Actual number of executed steps")
    error: str | None = Field(default=None, description="Execution error, if any")


class SkillInfo(BaseModel):
    name: str
    description: str
    category: str
    required_args: list[str] = Field(default_factory=list)
    optional_args: list[str] = Field(default_factory=list)
    args_desc: dict[str, str] = Field(default_factory=dict)
    returns_sources: bool = True
    enabled: bool = True


class SkillProfileInfo(BaseModel):
    name: str
    description: str = ""
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_count: int = 0


class SkillCatalogResponse(BaseModel):
    total_skills: int = Field(..., description="Number of registered built-in skills")
    enabled_skills: int = Field(..., description="Number of enabled built-in skills")
    categories: list[str] = Field(default_factory=list, description="Skill categories")
    profiles: list[SkillProfileInfo] = Field(default_factory=list, description="Available skill profiles")
    skills: list[SkillInfo] = Field(default_factory=list, description="Available built-in skills")


class RoutePreviewRequest(BaseModel):
    question: str = Field(..., description="Question to preview routing for")
    engine: str = Field(
        default="",
        description='Engine preset: "deep", "fast", or empty for auto.',
    )
    skill_profile: str = Field(
        default=DEFAULT_SKILL_PROFILE,
        description="Skill exposure profile used to preview visible skills.",
    )


class RoutePreviewResponse(BaseModel):
    question: str
    question_type: str
    skill_profile: str
    allowed_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    discouraged_skills: list[str] = Field(default_factory=list)
    starter: str = ""
    reasons: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


def _build_references(observations: list[dict]) -> tuple[list[ReferenceInfo], str]:
    ref_map: dict[int, ReferenceInfo] = {}

    for obs in observations:
        sources = obs.get("sources", []) or []
        cite_ids = obs.get("cite_ids", []) or []

        for idx, source in enumerate(sources):
            cite_id = cite_ids[idx] if idx < len(cite_ids) else None
            url = source.get("url", "")
            if not cite_id or not url or cite_id in ref_map:
                continue

            ref_map[cite_id] = ReferenceInfo(
                cite_id=cite_id,
                url=url,
                title=source.get("title", ""),
                snippet=source.get("snippet", ""),
            )

    references = [ref_map[key] for key in sorted(ref_map)]
    if not references:
        return [], ""

    refs_md = "## References\n\n" + "\n".join(
        f"{ref.cite_id}. [{ref.title or ref.url}]({ref.url})"
        for ref in references
    )
    return references, refs_md


def _build_skill_catalog() -> SkillCatalogResponse:
    enabled_map = get_skill_state_map(BUILTIN_SKILL_REGISTRY.names())
    skills_raw = BUILTIN_SKILL_REGISTRY.as_metadata_list(enabled_map=enabled_map)
    return SkillCatalogResponse(
        total_skills=len(skills_raw),
        enabled_skills=sum(1 for item in skills_raw if item["enabled"]),
        categories=sorted({item["category"] for item in skills_raw}),
        profiles=[
            SkillProfileInfo(**item)
            for item in get_profile_metadata_list([item["name"] for item in skills_raw if item["enabled"]])
        ],
        skills=[SkillInfo(**item) for item in skills_raw],
    )


def _validate_profile_name(profile_name: str) -> str:
    available_profiles = get_skill_profiles(BUILTIN_SKILL_REGISTRY.names())
    if profile_name not in available_profiles:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown skill_profile: {profile_name or '<empty>'}. "
                f"available: {sorted(available_profiles)}"
            ),
        )
    return profile_name


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/skills",
    response_model=SkillCatalogResponse,
    summary="List available built-in skills",
    description=(
        "Return the built-in skill catalog used by the ReAct agent, including "
        "category, required arguments, optional arguments, descriptions, "
        "current enabled state, and available skill profiles."
    ),
)
def list_skills() -> SkillCatalogResponse:
    return _build_skill_catalog()


@app.post(
    "/skills/route-preview",
    response_model=RoutePreviewResponse,
    summary="Preview skill routing for a question",
    description=(
        "Preview the current RouteDecision for a question after applying "
        "enabled skills, the selected profile allowlist, and question routing."
    ),
)
def route_preview(req: RoutePreviewRequest) -> RoutePreviewResponse:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")

    profile_name = _validate_profile_name(req.skill_profile.strip() or DEFAULT_SKILL_PROFILE)
    enabled_skills = get_enabled_skill_names(BUILTIN_SKILL_REGISTRY.names())
    resolved_profile, profile_skills = get_profile_allowlist(profile_name, enabled_skills)
    decision = preview_route(
        question,
        profile_skills,
        engine=req.engine,
        profile_name=resolved_profile,
    )

    return RoutePreviewResponse(
        question=question,
        question_type=decision.qtype.value,
        skill_profile=resolved_profile,
        allowed_skills=decision.allowed,
        preferred_skills=decision.preferred,
        discouraged_skills=decision.discouraged,
        starter=decision.starter,
        reasons=decision.reasons,
        signals=decision.signals,
    )


@app.post(
    "/run",
    response_model=RunResponse,
    summary="Run DeepResearch Agent",
    description=(
        "Run the ReAct research workflow and return the final report, "
        "step trace, structured observations, and deduplicated references."
    ),
)
def run(req: RunRequest) -> RunResponse:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    profile_name = req.skill_profile.strip() or DEFAULT_SKILL_PROFILE
    profile_name = _validate_profile_name(profile_name)

    result = run_agent(
        question=question,
        engine=req.engine,
        max_steps=req.max_steps,
        skill_profile=profile_name,
    )

    observations_raw = result.get("observations", [])
    references, references_md = _build_references(observations_raw)

    return RunResponse(
        answer=result.get("answer", ""),
        steps=[
            StepInfo(
                thought=step.get("thought", ""),
                tool=step.get("tool", ""),
                args=step.get("args", {}),
                observation=step.get("observation", ""),
                sources=step.get("sources", []),
                cite_ids=step.get("cite_ids", []),
                error_type=step.get("error_type"),
            )
            for step in result.get("steps", [])
        ],
        observations=[
            ObservationInfo(
                content=obs.get("content", ""),
                sources=obs.get("sources", []),
                tool=obs.get("tool", ""),
                args=obs.get("args", {}),
                cite_ids=obs.get("cite_ids", []),
            )
            for obs in observations_raw
        ],
        references=references,
        references_md=references_md,
        skill_profile=result.get("skill_profile", DEFAULT_SKILL_PROFILE),
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )
