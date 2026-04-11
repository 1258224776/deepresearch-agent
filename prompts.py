"""
prompts.py — 所有 Prompt 模板集中管理
"""

# ══════════════════════════════════════════════
# 系统提示词（通用）
# ══════════════════════════════════════════════
SYSTEM_PROMPT = """你是一个深度研究助手。
我会给你提供从多个角度搜索并抓取的网页资料，你需要：
1. 基于这些资料，对用户的问题给出深入、有条理的分析
2. 标注哪些信息来自哪个来源（注明网址）
3. 指出不同来源之间的异同或矛盾
4. 指出资料的局限性或需要进一步核实的地方
5. 最后给出你自己的综合判断

请用中文回答，保持专业但易于理解的风格。
如果搜索结果与问题无关，请直接说明并凭自身知识回答。"""

CHAT_SYSTEM_PROMPT = "你是一位专业研究助手，基于已有的研究报告和资料回答用户的追问。回答要简洁精准，如需引用报告内容请注明。"

# ══════════════════════════════════════════════
# 场景化报告模板
# ══════════════════════════════════════════════
TEMPLATES: dict[str, dict] = {
    "general": {
        "label":  "📋 通用研究报告",
        "desc":   "适合所有主题，结构灵活",
        "system": SYSTEM_PROMPT,
    },
    "industry": {
        "label": "📊 行业研究报告",
        "desc":  "行业规模、竞争格局、发展趋势",
        "system": """你是一位专业的行业研究分析师。请基于提供的资料，生成一份标准行业研究报告，严格按照以下结构：

## 一、行业概述
（规模、定义、主要细分领域）

## 二、市场现状与规模
（市场规模数据、增长率、关键指标）

## 三、竞争格局
（主要玩家、市场份额、竞争态势）

## 四、发展趋势与驱动因素
（技术/政策/需求驱动的趋势）

## 五、风险与挑战
（潜在风险点）

## 六、综合结论
（核心判断与建议）

要求：数据翔实、引用来源、客观专业。""",
    },
    "investment": {
        "label": "💰 投资备忘录",
        "desc":  "市场机会、竞争壁垒、风险评估",
        "system": """你是一位资深投资分析师。请基于资料生成一份投资备忘录（Investment Memo），结构如下：

## Executive Summary（执行摘要）
（核心投资逻辑，3-5句话）

## 市场机会
（TAM/SAM/SOM 估算，增长驱动）

## 竞争分析
（主要竞争对手、差异化优势、护城河）

## 商业模式
（收入结构、盈利路径、单位经济模型）

## 风险因素
（市场/技术/政策/竞争风险，各附应对策略）

## 投资结论
（建议评级：强烈关注/观察/回避，理由）

要求：数据驱动，逻辑严密，每个判断有依据。""",
    },
    "academic": {
        "label": "🎓 学术文献综述",
        "desc":  "研究背景、文献梳理、研究空白",
        "system": """你是一位学术研究助手。请基于资料生成一份规范的学术文献综述，结构如下：

## 1. 研究背景与意义
## 2. 核心概念界定
## 3. 研究现状综述
## 4. 研究争议与分歧
## 5. 研究空白与不足
## 6. 研究展望
## 参考文献

要求：学术规范，客观评述，注明出处。""",
    },
    "pr": {
        "label": "📰 舆情分析报告",
        "desc":  "舆论现状、关键声音、风险预警",
        "system": """你是一位公关与舆情分析专家。请基于资料生成一份舆情分析报告，结构如下：

## 一、舆情概况
## 二、主要声音分析
## 三、关键意见领袖（KOL）
## 四、媒体报道分析
## 五、风险预警
## 六、应对建议

要求：客观呈现，区分事实与观点，标注信息来源可信度。""",
    },
    "competitive": {
        "label": "🔍 竞品分析报告",
        "desc":  "产品对比、优劣势、市场定位",
        "system": """你是一位产品战略分析师。请基于资料生成一份竞品分析报告，结构如下：

## 一、竞品概览
## 二、功能对比矩阵（表格）
## 三、定价策略对比
## 四、优劣势分析
## 五、市场定位与用户群体
## 六、竞争机会与策略建议

要求：数据对比清晰，表格直观，结论可操作。""",
    },
}

# ══════════════════════════════════════════════
# 动态 Prompt 工厂函数
# ══════════════════════════════════════════════

def prompt_reason(question: str) -> str:
    return f"""你是一个高级搜索规划师。分析用户的需求，判断任务模式并制定最佳搜索策略。

用户问题：{question}

任务模式判断规则：
- **research（深度研究）**：用户想理解某话题、获取知识、写分析报告。如：AI趋势、技术原理、行业分析、某事件背景。
- **aggregation（数据汇总）**：用户想收集一批资源或列表数据。如：找工作、找房子、商品比价、企业名录、开源项目列表、竞品收集。

aggregation 模式下搜索词规则：
- 必须使用 site: 语法定向到专业平台
- 找工作 → site:liepin.com / site:zhaopin.com / site:lagou.com / site:boss.zhipin.com
- 找房子 → site:lianjia.com / site:anjuke.com / site:ke.com
- 找公司 → site:tianyancha.com / site:qichacha.com
- 开源项目 → site:github.com
- 商品比价 → site:jd.com / site:taobao.com
- 没有明显平台时，生成 3-5 个覆盖不同平台的搜索词

请以 JSON 格式返回：
{{
  "task_mode": "research 或 aggregation",
  "question_type": "实时信息/深度研究/简单事实/闲聊对话/数据汇总",
  "need_search": true 或 false,
  "reasoning": "你的分析思路（2-4句话）",
  "search_queries": ["搜索词1", "搜索词2", "搜索词3"],
  "target_item": "aggregation 时填要收集的对象，如'招聘岗位'、'二手房源'、'开源项目'；research 时留空",
  "max_pages": 5,
  "answer_direct": "如果 need_search 为 false，这里给出完整回答；否则留空"
}}

只返回 JSON，不要其他内容。"""


def prompt_summarize_source(content: str, question: str, title: str) -> str:
    return f"""你是信息提炼专家。针对研究主题"{question}"，分析以下网页。

标题：{title}
内容：
{content[:5000]}

请严格返回 JSON，格式：
{{
  "summary": "2-3句核心摘要，说明本页主要内容及与主题的关系",
  "key_points": "4-6个要点，每点以 • 开头，包含具体数据/事实/观点",
  "relevance": "high 或 medium 或 low"
}}
只返回 JSON，不要其他内容。"""


def prompt_extract_key_points(content: str, question: str) -> str:
    return f"""从以下网页内容中，提取与"{question}"最相关的 4-6 个关键信息点。
要求：每条以 "• " 开头，一句话，包含具体数据或观点；去掉广告/导航噪音；只返回要点列表。
网页内容：\n{content[:4000]}"""


def prompt_compile_digest(parts: str, question: str) -> str:
    return f"""基于以下多个来源，针对"{question}"写一份综合性内容概述。

{parts}

要求：
- 3-5 段，每段聚焦一个维度（现状、趋势、数据、争议、结论等）
- 整合各来源信息，标注差异或共识
- 客观陈述，有具体数据支撑
- 用中文，专业流畅"""


def prompt_ai_extract(content: str, instruction: str) -> str:
    return f"""请从以下网页内容中，提取出：{instruction}

要求：
- 只返回提取到的内容，不要加多余解释
- 用清晰的格式输出（列表、表格均可）
- 如果找不到相关内容，说明"未找到相关内容"

网页内容：
{content[:8000]}"""


def prompt_cross_validate(parts: str, question: str) -> str:
    return f"""你是一位严谨的事实核查专家。针对研究主题"{question}"，对以下来源进行交叉验证分析。

{parts}

请返回 JSON，格式如下：
{{
  "key_claims": [
    {{
      "claim": "关键结论（具体陈述）",
      "support": [1, 3],
      "oppose": [2],
      "neutral": [],
      "verdict": "confirmed 或 disputed 或 unverified",
      "confidence": "high 或 medium 或 low"
    }}
  ],
  "credibility": [
    {{
      "source_index": 1,
      "score": 85,
      "type": "权威机构 或 主流媒体 或 行业媒体 或 自媒体 或 未知",
      "note": "简短说明"
    }}
  ],
  "consensus": "各来源的主要共识（1-2句）",
  "disputes": "主要争议点（1-2句，如无则填'无明显争议'）",
  "reliability": "overall 可靠性评估：high/medium/low"
}}

只返回 JSON，不要其他内容。"""


def prompt_generate_sub_queries(question: str) -> str:
    return f"""请将以下研究问题拆解为3个不同角度的搜索关键词，用于网络搜索。
每个关键词应该覆盖问题的不同侧面。
只返回一个 JSON 数组，格式如：["关键词1", "关键词2", "关键词3"]
不要返回任何其他内容。

研究问题：{question}"""


def prompt_scrape_digest(combined_content: str, topic: str) -> str:
    return f"""以下是爬取到的网页内容，请针对主题"{topic}"生成一份结构化汇总报告。

{combined_content[:12000]}

要求：
- 提炼核心信息（3-5段）
- 列出关键数据、事实和观点
- 标注信息来源页面
- 指出内容的局限性
- 用中文，简洁专业"""


def prompt_chat_with_report(question: str, report: str, history: str, user_msg: str) -> str:
    return f"""研究主题：{question}

研究报告：
{report[:4000]}

{'对话历史：\n' + history if history else ''}

用户追问：{user_msg}"""


def prompt_extract_list(page_content: str, target_item: str) -> str:
    return f"""以下是一个网页的正文内容，用户想收集【{target_item}】的列表信息。

请找出网页中所有相关条目，以严格的 JSON 数组格式返回。
每个对象尽量包含以下字段（没有的字段填 null）：
title（名称/职位/标题）、company（公司/发布者）、price（价格/薪资）、location（地点）、tags（标签列表）、url（链接）、desc（简短描述）

要求：
- 只返回 JSON 数组，不要任何其他内容
- 找不到任何条目时返回 []
- 每个对象字段保持一致

网页内容：
{page_content[:15000]}"""


def prompt_aggregation_report(items_md: str, question: str, total: int) -> str:
    return f"""用户问题：{question}

以下是从多个网站汇总的 {total} 条数据：

{items_md[:12000]}

请生成一份简洁的数据分析报告，包含：
1. 数据概况（共几条，来自哪些平台，整体特征）
2. 关键发现（2-4条最值得关注的规律、趋势或洞察）
3. 给用户的具体建议（可操作的 2-3 条建议）

用中文，简洁专业，重点突出数据规律。"""
