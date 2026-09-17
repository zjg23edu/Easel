"""Offline regression cases for event-first writing; no live providers."""
import asyncio
from copy import deepcopy

import pytest

from easel.hot_topic import HotTopic, HotTopicFlow, EventEvidence, Draft, Review, identity, queries
from easel.gateway_tools import ToolError

QUOTE = "mimo-v2.6-pro in progress step 10 started 2026-09-15 10:32 UTC"
BODY = "MiMo-V2.6 training dashboard\n" + QUOTE + "\n" + "Training metrics and trainer logs are visible. " * 5
TOPIC = HotTopic(title="如何评价小米公开进行大语言模型Mimo V2.6的大规模强化学习训练？")
EVIDENCE = {
    "core_confirmed": True, "core_event": "小米公开展示MiMo-V2.6的训练过程", "reason": "训练面板显示目标型号正在训练",
    "core_evidence": [{"statement": "该面板展示MiMo-V2.6-Pro正在训练", "source_id": "S1", "quote": QUOTE}],
    "supported_details": [], "unsupported_claims": [{"statement": "此刻累计成本123万美元", "reason": "未取得此刻的快照"}],
}
DRAFT = {"title": "公开训练过程能告诉我们什么", "suitability": "面向关注AI训练的读者", "angles": ["观察训练过程", "过程与结果的区别"],
         "paragraphs": [{"text": "面板显示MiMo-V2.6-Pro正在训练。", "kind": "fact", "fact_ids": ["F1"]},
                        {"text": "我更关注公开过程能否帮助讨论训练方法，而非提前判断最终成绩。", "kind": "analysis", "fact_ids": ["F1"]}]}
REVIEW = {"core_supported": True, "reason": "有面板正文依据", "checks": [
    {"section_id": key, "status": "supported" if key == "p1" else "opinion", "source_ids": ["S1"] if key == "p1" else [], "reason": "对照正文"}
    for key in ["title", "suitability", "angle1", "angle2", "p1", "p2"]]}


class Tools:
    def __init__(self, evidence=None, drafts=None, reviews=None):
        self.evidence = deepcopy(evidence or [EVIDENCE])
        self.drafts = deepcopy(drafts or [DRAFT])
        self.reviews = deepcopy(reviews or [REVIEW])
        self.calls = []

    async def __call__(self, tool, args):
        self.calls.append((tool, args))
        if tool == "web_search":
            return {"results": [{"url": "https://example.com/old", "title": "MiMo-V2-Flash 发布", "snippet": "旧版本"},
                                {"url": "https://example.com/rl/", "title": "mimo-v2.6 RL", "snippet": "training dashboard"}]}
        if tool == "tavily_extract":
            return {"results": [{"url": url, "rawContent": BODY} for url in args["urls"]]}
        if tool == "web_fetch":
            return {"text": ""}
        if tool == "llm-task":
            name = args["schema"]["title"]
            values = {"EventEvidence": self.evidence, "Draft": self.drafts, "Review": self.reviews}[name]
            return values.pop(0) if len(values) > 1 else values[0]
        raise AssertionError(tool)


def run(tools):
    flow = HotTopicFlow(tools)
    return asyncio.run(flow.run(TOPIC, "写这次训练直播，不要求模型发布")), flow.report


def test_training_in_progress_without_release_cost_or_final_scores_produces_article():
    fake = Tools()
    result, report = run(fake)
    assert result["status"] == "approved"
    assert "正在训练" in result["article"]
    assert report["core_confirmed"] is True
    assert report["unsupported_claims"][0]["statement"] == "此刻累计成本123万美元"
    assert "最终成绩" not in result["article"].split("我更关注")[0]
    assert [args["schema"]["title"] for tool,args in fake.calls if tool == "llm-task"] == ["EventEvidence", "Draft", "Review"]
    assert len(report["research_rounds"]) == 1  # No searching for missing optional details.


def test_exact_version_and_effective_queries_are_preserved():
    assert identity(TOPIC.title) == "Mimo-V2.6"
    for followup in [False, True]:
        qs = queries(TOPIC, followup)
        assert all('"Mimo-V2.6"' in q for q in qs)
        assert all("Flash" not in q and "发布" not in q for q in qs)
    assert queries(TOPIC)[0] == '"Mimo-V2.6" 强化学习 直播'
    assert identity("如何看待Qwen V3.5的测试") == "Qwen-V3.5"


def test_old_version_results_are_not_read():
    fake = Tools()
    _, report = run(fake)
    assert report["research_rounds"][0]["selected_urls"] == ["https://example.com/rl"]
    assert "https://example.com/old" in report["research_rounds"][0]["excluded"]


def test_invalid_optional_quote_is_omitted_without_blocking_event():
    e = deepcopy(EVIDENCE)
    e["supported_details"] = [{"statement": "花费123万美元", "quote": "正文中根本没有这句话", "source_id": "S1"}]
    result, report = run(Tools(evidence=[e]))
    assert result["status"] == "approved"
    assert any(c["statement"] == "花费123万美元" for c in report["unsupported_claims"])
    assert len(report["facts"]) == 1


@pytest.mark.parametrize("case", ["unconfirmed", "fabricated_quote", "unknown_source"])
def test_only_unconfirmed_core_stops_for_missing_evidence(case):
    e = deepcopy(EVIDENCE)
    if case == "unconfirmed": e["core_confirmed"] = False
    elif case == "fabricated_quote": e["core_evidence"][0]["quote"] = "正文中根本没有这句话"
    else: e["core_evidence"][0]["source_id"] = "S99"
    fake = Tools(evidence=[e])
    result, report = run(fake)
    assert result["status"] == "blocked" and not result["article"]
    assert len(report["research_rounds"]) == 2
    assert not any(a.get("schema", {}).get("title") == "Draft" for _,a in fake.calls)


def test_unsupported_detail_is_removed_after_revision_not_whole_article():
    draft = deepcopy(DRAFT)
    draft["paragraphs"].append({"text": "花费123万美元。", "kind": "fact", "fact_ids": ["F1"]})
    review = deepcopy(REVIEW)
    review["checks"].append({"section_id": "p3", "status": "remove", "source_ids": [], "reason": "正文不支持此金额"})
    fake = Tools(drafts=[draft, draft], reviews=[review, review])
    result, report = run(fake)
    assert result["status"] == "approved"
    assert "123万" not in result["article"] and "正在训练" in result["article"]
    assert report["removed_sections"] == ["p3"]
    assert len(report["reviews"]) == 2


def test_missing_review_section_is_processing_error_not_missing_evidence():
    review = deepcopy(REVIEW); review["checks"].pop()
    result, report = run(Tools(reviews=[review]))
    assert result["status"] == "error" and not result["article"]
    assert report["core_confirmed"] is True
    assert "格式异常" in result["text"]


def test_second_pass_can_establish_core_then_write():
    bad = deepcopy(EVIDENCE); bad.update(core_confirmed=False, reason="尚未确认事件")
    result, report = run(Tools(evidence=[bad, EVIDENCE]))
    assert result["status"] == "approved"
    assert len(report["research_rounds"]) == 2


def test_no_extracted_body_never_reaches_writing():
    fake = Tools()
    async def invoke(tool, args):
        if tool == "tavily_extract": return {"results": []}
        return await fake(tool, args)
    result, _ = run(invoke)
    assert result["status"] == "blocked"
    assert not any(tool == "llm-task" for tool,_ in fake.calls)


def test_contract_is_visible_to_model_at_every_stage():
    import json
    fake = Tools()
    run(fake)
    for tool,args in fake.calls:
        if tool == "llm-task":
            assert json.loads(args["prompt"].split("OUTPUT_JSON_SCHEMA:\n")[1]) == args["schema"]



@pytest.mark.parametrize("still_needs_polish", [False, True])
def test_editorial_feedback_triggers_one_revision_without_blocking(still_needs_polish):
    first = deepcopy(REVIEW)
    first["editorial_notes"] = ["p2没有回答标题的问题，请结合已核实事实给出具体解释，合并重复提醒。"]
    final = first if still_needs_polish else REVIEW
    revised = deepcopy(DRAFT)
    revised["paragraphs"][1]["text"] = "我认为公开过程的价值在于提供观察依据，不能据此预判最终成绩。"
    fake = Tools(drafts=[DRAFT, revised], reviews=[first, final])
    result, report = run(fake)
    assert result["status"] == "approved"
    assert revised["paragraphs"][1]["text"] in result["article"]
    writes = [args for tool,args in fake.calls if args.get("schema", {}).get("title") == "Draft"]
    assert len(writes) == 2
    assert writes[1]["input"]["feedback"]["editorial_notes"] == first["editorial_notes"]
    assert writes[1]["input"]["remove_sections"] == []
    assert len(report["reviews"]) == 2


def test_markdown_quote_keeps_real_evidence_and_snapshot_details():
    e = deepcopy(EVIDENCE)
    e["supported_details"] = [{"statement": "快照的批次配置是1568×16", "source_id": "S1",
                               "quote": "train batch size × n 1,568 × 16 seqs", "scope": "snapshot",
                               "usage_note": "页面快照，不代表当前实时值"}]
    source = "**mimo-v2.6-pro**in progress step 10 started 2026-09-15 10:32 UTC\n\ntrain batch size × n\n\n1,568 × 16 seqs"
    facts, unsupported = HotTopicFlow.facts(EventEvidence.model_validate(e), [
        {"id": "S1", "text": source, "retrieved_at": "2026-09-17T08:40:00Z"}])
    assert len(facts) == 2
    assert facts[1]["scope"] == "snapshot"
    assert facts[1]["retrieved_at"] == "2026-09-17T08:40:00Z"
    assert len(unsupported) == 1  # A different unsupported current-value claim does not ban the snapshot.


@pytest.mark.parametrize("wrong", ["MiMo-V2.5 is not released; cost $10 million",
                                     "MiMo-V2.6 is released; cost $10 million",
                                     "MiMo-V2.6 is not released; cost $11 million",
                                     "MiMo-V2.6 is not released; cost $10 billion"])
def test_quote_normalization_never_erases_meaning(wrong):
    e = deepcopy(EVIDENCE)
    e["core_evidence"][0]["quote"] = wrong
    facts, _ = HotTopicFlow.facts(EventEvidence.model_validate(e), [
        {"id": "S1", "text": "**MiMo-V2.6** is not released; cost $10 million"}])
    assert facts == []
