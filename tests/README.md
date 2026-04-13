# `tests`：测试用例

本目录用于放置项目的单元测试与集成测试，确保 LangGraph 内核、各个 Agent 以及 RAG 子系统在迭代中保持稳定。

## 布局（分组示例）

- **`mcp/basic/`** — 与 `src/mcp_tools/basic` 对应，如 [`test_peptide.py`](mcp/basic/test_peptide.py)

仓库根 **`pytest.ini`** 已设置 `pythonpath = src`，IDE（VS Code / PyCharm）在测试文件上 **Run Test** 时一般可直接发现 `mcp_tools` / `pkg`，无需再手写 `PYTHONPATH`。

## TODO 列表

- [ ] **测试框架与结构**
  - [ ] 确定测试框架（默认使用 `pytest`）。
  - [ ] 规划测试命名与分层结构（如 `test_core_*.py`、`test_agents_*.py`、`test_rag_*.py`）。
- [ ] **核心内核测试**
  - [ ] 为最小 demo graph 编写单元测试（节点执行顺序、状态传递等）。
  - [ ] 为 `BaseAgent` 抽象实现基础行为测试。
- [ ] **RAG 子系统测试**
  - [ ] 为向量库封装编写基础 CRUD/检索测试（使用小样本数据）。
  - [ ] 为检索策略编写简单的契约测试（例如：能检索到预期文档）。
- [ ] **业务流程集成测试（后续）**
  - [ ] 基于一个简单的 demo 数据集，验证端到端流程是否跑通（从输入数据到报告草稿）。

