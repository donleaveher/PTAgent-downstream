# mcp_framework（`pkg.mcp` 子包）

本目录为 **MCP Broker** 实现：对外 **MCP over Streamable HTTP**（[FastMCP](https://gofastmcp.com/)），对内 **WebSocket** 供 Provider 动态注册工具并中继 `tools/call`。

无 CLI；对外以少量类型为主 API。在本仓库中作为 **`pkg.mcp.mcp_framework`** 使用，无需单独 `pip install` 子包（依赖见项目根 `requirements.txt`：`fastmcp` 等）。

```python
from pkg.mcp.mcp_framework import MCPBroker, BrokerConfig

app = MCPBroker().asgi_app()
```

---

## 设计要点

| 面 | 说明 |
|----|------|
| **客户端（LLM / Agent）** | 连接 `http://host:port/mcp`，标准 MCP（`tools/list`、`tools/call` 等）。 |
| **Provider** | 连接 `ws://host:port/provider`，JSON-RPC：`initialize`、`provider/register`、`provider/heartbeat`、`provider/unregister`；执行经 `provider/invoke` 回传。 |
| **进程内发现（可选）** | `MCPDiscoveryCenter` 内存注册表。 |

---

## 对外主 API

1. **`MCPBroker`** — `.asgi_app()` 得到 ASGI 应用；`.run()` 仅本地调试。
2. **`BrokerConfig`** — 名称、路径、超时、发现等。
3. **`RegisteredTool`** — 工具元数据。

进阶：`ToolBroker`、`build_broker_asgi_app`；发现见 `discovery`；URL 见 `endpoints`。

---

## 与 ASGI 宿主集成

```python
from pkg.mcp.mcp_framework import MCPBroker

mcp_app = MCPBroker().asgi_app()
# 按宿主框架文档挂载
```

---

## Provider 协议摘要（WebSocket / JSON-RPC）

- `initialize`
- `provider/register` — `params.providerId`、`params.tools[]`（`name`、`description`、`inputSchema`、`outputSchema`）
- `provider/heartbeat` / `provider/unregister`
- 下行 `provider/invoke` — Broker 将 `tools/call` 转为对 Provider 的中继
