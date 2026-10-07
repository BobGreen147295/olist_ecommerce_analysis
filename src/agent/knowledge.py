"""Small, public-only product knowledge retrieval; never indexes merchant data."""

import re


# ponytail: curated keyword retrieval for four records; evaluate recall before adding embeddings.
DOCUMENTS = (
    {
        "id": "order-sales", "title": "订单销售额的当前口径",
        "keywords": ("销售额", "订单金额", "sales", "revenue"),
        "text": "CSV 订单趋势按期间汇总 total_amount，订单数按 order_id 去重。销售额不等于利润；不能把订单金额汇总自动称为扣除退款、折扣、税费后的净销售额。Shopify 同步汇总与 CSV 导入是不同来源，比较前必须核对来源、时间范围和币种。多币种不能直接相加。",
        "source_url": "https://github.com/BobGreen147295/olist_ecommerce_analysis/blob/91cba64/src/agent/commerce_store.py",
    },
    {
        "id": "profit-data", "title": "折扣与利润诊断的数据边界",
        "keywords": ("利润", "亏损", "折扣", "成本", "profit", "discount", "cost", "margin"),
        "text": "折扣高不等于亏损。判断利润侵蚀，需要明确商品成本、折扣、退款、履约及渠道费用和税费处理口径；缺少这些字段时只能描述已知金额和缺口，不能计算真实净利润或声称某订单亏损。通用订单 CSV 当前没有完整成本字段。",
        "source_ref": "src/agent/knowledge.py · profit-data",
    },
    {
        "id": "retention-readiness", "title": "复购与召回的适用条件",
        "keywords": ("复购", "召回", "流失", "retention", "repeat purchase", "churn", "reactivation"),
        "text": "复购率必须先说明人群、观察窗口、有效订单及分母口径。例如窗口内至少两笔有效订单的客户数除以窗口内购买客户数，是一种口径，不等同于首购队列的后续复购率。当前趋势工具没有计算复购率，不能从订单总数推算。召回诊断还需要稳定的匿名客户标识、覆盖合理购买周期的历史和明确营销同意及可执行渠道。小样本、缺失历史或仅开发店订单不能证明真实流失或收入增量；没有授权不得触达。",
        "source_ref": "src/agent/knowledge.py · retention-readiness",
    },
    {
        "id": "roi-evidence", "title": "ROI 与实验效果的证据要求",
        "keywords": ("roi", "投入产出", "增量", "对照组", "实验", "a/b", "uplift"),
        "text": "机会估算不是已实现收入。ROI 必须明确收益与成本口径；若用增量利润，口径可为（增量利润减实验成本）除以实验成本，且成本必须大于零。声称增量效果需要可比较的对照组、明确归因窗口、执行回执及结果数据；没有这些证据时不得把收入变化归因于 AI，或保证增长。预算与触达均需商家确认。",
        "source_ref": "src/agent/knowledge.py · roi-evidence",
    },
)


def retrieve_knowledge(query: str) -> list[dict]:
    """Return only authored product rules, not policy news or private documents."""
    normalized = query.casefold()
    ranked = []
    for document in DOCUMENTS:
        score = sum(
            bool(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", normalized))
            if term.isascii() else term in normalized
            for term in document["keywords"]
        )
        if score:
            ranked.append((score, document))
    ranked.sort(key=lambda item: -item[0])
    return [{key: value for key, value in document.items() if key != "keywords"}
            | {"version": "2026-10-07", "scope": "public_product_rule", "source_kind": "产品自定义口径"}
            for _, document in ranked[:3]]


def is_knowledge_question(query: str) -> bool:
    normalized = query.casefold()
    # Explicit definitions only; store-specific measurements stay on the data path.
    return any(term in normalized for term in (
        "是什么意思", "什么是", "如何定义", "怎么定义", "定义是什么", "怎么算", "如何计算",
        "计算公式", "需要哪些数据", "what is", "definition", "how to calculate",
    )) and not any(term in normalized for term in ("本月", "上月", "我的店", "我们店", "my store", "this month"))


def render_knowledge(documents: list[dict]) -> str:
    if not documents:
        return "当前审核过的产品知识库没有与问题匹配的依据，不能据此作答。请明确指标名称或补充可核验资料；本知识库不提供实时政策结论。"
    return "\n\n".join(
        f"[{item['id']}] {item['title']}\n{item['text']}\n"
        f"依据：{item['source_kind']} · 版本 {item['version']}\n{item.get('source_url') or item['source_ref']}"
        for item in documents
    )
