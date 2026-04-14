"""
skills 包 —— 所有 ReAct 工具的外置实现

约定：
  - 每个 *.py 定义一个继承 Skill 的类，声明 class-level `spec: SkillSpec`
  - 在 create_builtin_registry() 中集中注册，运行时由 BUILTIN_SKILL_REGISTRY 统一访问
  - agent_loop 通过 registry.export_tool_dict() 把工具暴露给 LLM
  - router.py 按问题类型做白名单过滤，不要在这里硬编码"可见 / 不可见"

新增 skill 的步骤：
  1. 新建 skills/xxx.py，实现 XxxSkill(Skill)
  2. 在下面的 import 块加一行，再到 create_builtin_registry() 内注册
  3. 如果希望它参与入口预路由，去 skills/router.py 的 ROUTE_MAP 里加一行
"""

from __future__ import annotations

from .extract_links import ExtractLinksSkill
from .extract_structured import ExtractStructuredSkill
from .rag_retrieve import RagRetrieveSkill
from .registry import SkillRegistry
from .scrape_batch import ScrapeBatchSkill
from .scrape_deep import ScrapeDeepSkill
from .scrape_page import ScrapePageSkill
from .search_company import SearchCompanySkill
from .search_docs import SearchDocsSkill
from .search_multi import SearchMultiSkill
from .search_news import SearchNewsSkill
from .search_recent import SearchRecentSkill
from .search_site import SearchSiteSkill
from .search_web import SearchWebSkill
from .summarize_text import SummarizeTextSkill


def create_builtin_registry() -> SkillRegistry:
    registry = SkillRegistry()
    for skill in (
        SearchWebSkill(),
        SearchMultiSkill(),
        SearchDocsSkill(),
        SearchCompanySkill(),
        SearchSiteSkill(),
        ScrapePageSkill(),
        ExtractLinksSkill(),
        ExtractStructuredSkill(),
        SummarizeTextSkill(),
        RagRetrieveSkill(),
        SearchRecentSkill(),
        SearchNewsSkill(),
        ScrapeBatchSkill(),
        ScrapeDeepSkill(),
    ):
        registry.register(skill)
    return registry


BUILTIN_SKILL_REGISTRY = create_builtin_registry()
