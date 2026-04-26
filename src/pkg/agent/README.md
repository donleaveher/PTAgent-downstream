# `pkg.agent`

## Agent 交互模式（`AgentSpec.interaction_mode`）

- **`freeform`（默认）**：开放式对话与工具调用。
- **`structured`**：在 **`meta.output_json_schema`** 中提供 **JSON Schema**（管理台 Agents 页可编辑）。运行时将该 Schema 追加进 **system prompt**，要求模型**仅输出一段可解析 JSON**；随后用 **`jsonschema`（Draft 2020-12）** 校验。成功则 `state.data.structured_valid=true`，`working_note` 为规范化 JSON 字符串；失败则保留模型原文，并写入 `structured_valid=false` 与 `structured_validation_error`。解析逻辑见 **`pkg/agent/structured_output.py`**。

## 多工具 / 分叉与并行

- 工业编排中，**同一节点若有多条出边**，下游节点由 LangGraph **并行调度**（fan-out）；合并进 `state.data` 时若多路写入**同一键**，以后写为准（见 `fork_warnings` 提示）。**建议**各工具节点使用不同 `outputKey`。
- **纯线性**链式图（单后继）则为**串行**。

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

管理台页面源码在 monorepo **`PTAgent-frontend/frontend/ptagent/`**；由边缘 ASGI 提供 **`/ptagent-admin/`** 与 **`/ui-static/...`**。本仓库仅暴露 **`/ptagent-admin/api/...`**。

| 路径 | 说明 |
|------|------|
| `/ptagent-admin/` | 总览 |
| `/ptagent-admin/agents` | 卡片式 Agent + 动态工具勾选 + 统一运行 |
| `/ptagent-admin/flow` | 工业编排（起点/Agent/工具/结束）+ 保存 Team |
| `/ptagent-admin/llm` | LLM 密钥与连通性 |

持久化（**统一 SQLite**，默认 `{项目根}/data/ptagent.db`，WAL 模式）由 **`application/agent/store.py`** 实现（**非** `pkg`）：

- **Agent / Team**：表 `agents`、`teams`。
- **LLM 覆盖与自定义模型目录**：表 `kv`（键 `llm_overrides`、`llm_models` 等）。
- 路径覆盖：**`PTAGENT_DATABASE__SQLITE_PATH`**（相对路径相对 **`PTAGENT_PROJECT_ROOT`**）。
- 容器/集群：务必设置 **`PTAGENT_PROJECT_ROOT`** 指向**可写持久卷**，否则重启后数据仍在临时层会丢失。
