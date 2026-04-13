# 质谱-蛋白质组学智能 Agent 内核（基于 LangGraph）

本项目目标是构建一个**企业级可扩展**的质谱-蛋白质组学智能 Agent 内核，基于 **LangGraph / RAG / Multi-Agent** 架构，用于支持从原始质谱数据到生物学结论的一体化智能工作流。

## 快速开始（后端 API）

1. **配置环境变量**：复制 `.env.example` 为 `.env`，至少填写 `PTAGENT_JWT__SECRET_KEY`、`PTAGENT_MCP__ENDPOINT`（与 MCP Broker 地址一致，例如 `http://127.0.0.1:8765/mcp`）。
2. **安装依赖**：`./scripts/setup.sh`（需要已安装 [uv](https://github.com/astral-sh/uv)），然后 `source .venv/bin/activate`。
3. **启动后端**：`./scripts/run-backend.sh`（默认端口 `8000`，可用 `PORT=9000 ./scripts/run-backend.sh` 修改）。

启动后：

- OpenAPI / Swagger：`http://localhost:8000/docs`
- MCP 管理页：`http://localhost:8000/mcp-admin/`

若 `.env` 中 `PTAGENT_MCP__AUTO_START_SUBPROCESS=true`（默认），后端会在启动时尝试按 `PTAGENT_MCP__ENDPOINT` 拉起 MCP Broker 子进程。若关闭自动拉起，需另开终端执行 `./scripts/run-mcp-broker.sh`，并保证端口与 `PTAGENT_MCP__ENDPOINT` 一致。

更多脚本说明见 [`scripts/README.md`](scripts/README.md)。

## 目标能力（高层）

- **Multi-Agent 编排**
  - 质谱原始数据解析 Agent
  - 肽段/蛋白鉴定与定量 Agent
  - 生物学解释与注释 Agent
  - 报告生成与合规审计 Agent
- **RAG 能力**
  - 支持对接本地知识库（实验 SOP、项目文档、数据库说明等）
  - 支持对接在线数据库（如 UniProt、KEGG 等，后续实现）
- **企业级工程化**
  - 分层架构（core / agents / rag / services / config）
  - 清晰的配置与环境管理
  - 可插拔的数据源与模型适配层

## 项目结构（计划）

- `src/`
  - `core/`：LangGraph 核心编排、graph 定义、节点抽象
  - `agents/`：不同职责的 Agent 定义（数据预处理、鉴定、定量、解释等）
  - `rag/`：RAG 管线、向量库接口、检索策略
  - `services/`：外部服务集成（LLM 服务、向量数据库、存储、消息队列等）
  - `config/`：配置管理、环境切换（dev/staging/prod）
  - `interfaces/`：与上层应用（API、CLI、批处理管线）之间的接口
- `tests/`：单元测试 & 集成测试
- `docs/`：设计文档、使用手册、API 说明

## 全局 TODO

- [ ] **搭建基础 Python 工程**
  - [ ] 明确 Python 版本（建议 3.10+）
  - [ ] 整理依赖清单（langgraph、langchain-core、向量库 SDK 等）
  - [ ] 配置 `requirements.txt` / `pyproject.toml`
- [ ] **设计核心 LangGraph 内核**
  - [ ] 定义抽象的 `Node` / `Agent` 接口
  - [ ] 设计质谱工作流的初版 graph（从原始数据到报告）
  - [ ] 规划状态管理与错误恢复机制
- [ ] **规划 Multi-Agent 协作模式**
  - [ ] 按业务职责拆分 Agent
  - [ ] 定义 Agent 之间消息/上下文协议
  - [ ] 支持基于项目/任务的会话级上下文
- [ ] **规划 RAG 子系统**
  - [ ] 选型向量库（本地/云端：FAISS / Qdrant / Milvus 等）
  - [ ] 设计知识分块策略和元数据 schema
  - [ ] 规划数据注入/更新/重建 pipeline
- [ ] **企业级能力预留**
  - [ ] 配置多环境（本地开发 / 测试 / 生产）
  - [ ] 日志 & 监控接口预留
  - [ ] 权限与审计（合规需求）接口预留

## 下一步建议

1. 在 `requirements.txt` 中锁定核心依赖版本（langgraph 及 LLM SDK）。
2. 在 `src/core` 中定义最简版的 graph kernel 接口（仅 TODO stub）。
3. 在 `src/agents` 中列出关键 Agent 类型和职责说明（README + TODO）。
4. 根据你的具体质谱平台/软件（如 MaxQuant、DIA-NN 等），在 `services` 里规划集成适配层。

