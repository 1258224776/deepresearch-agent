"""
skills/base.py —— Skill 抽象基类与上下文定义

Skill 的三件套：
  - SkillSpec：声明式元数据（名字、描述、参数），供 LLM 和 UI 渲染
  - SkillContext：执行一次 skill 所需的共享状态（主问题、引擎、历史、registry）
  - Skill：抽象基类，所有具体 skill 继承它、实现 run()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

from pydantic import BaseModel, Field

from report import Observation

if TYPE_CHECKING:
    from report import CitationRegistry


class SkillSpec(BaseModel):
    """
    Skill 的声明式元数据。
    name / desc / args 是给 LLM 看的；category 控制注册表分组排序；
    returns_sources 标记此 skill 是否会产出可登记的来源。
    """
    name: str                                                      # 工具名，唯一
    desc: str                                                      # 一句话描述，进入 system prompt
    args: list[str] = Field(default_factory=list)                  # 必填参数名
    optional_args: list[str] = Field(default_factory=list)         # 可选参数名
    args_desc: dict[str, str] = Field(default_factory=dict)        # 参数的中文解释
    category: str = "utility"                                      # search / scrape / extract / rag / utility
    returns_sources: bool = True                                   # 是否会产生 Source

    def as_tool_info(self) -> dict:
        """导出给 agent_loop.TOOLS 字典 + prompt_react_system 渲染用。"""
        data = {
            "desc": self.desc,
            "args": list(self.args),
        }
        if self.optional_args:
            data["optional_args"] = list(self.optional_args)
        if self.args_desc:
            data["args_desc"] = dict(self.args_desc)
        return data


@dataclass(slots=True)
class SkillContext:
    """
    一次 skill 调用可见的共享状态。

    question     ：用户原始问题（sub-agent 里是改写后的子问题）
    engine       ：引擎预设 "deep"/"fast"/""
    history      ：已执行步骤（dict 列表，含 thought/tool/args/observation 等）
    observations ：结构化观察列表（Observation 实例，比 history 多了 sources）
    registry     ：共享的引用注册表，skill 可以主动查而不必等 agent_loop 登记
    progress_callback：进度回调，传给 UI 层显示状态
    shared       ：skill 之间自由共享的临时数据（目前很少使用）
    """
    question: str
    engine: str = ""
    history: list[dict] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    registry: CitationRegistry | None = None
    progress_callback: Callable | None = None
    shared: dict = field(default_factory=dict)

    @property
    def last_observation(self) -> Observation | None:
        """最近一次成功的观察，summarize 类 skill 用它继承 sources。"""
        return self.observations[-1] if self.observations else None


class Skill(ABC):
    """所有 skill 的抽象基类，子类必须声明 class-level spec 并实现 run()。"""
    spec: SkillSpec

    @abstractmethod
    def run(self, ctx: SkillContext, args: dict) -> Observation:
        raise NotImplementedError
