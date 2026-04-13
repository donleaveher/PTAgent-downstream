# `pkg.agent`

## 统一运行

- **`runner.run_invocation`**：对已编译图执行一次 `invoke`。
- **`runner.compile_llm_client(dry_run=...)`** + **`create_llm_mcp_agent(..., llm=...)`**：干跑与实跑仅差 LLM 实现。
- **HTTP**：`POST /ptagent-admin/api/run`，body：`{ "target", "key", "task", "dry_run", "model", "temperature", "data_payload" }`（`data_payload` 合并进初始 `state.data`）。

## Agent 与 MCP

- **`AgentSpec.mcp_tool_allowlist`**：在类别过滤之后按**工具名**白名单收窄；与 **`mcp_categories`** 组合使用。
- **`GET /ptagent-admin/api/mcp-resources`**：当前 Broker 工具列表 + **`byCategory`**，供界面动态勾选。

## 团队编排（DAG）

- **Legacy**：`graph` 中每节点 `agentKey`；或 **`linear_order`** 自动链式转图。
- **工业编排（v2）**：`schemaVersion: 2`，节点 `kind` 为 `start` / `agent` / `tool` / `end`；图级 `inputKeys` / `outputKeys`；工具节点走单次 MCP `tools/call`。
- **`team.build_team_mcp_workflow`**：按图编译 LangGraph（Agent 节点输出 `{nodeId}_output` 等）。

## 管理端（侧栏导航）

源码目录：**`src/frontend/ptagent/`**（共享样式 **`src/frontend/shared/shell.css`**，URL **`/ui-static/shell.css`**）。

| 路径 | 说明 |
|------|------|
| `/ptagent-admin/` | 总览 |
| `/ptagent-admin/agents` | 卡片式 Agent + 动态工具勾选 + 统一运行 |
| `/ptagent-admin/flow` | 工业编排（起点/Agent/工具/结束）+ 保存 Team |
| `/ptagent-admin/llm` | LLM 密钥与连通性 |

注册表：`{项目根}/data/ptagent_registry.json`。
