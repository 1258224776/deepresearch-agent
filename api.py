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


app = FastAPI(
    title="DeepResearch Agent API",
    description=(
        "AI research agent with search, scraping, local RAG, structured "
        "observations, cited final reports, and inspectable skill metadata."
    ),
    version="1.2.0",
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


class SkillCatalogResponse(BaseModel):
    total_skills: int = Field(..., description="Number of registered built-in skills")
    categories: list[str] = Field(default_factory=list, description="Skill categories")
    skills: list[SkillInfo] = Field(default_factory=list, description="Available built-in skills")


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
    skills_raw = BUILTIN_SKILL_REGISTRY.as_metadata_list()
    return SkillCatalogResponse(
        total_skills=len(skills_raw),
        categories=sorted({item["category"] for item in skills_raw}),
        skills=[SkillInfo(**item) for item in skills_raw],
    )


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/skills",
    response_model=SkillCatalogResponse,
    summary="List available built-in skills",
    description=(
        "Return the built-in skill catalog used by the ReAct agent, including "
        "category, required arguments, optional arguments, and descriptions."
    ),
)
def list_skills() -> SkillCatalogResponse:
    return _build_skill_catalog()


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

    result = run_agent(
        question=question,
        engine=req.engine,
        max_steps=req.max_steps,
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
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )
