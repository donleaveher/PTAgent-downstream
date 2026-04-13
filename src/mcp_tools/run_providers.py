"""
并行拉起多个 MCP Tool Provider 子进程（每个 Provider 一条到 Broker 的 WebSocket）。

**不占独立监听端口**：Provider 作为客户端连到已有 Broker（见 ``PTAGENT_MCP__ENDPOINT``）。

用法（仓库根目录，``mcp_tools`` 位于 ``src/mcp_tools``）::

    export PYTHONPATH=src
    export PTAGENT_MCP__ENDPOINT=ws://127.0.0.1:8001
    python -m mcp_tools.run_providers

环境变量:

- ``PTAGENT_MCP__ENDPOINT`` — 必填（与后端 / Broker 一致）
- ``MCP_TOOLS_PROVIDERS`` — 逗号分隔 ID，默认 ``basic.peptide``（见 ``mcp_tools.registry``）
- ``MCP_TOOL_PROVIDER_MODULE`` — 解析 ``ToolProvider`` 的模块，默认 ``pkg.mcp.provider``
"""

from __future__ import annotations

import importlib
import os
import sys
from multiprocessing import Process
from pathlib import Path
from typing import Callable


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    # src/mcp_tools/run_providers.py -> parents[2] = 仓库根目录
    if len(here.parents) > 2:
        env_path = here.parents[2] / ".env"
        if env_path.is_file():
            load_dotenv(env_path)


def _import_runner(spec: str) -> Callable[[str], None]:
    mod_name, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"invalid provider spec {spec!r}, want 'module:callable'")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise TypeError(f"{spec!r} is not callable")
    return fn  # type: ignore[return-value]


def main() -> None:
    _load_dotenv()
    endpoint = os.environ.get("PTAGENT_MCP__ENDPOINT", "").strip()
    if not endpoint:
        print("错误: 请设置 PTAGENT_MCP__ENDPOINT（与 MCP Broker 配置一致）", file=sys.stderr)
        sys.exit(1)

    from mcp_tools.registry import DEFAULT_PROVIDERS, PROVIDER_SCRIPTS

    raw = os.environ.get("MCP_TOOLS_PROVIDERS", DEFAULT_PROVIDERS).strip()
    ids = [x.strip() for x in raw.split(",") if x.strip()]
    unknown = [i for i in ids if i not in PROVIDER_SCRIPTS]
    if unknown:
        print(f"错误: 未知 provider ID: {unknown}，可选: {list(PROVIDER_SCRIPTS)}", file=sys.stderr)
        sys.exit(1)

    procs: list[Process] = []
    for pid in ids:
        spec = PROVIDER_SCRIPTS[pid]
        runner = _import_runner(spec)
        p = Process(target=runner, args=(endpoint,), name=f"mcp-{pid}")
        p.start()
        procs.append(p)
        print(f"[mcp_tools] started {pid} (pid={p.pid})")

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
