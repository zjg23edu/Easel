"""Manual model acceptance against frozen source documents; never invoked by pytest."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from easel.gateway_tools import GatewayTools
from easel.hot_topic import HotTopic, HotTopicFlow
from easel.timeouts import TIMEOUT_HOT_TOPIC


class FrozenFlow(HotTopicFlow):
    def __init__(self, invoke, documents, progress):
        super().__init__(invoke, progress)
        self.documents = documents

    async def research(self, topic, request, docs, followup=False, background_queries=None):
        if not docs:
            docs.extend(deepcopy(self.documents))
        self.report["documents"] = docs
        self.report["frozen_sources"] = True
        if background_queries:
            self.report["unfulfilled_background_queries"] = background_queries
        return docs


async def replay(sample, output):
    gateway = GatewayTools("agent:main:hot-topic-replay-" + uuid.uuid4().hex)

    async def invoke(tool, args):
        if tool != "llm-task":
            raise ValueError("Frozen replay must not search or fetch new sources")
        return await gateway(tool, args)

    flow = FrozenFlow(invoke, sample["documents"], lambda message: print(message, flush=True))
    result = await asyncio.wait_for(flow.run(HotTopic.model_validate(sample["topic"]),
        sample.get("request", "围绕这个热点写一篇有事实、有解释的公众号初稿。"),
        sample.get("profile", "")), timeout=TIMEOUT_HOT_TOPIC)
    flow.report["fictional_fixture"] = bool(sample.get("fictional"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(flow.report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "draft.md").write_text(result["article"], encoding="utf-8")
    print(json.dumps({"status": result["status"], "facts": len(flow.report.get("facts", [])),
                      "reviews": len(flow.report.get("reviews", [])), "output": str(output)}, ensure_ascii=False))
    return 0 if result["article"] else 1


def main():
    parser = argparse.ArgumentParser(description="用冻结正文进行人工验收；会调用当前配置模型，不搜索、不发布、不进入生产会话。")
    parser.add_argument("--input", type=Path, required=True, help="包含topic、documents及可选request的JSON，亦可使用历史取证记录")
    parser.add_argument("--output", type=Path, required=True, help="独立验收输出目录，不能是已存在的目录")
    parser.add_argument("--live-model", action="store_true", help="明确执行真实模型调用；不能由自动测试使用")
    args = parser.parse_args()
    if not args.live_model:
        parser.error("这是手动模型验收命令，需要 --live-model；普通测试不调用模型")
    if args.output.exists():
        parser.error("输出目录已存在，请选择新目录以保留之前记录")
    sample = json.loads(args.input.read_text(encoding="utf-8"))
    return asyncio.run(replay(sample, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
