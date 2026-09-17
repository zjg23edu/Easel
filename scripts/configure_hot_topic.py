#!/usr/bin/env python3
"""Enable the bundled llm-task tool used by the hot-topic pipeline."""
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def configured(config: dict) -> dict:
    result = copy.deepcopy(config)
    plugins = result.setdefault("plugins", {})
    plugins.setdefault("entries", {}).setdefault("llm-task", {})["enabled"] = True
    if "allow" in plugins and "llm-task" not in plugins["allow"]:
        plugins["allow"].append("llm-task")
    if "llm-task" in plugins.get("deny", []):
        raise ValueError("llm-task 被 plugins.deny 禁止，请先确认现有权限策略。")
    tools = result.setdefault("tools", {})
    # Respect existing explicit allowlists; do not combine allow and alsoAllow.
    key = "allow" if "allow" in tools else "alsoAllow"
    allowed = tools.setdefault(key, [])
    if "llm-task" not in allowed:
        allowed.append("llm-task")
    if "llm-task" in tools.get("deny", []) or "llm-task" in result.get("gateway", {}).get("tools", {}).get("deny", []):
        raise ValueError("llm-task 被工具权限禁止，请先确认现有权限策略。")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw-easel" / "openclaw.json")
    args = parser.parse_args()
    path = args.config.expanduser().resolve()
    original = json.loads(path.read_text(encoding="utf-8"))
    result = configured(original)
    if result == original:
        print("热点核验工具已配置，无需修改。")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.name}.before-fact-check-{stamp}")
    # Backups also contain credentials; create both files with private permissions.
    with backup.open("x", encoding="utf-8") as handle:
        os.chmod(backup, 0o600)
        handle.write(path.read_text(encoding="utf-8"))
    temp = path.with_name(f".{path.name}.{stamp}.tmp")
    with temp.open("x", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)
    print(f"已启用 llm-task；备份：{backup}。请重启 Easel Gateway。")


if __name__ == "__main__":
    main()
