"""Offline regression cases for event-first writing; no live providers."""
import asyncio
from copy import deepcopy

import pytest

from easel.hot_topic import HotTopic, HotTopicFlow, EventEvidence, Draft, Review, Repair, Check, identity, queries
from easel.gateway_tools import ToolError

QUOTE = "mimo-v2.6-pro in progress step 10 started 2026-09-15 10:32 UTC"
BODY = "MiMo-V2.6 training dashboard\n" + QUOTE + "\n" + "Training metrics and trainer logs are visible. " * 5
TOPIC = HotTopic(title="如何评价小米公开进行大语言模型Mimo V2.6的大规模强化学习训练？")
EVIDENCE = {
    "core_confirmed": True, "core_event": "小米公开展示MiMo-V2.6的训练过程", "reason": "训练面板显示目标型号正在训练",
    "core_evidence": [{"statement": "该面板展示MiMo-V2.6-Pro正在训练", "source_id": "S1", "quote": QUOTE}],
    "supported_details": [], "unsupported_claims": [{"statement": "此刻累计成本123万美元", "reason": "未取得此刻的快照"}],
}
DRAFT = {"outline": {"reader": "关注AI的普通读者", "question": "公开过程有什么价值？", "answer": "提供观察依据",
                     "points": [{"point": "用运行状态说明观察依据", "fact_ids": ["F1"]}]}, "title": "公开训练过程能告诉我们什么", "suitability": "面向关注AI训练的读者", "angles": ["观察训练过程", "过程与结果的区别"],
         "paragraphs": [{"text": "面板显示MiMo-V2.6-Pro正在训练。", "kind": "fact", "fact_ids": ["F1"]},
                        {"text": "我更关注公开过程能否帮助讨论训练方法，而非提前判断最终成绩。", "kind": "analysis", "fact_ids": ["F1"]}]}
REVIEW = {"editorial_ready": True, "core_supported": True, "reason": "有面板正文依据", "checks": [
    {"section_id": key, "status": "supported" if key == "p1" else "opinion", "source_ids": ["S1"] if key == "p1" else [], "reason": "对照正文"}
    for key in ["title", "suitability", "angle1", "angle2", "p1", "p2"]]}


class Tools:
    def __init__(self, evidence=None, drafts=None, reviews=None, repairs=None):
        self.evidence = deepcopy(evidence or [EVIDENCE])
        self.drafts = deepcopy(drafts or [DRAFT])
        self.reviews = deepcopy(reviews or [REVIEW])
        self.repairs = deepcopy(repairs or [{"patches": [{"section_id": "p3", "text": ""}]}])
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
            values = {"EventEvidence": self.evidence, "Draft": self.drafts, "Review": self.reviews, "Repair": self.repairs}[name]
            value = deepcopy(values.pop(0) if len(values) > 1 else values[0])
            if name == "Review":
                value["checks"] = {c["section_id"]: {k: v for k, v in c.items() if k != "section_id"}
                                   for c in value["checks"]}
            return value
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


def test_local_repair_keeps_supported_sentence_and_is_rechecked():
    draft = deepcopy(DRAFT)
    draft["paragraphs"][0]["text"] += "花费123万美元。"
    review = deepcopy(REVIEW)
    review["checks"][4].update(status="revise", issues=[{
        "text": "花费123万美元。", "reason": "正文不支持此金额", "instruction": "删除金额，保留训练状态"}])
    fake = Tools(drafts=[draft, draft], reviews=[review, review, REVIEW],
                 repairs=[{"patches": [{"section_id": "p1", "text": DRAFT["paragraphs"][0]["text"]}]}])
    result, report = run(fake)
    assert result["status"] == "approved"
    assert "123万" not in result["article"] and "正在训练" in result["article"]
    assert len(report["reviews"]) == 3
    assert report["reviews"][-1]["draft"]["paragraphs"][0]["text"] == DRAFT["paragraphs"][0]["text"]
    assert report["remaining_issues"] == []


def test_failed_local_repair_preserves_safe_sentences_but_never_claims_approval():
    draft = deepcopy(DRAFT)
    draft["paragraphs"][0]["text"] += "花费123万美元。"
    review = deepcopy(REVIEW)
    review["checks"][4].update(status="revise", issues=[{
        "text": "123万美元", "reason": "无依据", "instruction": "删除金额"}])
    fake = Tools(drafts=[draft], reviews=[review], repairs=[{
        "patches": [{"section_id": "p1", "text": draft["paragraphs"][0]["text"]}]}])
    result, report = run(fake)
    assert result["status"] == "needs_edit"
    assert "123万" not in result["article"] and "花费" not in result["article"]
    assert "正在训练" in result["article"]
    assert "请检查衔接" in result["text"]
    assert len(report["reviews"]) == 3


def test_background_explanation_does_not_need_fake_event_citation():
    draft = deepcopy(DRAFT)
    draft["paragraphs"].append({"text": "后训练是在已有模型基础上进一步调整表现。", "kind": "background", "fact_ids": []})
    review = deepcopy(REVIEW)
    review["checks"].append({"section_id": "p3", "status": "background", "source_ids": [], "reason": "基础概念准确"})
    result, report = run(Tools(drafts=[draft], reviews=[review]))
    assert result["status"] == "approved"
    assert "进一步调整表现。" in result["article"]
    assert len(report["reviews"]) == 1


@pytest.mark.parametrize("claim", ["正文不存在的句子", "训练"])
def test_review_issue_must_locate_one_exact_claim(claim):
    sections = {"p1": "训练开始。训练进行中。"}
    review = Review.model_validate({"editorial_ready": True, "core_supported": True, "reason": "已确认", "checks": [{
        "section_id": "p1", "status": "revise", "source_ids": [], "reason": "待改", "issues": [{
            "text": claim, "reason": "无依据", "instruction": "删除"}]}]})
    with pytest.raises(ValueError):
        HotTopicFlow.checks(review, sections, [])


def test_local_repair_cannot_patch_unknown_sections():
    with pytest.raises(ValueError):
        HotTopicFlow.patch(Draft.model_validate(DRAFT), Repair.model_validate({"patches": [{"section_id": "p99", "text": "未知"}]}))


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
    first["editorial_ready"] = False
    first["editorial_notes"] = ["p2没有回答标题的问题，请结合已核实事实给出具体解释，合并重复提醒。"]
    final = first if still_needs_polish else REVIEW
    revised = deepcopy(DRAFT)
    revised["paragraphs"][1]["text"] = "我认为公开过程的价值在于提供观察依据，不能据此预判最终成绩。"
    fake = Tools(drafts=[DRAFT, revised], reviews=[first, final])
    result, report = run(fake)
    assert result["status"] == ("needs_edit" if still_needs_polish else "approved")
    assert revised["paragraphs"][1]["text"] in result["article"]
    writes = [args for tool,args in fake.calls if args.get("schema", {}).get("title") == "Draft"]
    assert len(writes) == 2
    assert writes[1]["input"]["feedback"]["editorial_notes"] == first["editorial_notes"]
    assert "remove_sections" not in writes[1]["input"]
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


def test_outline_is_recorded_and_reviewed_but_not_rendered_as_internal_notes():
    fake = Tools()
    result, report = run(fake)
    assert report["outline"] == DRAFT["outline"]
    reviews = [a for t, a in fake.calls if a.get("schema", {}).get("title") == "Review"]
    assert reviews[0]["input"]["outline"] == DRAFT["outline"]
    assert 'fact_ids' not in result["article"]
    assert DRAFT["outline"]["question"] not in result["article"]


def test_critical_background_research_is_bounded_to_one_round():
    first = deepcopy(REVIEW)
    first["background_queries"] = ["reinforcement learning introductory definition official"]
    fake = Tools(reviews=[first, first])
    result, report = run(fake)
    queries_used = [a["query"] for t, a in fake.calls if t == "web_search"]
    assert queries_used.count(first["background_queries"][0]) == 1
    assert report["research_rounds"][-1]["purpose"] == "background"
    assert result["article"]


def test_person_event_does_not_keep_unsupported_departure_in_same_paragraph():
    text = "林舟发表了一篇谈创作感受的随笔。他已经决定辞职。"
    c = Check.model_validate({"section_id": "p1", "status": "revise", "source_ids": ["S1"], "reason": "无辞职依据",
                              "issues": [{"text": "他已经决定辞职。", "reason": "随笔不能证明去向", "instruction": "删除辞职推断"}]})
    assert HotTopicFlow.safe_remainder(text, c) == "林舟发表了一篇谈创作感受的随笔。"


def test_product_quote_preserves_units_and_time_scope():
    e = deepcopy(EVIDENCE)
    e["core_evidence"] = [{"statement": "产品页面列出容量5000mAh", "source_id": "S1", "quote": "Capacity: 5000 mAh; measured under lab conditions", "scope": "snapshot"}]
    facts, _ = HotTopicFlow.facts(EventEvidence.model_validate(e), [{"id": "S1", "text": "**Capacity:** 5000 mAh; measured under lab conditions"}])
    assert len(facts) == 1
    e["core_evidence"][0]["quote"] = "Capacity: 5000 Wh; measured under lab conditions"
    assert HotTopicFlow.facts(EventEvidence.model_validate(e), [{"id": "S1", "text": "Capacity: 5000 mAh; measured under lab conditions"}])[0] == []


def test_review_contract_requires_title_angles_and_every_paragraph():
    fake = Tools()
    run(fake)
    args = next(a for t, a in fake.calls if a.get("schema", {}).get("title") == "Review")
    checks = args["schema"]["properties"]["checks"]
    assert checks["type"] == "object"
    assert set(checks["required"]) == set(HotTopicFlow.sections(Draft.model_validate(DRAFT)))
    assert checks["additionalProperties"] is False
    assert {"title", "suitability", "angle1", "angle2", "p1", "p2"} <= set(checks["properties"])


def test_resolved_editorial_comments_do_not_trigger_rewrite_or_needs_edit():
    review = deepcopy(REVIEW)
    review["editorial_notes"] = ["上一轮问题已修正，继续保留当前解释。"]
    result, report = run(Tools(reviews=[review]))
    assert result["status"] == "approved"
    assert len(report["reviews"]) == 1
    assert report["editorial_ready"] is True
