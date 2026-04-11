"""
api.py — FastAPI 封装，将 DeepResearch Agent 暴露为 HTTP 工具

供 Dify 等平台通过 OpenAPI 规范调用。

启动方式：
    pip install fastapi uvicorn
    uvicorn api:app --host 0.0.0.0 --port 8000

公网暴露（测试用）：
    ngrok http 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_loop import run_agent

# ══════════════════════════════════════════════
# 应用实例
# ══════════════════════════════════════════════
app = FastAPI(
    title="DeepResearch Agent API",
    description="AI 深度研究 Agent：自动搜索、爬取、RAG 检索，多步推理后输出完整研究报告。",
    version="1.0.0",
)

# 允许 Dify 跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════
class RunRequest(BaseModel):
    question: str = Field(..., description="研究问题，例如：特斯拉 2024 年的核心财务指标是什么？")
    engine: str = Field(
        default="",
        description="引擎模式：deep（全球最强模型，需 VPN）| fast（国内直连）| 空字符串（自动）",
    )
    max_steps: int = Field(default=8, ge=3, le=15, description="Agent 最大推理步数，默认 8")


class StepInfo(BaseModel):
    thought: str
    tool: str
    args: dict
    observation: str


class RunResponse(BaseModel):
    answer: str = Field(..., description="最终研究报告（Markdown 格式）")
    steps: list[StepInfo] = Field(..., description="Agent 每步推理过程")
    step_count: int = Field(..., description="实际执行步数")
    error: str | None = Field(default=None, description="如有错误，此处返回详情")


# ══════════════════════════════════════════════
# 接口
# ══════════════════════════════════════════════
@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}


@app.post(
    "/run",
    response_model=RunResponse,
    summary="运行 DeepResearch Agent",
    description=(
        "输入研究问题，Agent 自主决策调用搜索、爬取、RAG 检索等工具，"
        "多步推理后返回完整的 Markdown 格式研究报告及每步思考过程。"
    ),
)
def run(req: RunRequest) -> RunResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")

    result = run_agent(
        question=req.question.strip(),
        engine=req.engine,
        max_steps=req.max_steps,
    )

    return RunResponse(
        answer=result.get("answer", ""),
        steps=[
            StepInfo(
                thought=s.get("thought", ""),
                tool=s.get("tool", ""),
                args=s.get("args", {}),
                observation=s.get("observation", ""),
            )
            for s in result.get("steps", [])
        ],
        step_count=result.get("step_count", 0),
        error=result.get("error"),
    )
