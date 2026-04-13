# 已实现接口说明（后端 API）

本文档列出当前已经实现、可稳定调用的主要 HTTP 入口，便于联调。

基础 URL：`http://<host>:8000`（端口以实际运行为准）。

---

## 1. MCP 管理台

- **前缀**：`/mcp-admin`
- **说明**：MCP 工具列表、约定文档、多页静态控制台等（见 `pkg.mcp.admin_router`）。

---

## 2. PTAgent 管理端（主控制台）

- **前缀**：`/ptagent-admin`
- **静态页**：`/ptagent-admin/`、`/agents`、`/flow`、`/llm` 等
- **主要 JSON API**（均在 `/ptagent-admin` 下）：
  - `GET /api/overview` — 概览（MCP 端点、注册表路径、Agent/Team 数量）
  - `GET /api/workflow-data-keys` — 编排可用的 `state.data` 键
  - `GET /api/mcp-resources` — MCP 工具负载（供前端画布等使用）
  - `GET|PUT /api/llm/settings`、`POST /api/llm/test`、`GET /api/llm/models`、`POST /api/llm/ping-all`
  - `GET|PUT|DELETE /api/agents`、`GET|PUT|DELETE /api/teams`
  - `POST /api/run` — 单 Agent 或 Team 运行
  - `POST /api/agents/{key}/debug/validate` — Agent 校验

实现位置：`src/router/ptagent_admin.py`。

---

## 3. Agent Studio（兼容入口）

- **前缀**：`/agent-studio`
- **说明**：根路径重定向到 `/ptagent-admin/agents`；`GET /api/overview` 仍返回 MCP 工具信息并提示使用 `/ptagent-admin/api/mcp-resources`。

实现位置：`src/router/agent_studio.py`。

---

## 已移除的示例接口

以下路径曾为占位示例，已从路由中删除：

- `GET /api/tools`
- `POST /api/pipelines/check`

若需要工具目录或 Pipeline 校验，请使用 PTAgent 管理端下的 MCP 与编排相关 API，或在 `application` / `model` 中重新实现用例后再挂路由。
