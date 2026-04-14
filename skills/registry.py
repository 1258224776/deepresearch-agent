"""
skills/registry.py —— Skill 注册表

职责：
  - 集中存放所有 Skill 实例，按名字查找
  - 导出 tool 字典给 agent_loop.TOOLS（LLM 可见）
  - 导出分组元数据给 UI（按 category 展示）
  - 提供 run(name, ctx, args) 统一执行入口

设计要点：同名 skill 注册会报错；未知 skill 调用会抛 KeyError，
由 agent_loop 的 parse_action / router 层捕获并转成"越权/未知工具"提示。
"""

from __future__ import annotations

from report import Observation

from .base import Skill, SkillContext


# UI / 元数据展示时的分组排序（数字小的在前）
_CATEGORY_ORDER = {
    "search": 10,   # 搜索类
    "scrape": 20,   # 抓取类
    "extract": 30,  # 抽取类
    "rag": 40,      # 本地 RAG
    "utility": 50,  # 通用工具（summarize 等）
}


class SkillRegistry:
    """按 name 索引 skill，提供多种视图：工具字典 / 分组元数据 / 执行入口。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        name = skill.spec.name.strip()
        if not name:
            raise ValueError("skill name cannot be empty")
        if name in self._skills:
            raise ValueError(f"duplicate skill: {name}")
        self._skills[name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def required_args(self, name: str) -> list[str]:
        skill = self.get(name)
        return list(skill.spec.args) if skill else []

    def export_tool_dict(self) -> dict[str, dict]:
        return {
            name: skill.spec.as_tool_info()
            for name, skill in self._skills.items()
        }

    def as_metadata_list(self) -> list[dict]:
        items: list[dict] = []
        for name, skill in self._skills.items():
            spec = skill.spec
            items.append(
                {
                    "name": name,
                    "description": spec.desc,
                    "category": spec.category,
                    "required_args": list(spec.args),
                    "optional_args": list(spec.optional_args),
                    "args_desc": dict(spec.args_desc),
                    "returns_sources": spec.returns_sources,
                }
            )
        return sorted(
            items,
            key=lambda item: (
                _CATEGORY_ORDER.get(item["category"], 999),
                item["category"],
                item["name"],
            ),
        )

    def as_grouped_metadata(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for item in self.as_metadata_list():
            grouped.setdefault(item["category"], []).append(item)
        return grouped

    def run(self, name: str, ctx: SkillContext, args: dict) -> Observation:
        skill = self.get(name)
        if not skill:
            raise KeyError(f"unknown skill: {name}")
        return skill.run(ctx, args)
