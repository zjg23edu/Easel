"""Call configured OpenClaw tools without duplicating search/model credentials."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .timeouts import TIMEOUT_FACT_MODEL, TIMEOUT_RESEARCH_HTTP


class ToolError(RuntimeError):
    """Safe user-facing error, excluding provider responses and credentials."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


def unpack_result(payload: dict, tool: str) -> dict:
    result = payload.get("result")
    if not payload.get("ok") or not isinstance(result, dict) or result.get("isError"):
        raise ToolError(f"{tool} 未返回有效资料，请检查 Gateway 工具配置和日志。")
    details = result.get("details")
    if isinstance(details, dict):
        value = details.get("json") if tool == "llm-task" else details
        if isinstance(value, dict) and value:
            return value
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                value = json.loads(block["text"])
            except (ValueError, KeyError):
                continue
            if isinstance(value, dict):
                return value
    raise ToolError(f"{tool} 返回格式无法解析，已停止生成。")


class GatewayTools:
    def __init__(self, session_key: str):
        self.session_key = session_key

    async def __call__(self, tool: str, args: dict) -> dict:
        return await asyncio.to_thread(self._invoke, tool, args)

    def _invoke(self, tool: str, args: dict) -> dict:
        if tool not in {"web_search", "tavily_extract", "web_fetch", "llm-task"}:
            raise ToolError("热点核验不允许调用该工具。")
        state = Path(os.environ.get("EASEL_OPENCLAW_STATE_DIR") or Path.home() / ".openclaw-easel")
        try:
            config = json.loads((state / "openclaw.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ToolError("无法读取 Easel Gateway 配置。") from None
        gateway = config.get("gateway", {})
        host = os.environ.get("EASEL_GATEWAY_HOST", "127.0.0.1")
        port = int(os.environ.get("EASEL_GATEWAY_PORT") or gateway.get("port", 18789))
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ToolError("热点核验只连接本机 Gateway，请设置 EASEL_GATEWAY_HOST 为回环地址。")
        auth = gateway.get("auth", {})
        mode = auth.get("mode", "token")
        headers = {"Content-Type": "application/json"}
        if mode != "none":
            env_key = "OPENCLAW_GATEWAY_PASSWORD" if mode == "password" else "OPENCLAW_GATEWAY_TOKEN"
            secret = os.environ.get(env_key) or auth.get("password" if mode == "password" else "token")
            if isinstance(secret, dict) and secret.get("source") == "env":
                secret = os.environ.get(secret.get("id", ""))
            if isinstance(secret, str) and secret.startswith("${") and secret.endswith("}"):
                secret = os.environ.get(secret[2:-1])
            if not isinstance(secret, str) or not secret:
                raise ToolError("Gateway 认证未配置到 Web 进程环境。")
            headers["Authorization"] = f"Bearer {secret}"
        body = json.dumps({"tool": tool, "args": args, "sessionKey": self.session_key}).encode()
        host = f"[{host}]" if ":" in host else host
        request = Request(f"http://{host}:{port}/tools/invoke", body, headers)
        timeout = TIMEOUT_FACT_MODEL + TIMEOUT_RESEARCH_HTTP if tool == "llm-task" else TIMEOUT_RESEARCH_HTTP
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ToolError(f"{tool} 返回过大，已停止生成。")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError()
        except HTTPError as exc:
            # Classify known llm-task formatting errors without exposing provider bodies.
            try:
                detail = exc.read(4096).decode("utf-8", errors="replace")
            except OSError:
                detail = ""
            if tool == "llm-task" and exc.code == 500 and any(marker in detail for marker in (
                    "LLM returned invalid JSON", "LLM JSON did not match schema")):
                raise ToolError("模型返回格式不符合输出契约。", kind="model_format") from None
            hint = ("工具未开放，请检查插件启用和权限。" if exc.code in {401, 403, 404}
                    else "工具执行失败，具体原因需查看 Gateway 日志；也可能是模型输出格式校验未通过。")
            # This Gateway version masks tool exception details as a generic HTTP 500.
            kind = "model_execution" if tool == "llm-task" and exc.code == 500 else "other"
            raise ToolError(f"{tool} 调用失败（HTTP {exc.code}），{hint}", kind=kind) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ToolError(f"{tool} 请求失败或超时，未取得可用结果。") from None
        return unpack_result(payload, tool)
