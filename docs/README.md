# `docs`：文档与设计说明

本目录用于存放项目相关文档，包括：

- 系统架构设计说明
- Agent 设计与工作流说明
- RAG 知识库与数据流设计
- 部署与运维指南

## 建议文档清单

- `architecture.md`：整体架构与模块关系图（core / agents / rag / services / interfaces）。
- `workflow-proteomics.md`：典型质谱-蛋白质组学分析流程与对应的 Agent/graph 设计。
- `rag-design.md`：知识源类型、索引方案、检索策略等。
- `deployment.md`：开发/测试/生产的部署方式与依赖。

## TODO 列表

- [ ] **高层架构文档**
  - [ ] 绘制并说明 LangGraph 内核与各模块关系。
  - [ ] 说明 Multi-Agent 与 RAG 如何协同。
- [ ] **质谱业务流程文档**
  - [ ] 梳理当前你们实验室/公司真实使用的质谱分析流程。
  - [ ] 将流程节点与 Agent/graph 进行一一对应。
- [ ] **运维与部署**
  - [ ] 明确依赖服务（LLM、向量库、数据库、存储等）的部署方式。
  - [ ] 说明日志、监控、告警的接入方案（预留）。

