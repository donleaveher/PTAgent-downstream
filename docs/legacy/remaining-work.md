# PTAgent 关系图谱 · 剩余工作清单

> 最后更新：2026-06-17。状态对照真实代码核过，非旧分析照搬。
> 图例：✅ 真实可用 · 🟡 框架在/关键处占位 · ❌ 空/缺失/未接 · ⏸ 待 PhD 决策后再做

两条数据通路（详见 [architecture-data-pipeline.svg](architecture-data-pipeline.svg)）：
- **A 路 FILE_PIPELINE**：产鉴定数据（谱图 → 肽段/蛋白 → 图谱）
- **B 路 MCP_IO**：做增强/解读（文献、注释、RAG）

---

## 0. 本轮已完成（对账，勿重复做）

- [x] `DataType.MZTAB` 枚举 + `ingest.infer_data_type_from_filename` 的 `.mztab` 映射
- [x] `store.update_data_object_meta`（materializer 盖章用）
- [x] `get_store` → `get_data_plane_store` 全仓已统一（含 `_get_compiler`）
- [x] `loaders/casakono.py` → `casanovo.py` 改名（ImportError 已消除）
- [x] `loaders/casanovo.py::build_rows` 完整并通过 join 冒烟测试
- [x] `loaders/__init__.py` 注册表（含别名 + 子串兜底）
- [x] `materializer.py`（`materialize_run` / `materialize_run_safe`，101 行，import 已通）
- [x] Casanovo 输出格式钉死为 mzTab（🔴-3）

---

## 1. A 路：鉴定 → 图谱（当前主线）

### 1.1 图谱编排收尾 —— 最短闭环，无外部依赖，可立刻做
- [ ] **新建 `pipeline/nodes/materialize_graph.py`**：薄封装节点，从 state 取 `run_id` 调 `materialize_run_safe`
- [ ] **接进 LangGraph**：在 [graph.py](../src/application/pipeline/graph.py) 把节点插在 `execute_dag → distill_and_research` 之间（现在 `graph.py` 里 0 处 materialize）
- [ ] **补图谱层测试**：`pkg/graph` 与 materializer 目前零测试；至少补一个 loader join 单测 + materialize_run 的 status 分支测试
- [ ] **（可选）RT 入图**：[mgf.py](../src/pkg/ms_formats/mgf.py) 的 `parse_mgf_spectra` 不解析 `RTINSECONDS`（写入端 `write_spectrum_block` 会写，读端不读）→ 若 B5 要 RT，扩展读端

### 1.2 真实工具执行 —— 打通数据源头（依赖外部工具）
- [ ] **`scheduler._call_mcp_tool` 去 Mock**：[scheduler.py:207](../src/application/dag_engine/scheduler.py) 现在是随机 sleep + 假 `output_object_ids`；改成真调 [pkg/mcp/client.py](../src/pkg/mcp/client.py) 的 `call_tool_async`
- [ ] **工具输出注册成 DataObject**：当前全仓没有"把工具产物登记成 DataObject"的代码（`create_data_object` 只在 ingest/admin 调过）；要在工具执行后 `create_data_object(MZTAB, 路径)` 并 `update_run(output_object_ids=...)`
- [ ] **注册真实 Casanovo MCP 工具**：`toolCount=0`，没有任何真工具；包一个 MCP file-tool（收 input 谱图 object_id → 跑 `casanovo sequence` → 写 `.mztab` → 注册 → 返回 output id）
- [ ] **校准 loader 注册表 key**：等真工具接上，跑一次 `get_run().tool_name` 看真名，回填 `loaders/__init__.py` 的 key（现为猜测 `casanovo`/`casanovo_sequence`）

### 已就绪（A 路底座，无需动）
- ✅ ingest / DataObject / SQLite 存取 / 类型 / 目录约定
- ✅ 解析器：`mztab_casanovo.py`（带测试）、`mgf.py`（除 RT）、`mzml_write.py`
- ✅ `pkg/graph/`：schema / cypher（含 MERGE_TRUNK / 蛋白层 / GDS 推断）/ store / types
- ✅ `materializer.py` + `loaders/casanovo.py`

---

## 2. B 路：增强 / 解读（MCP_IO）

- ✅ MCP 基础设施真实（fastmcp client / broker / provider / relay）
- [ ] **`distill_and_research` 去占位**：[distill_and_research.py](../src/application/pipeline/nodes/distill_and_research.py)
  - `_mock_generate_findings`（128 行）→ 真 LLM 提炼 KeyFindings
  - `_mock_search_evidence`（158 行）→ 真调 DeepXiv/UniProt 取证
  - `_apply_filter` 的 TODO（123 行）→ 按 confidence/top_n 真过滤
- [ ] **RAG 开启**：[agent/contracts.py:73](../src/pkg/agent/contracts.py) 现为无检索占位（默认关）→ 接真实向量库/本地语料（依赖 E3 有无语料）
- 🟡 `uniprot_taxonomy.py`：经 broker 调 UniProt 已通，失败兜底占位（可保留）

---

## 3. 共用上游（规划 / 输出层）

- [ ] **`plan_workflow` 去占位**：[plan_workflow.py](../src/application/pipeline/nodes/plan_workflow.py) 占位 `ToolBroker.list_tools` + 占位 LLM 生成 WorkflowPlan
- [ ] **`generate_report` 去占位**：[generate_report.py:94](../src/application/pipeline/nodes/generate_report.py) 占位 LLM 出 Markdown 报告
- ✅ `pkg/llm/` 客户端真实（`registry` 部分 provider 抛 `NotImplementedError`，按需补）

---

## 4. 定量层（⏸ 待 A3 决策后再做）

> 设计已成形（见 [quant-data-location.svg](quant-data-location.svg) / [proteingroup-vs-sample-axes.svg](proteingroup-vs-sample-axes.svg)），但**是否做、用 LFQ/TMT/SILAC 哪种**取决于确认清单 A3。**不动 `TrunkRow`，新开对称的一层：**

- [ ] `QuantRow`（types.py）：peptidoform / sample_id / condition / intensity / channel / ratio
- [ ] `MERGE_QUANT`（cypher.py）：`MERGE (pep)-[:QUANTIFIED_IN {intensity}]->(s)`
- [ ] `GraphStore.merge_quant`（store.py）+ `Q_QUANT_BY_CONDITION` 取数查询
- [ ] 定量 loader：吃 DIA-NN/MaxQuant 报表 → `list[QuantRow]`；materializer 多调一步 `merge_quant`
- [ ] 差异分析（解释 Agent）：按 `Sample.condition` 分组 → log2FC / q 值

---

## 5. 部署

- [ ] **Neo4j 实例 + GDS 插件**：`INFERENCE_STEPS` 的 `gds.*` 需 Graph Data Science 插件，光装驱动会报"未知过程"（确认清单 E1）
- [ ] 连接配置：`PTAGENT_GRAPH__URI` / `__PASSWORD` 等（默认 `bolt://127.0.0.1:7687`）

---

## 6. 待 PhD 决策（阻塞项，见 [phd-confirmation-checklist.html](phd-confirmation-checklist.html)）

- [ ] **A 组（先锁）**：de novo vs DB 搜索 / DDA vs DIA / 定量策略 / 上游工具 → 决定蛋白层、定量层挂不挂
- [ ] **B1/B2**：Casanovo 部署工具实际吐标准 `.mztab`？真实 `tool_name`？
- [ ] **D2**：报告受众 QC / 生物学解读 → 决定要不要展开 B 路解释层
- [ ] **E1**：Neo4j 是否装 GDS

---

## 7. 建议执行顺序（最短闭环优先）

1. **A1.1 图谱编排收尾**（materialize_graph 节点 + 接线 + 测试）——纯本地、最确定，做完 `mztab → 图` 这段就能在测试里端到端通。
2. **A1.2 真实工具**（scheduler 去 Mock + 注册输出 DataObject + 包 Casanovo MCP 工具）——打通真实数据源头，A 路真正跑起来。
3. **共用 3**（plan / report 去占位）——让主 pipeline 不靠 Mock。
4. **B 路 2**（distill / RAG）——增强解读。
5. **定量层 4 + 部署 5**——待 PhD 锁 A3/E1 后做。

> 当前最该先动：**第 1 步**（无外部依赖、无 PhD 阻塞）。
