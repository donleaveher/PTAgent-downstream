# 下游知识层 · 代码阅读指南

> **给谁看**：负责"下游知识层"的人，想**读懂已写的代码**（不是规划下一步）。
> **核心原则**：**按数据的旅程读，不按清单的 ⬜ 读。** `IMPLEMENTATION-CHECKLIST.md` 的 ⬜
> 是"还要建什么"（很多是未来/卡外部的活），**不是**已有代码的地图。
> **配套**：[architecture.svg](architecture.svg)（结构图）、[evidence-model.svg](evidence-model.svg)（证据分级）、
> [INPUT-CONTRACT.md](INPUT-CONTRACT.md)（输入契约）。

---

## 0. 先建立心智模型（读代码前花 5 分钟）

### 0.1 三层架构（依赖只能从上往下）

```
router/         HTTP 端点（薄；URL → 调一个服务，复杂逻辑不在这）
   ↓
application/     应用服务（读仓库 → 算 → 写回仓库；一个文件一件事）
   ↓
pkg/             领域模型 + 纯引擎 + 存储实现（不依赖 application/router）
```

读代码就是**从 application 的某个服务进去，顺着 import 往 pkg 里钻一层**，看它用的纯引擎。

### 0.2 数据的旅程（这就是阅读顺序）

```
输入(蛋白/肽/分组/背景 + 定量)
   → 差异分析(谁变了)
   → 富集(变的蛋白扎堆在哪些疾病)
   → 基础注释 + CTD 疾病结论(公共事实)
   → 结构类比假说(跨物种借疾病)
   → deep-search(文献验证假说 → 升结论/降伪理)
   → 投影成知识图谱
   → 冻结成只读快照
   → 出分层报告
```

### 0.3 一条贯穿全场的主线：**证据分级**（最重要的概念）

每条知识都带一个 `evidence_level`，三态：

| 级别 | 含义 | 谁产生 |
|---|---|---|
| `CONCLUSION` | 公共事实/直接证据 | UniProt 基础注释、CTD 基因→疾病直接命中 |
| `HYPOTHESIS` | 推导猜测 | 结构类比"借"来的疾病关联 |
| `REFUTED` | 已被反驳的伪理 | deep-search 找到反证 |

**"认知态跃迁"** = deep-search 把 `HYPOTHESIS` → `CONCLUSION`（找到支持）或 → `REFUTED`（找到反证）。
看懂这条三态线，整个系统的"为什么"就通了。详见 [evidence-model.svg](evidence-model.svg)。

### 0.4 两条必须记住的铁律

- **MySQL 是事实唯一来源；图谱只是投影**（Q5）。改事实改 MySQL，图谱重投即可。
- **冻结快照是只读的**；报告只读 `snapshot.manifest`，**不碰活库** —— 所以冻结后再改事实，旧报告不变。

---

## 1. 哪些是"你的"代码（约 15 个文件），哪些跳过

仓库里 `src/` 下有 ~75 个 `.py`，**你的下游知识层只占约 15 个**。其余是原始基座或已废弃支线。

### 1.1 你的文件（本指南覆盖的全部）

- `pkg/experiment/`：模型 + 仓库 + schema + 摄入（**地基**）
- `pkg/analysis/`、`pkg/disease/`、`pkg/structure/`、`pkg/graph/`、`pkg/deep_search/`：各步的纯引擎
- `application/{experiment,analysis,knowledge,graph,report,orchestration}/`：应用服务
- `router/downstream.py`：HTTP 入口

### 1.2 **不要读**（会把你淹没）

| 跳过 | 是什么 |
|---|---|
| `application/pipeline/`（注意：不是 orchestration） | **旧的** Mock 管线（planner/scheduler/nodes），已 deprecated，待删 |
| `application/dag_engine/`、`application/agent/`、`application/workflow/` | 旧基座/支线 |
| `pkg/{llm,mcp,agent,ms_formats,protein_db,embedding}/` | 原始基座（LLM/MCP/谱图/序列库），不属于知识层 |

> **判别法（golden rule）**：**从 [pipeline.py](../src/application/orchestration/pipeline.py) 出发顺着 import 走，走不到的就别读。** 走不到 = 基座或废弃 = 与你无关。

---

## 2. 阅读路径（按这个顺序，逐文件）

### 阶段 0 · 两个锚文件（先读这两个，30 分钟拿下 70%）

| # | 文件 | 读什么 / 注意什么 |
|---|---|---|
| 1 | [types.py](../src/pkg/experiment/types.py) | **所有名词。** 每个数据形状：`ExperimentBundle`、`ProteinQuantification`、`DifferentialResult`、`MetaAnnotation`（带 `evidence_level`）、`AnnotationHistory`、`ExperimentSnapshot`、`ReportRecord`。这是全系统的词汇表。注意 `StrictModel`（`extra=forbid` + `str_strip_whitespace`）。 |
| 2 | [pipeline.py](../src/application/orchestration/pipeline.py) | **所有动词 + 顺序。** 看 `STEP_ORDER` 和十个 `_step_*` 函数 —— 每个就 ~5 行，调一个服务。这一个文件就是整条流程的目录。 |

> 只读这两个文件，你就能在脑子里跑通整条流程。下面只是逐站深入。

### 阶段 1 · 存储（你能对数据做什么）

| # | 文件 | 读什么 |
|---|---|---|
| 3 | [repository.py](../src/pkg/experiment/repository.py) | 先读 `ExperimentRepository` **Protocol**（操作清单：`save_bundle`/`list_proteins`/`add_annotations`/`add_differentials`/`save_snapshot`/`save_report`…），再读下面的 `InMemoryExperimentRepository`（**可读的参考实现**，dict 存储）。**[mysql_store.py](../src/pkg/experiment/mysql_store.py) 先跳过** —— 同样的操作，只是换成 SQL。 |

### 阶段 2 · 输入（数据怎么进来）

| # | 文件 | 读什么 |
|---|---|---|
| 4 | [ingest.py](../src/pkg/experiment/ingest.py) | 极短。`ingest_experiment_payload`：dict → `ExperimentBundle` 校验 → `save_bundle`。 |
| 5 | [quantification_ingest.py](../src/application/experiment/quantification_ingest.py) | 定量摄入：校验每行 `protein_id`/`group_id` 属于该实验 → 整批原子 → 幂等 upsert。 |
| 6 | [downstream.py](../src/router/downstream.py) | 所有 HTTP 端点。每个都很薄：`_require` 查实验存在 → 调一个服务 → 包成 JSON。先扫一遍有哪些端点。 |

### 阶段 3 · 顺着管线走十步（**正餐**）

每一步 = `pipeline.py` 里一个 `_step_*` → 一个应用服务。按顺序读服务文件：

| 步 | 服务文件 | 读什么（输入 → 输出 + 关键点） |
|---|---|---|
| `differential` | [differential_analysis.py](../src/application/analysis/differential_analysis.py) | 读 `list_quantifications`+`list_groups`（按 role 自动选 case/control）→ 调引擎 [pkg/analysis/differential.py](../src/pkg/analysis/differential.py)（log2FC + Welch t + BH，无重复退化为 fold-change）→ 写 `DifferentialResult`。**无定量 → 无差异 → 后面假说也空。** |
| `enrichment` | [enrichment_analysis.py](../src/application/analysis/enrichment_analysis.py) | study = 差异蛋白基因，**背景 = 全部鉴定蛋白基因（Q1）**，基因集取自已落库的 CTD 结论 → 调 [pkg/analysis/enrichment.py](../src/pkg/analysis/enrichment.py)（超几何 + BH）→ 写 `EnrichmentRecord`（带 study/background checksum，可复现）。 |
| `base_annotation` | [protein_enrichment.py](../src/application/knowledge/protein_enrichment.py) | **全部**蛋白 → UniProt 源（`pkg/annotation`）→ 写 `MetaAnnotation(CONCLUSION, target=protein)`。 |
| `ctd_disease` | [disease_annotation.py](../src/application/knowledge/disease_annotation.py) | **全部**蛋白对应基因 → CTD 源（`pkg/disease`）直接命中 → 写 `MetaAnnotation(CONCLUSION, target=gene)`。与上一步对称（Q3 双节点：蛋白属性 vs 基因疾病）。 |
| `hypothesis` | [hypothesis_generation.py](../src/application/knowledge/hypothesis_generation.py) | **仅差异蛋白**（Q2）：结构近邻(M2, `pkg/structure` Foldseek) → 近邻 gene（gene resolver）→ 近邻 gene 的 CTD 疾病(M1) → **借**过来 → 写 `MetaAnnotation(HYPOTHESIS, target=protein)`。跨物种由结构近邻天然完成；RRF 融合重排（结构分+覆盖度）。蛋白自身已有直接结论的疾病不重复出假说。 |
| `kg_projection` | [project_kg.py](../src/application/graph/project_kg.py) | 读蛋白/基因/注释/差异 → 投成两层图（通用 KG + 实验工作区）经 `GraphStore`（`pkg/graph`）。节点带 `mysql_ref`，边带 `evidence_level`。幂等可重投。 |
| `deep_search` | [deep_search.py](../src/application/knowledge/deep_search.py) | 对每条 `HYPOTHESIS` 注释建检索任务 → 文献源 → `decide_verdict`（[pkg/deep_search/verdict.py](../src/pkg/deep_search/verdict.py) 纯状态机）→ 支持升 `CONCLUSION`/反证降 `REFUTED`/无证据留 `HYPOTHESIS`；追加 `AnnotationHistory`（确定性 id，幂等可回放）。还有 `override_hypothesis_verdict`（人工覆盖）。 |

### 阶段 4 · 输出（归档 + 报告）

| # | 文件 | 读什么 |
|---|---|---|
| `freeze` | [freeze.py](../src/application/experiment/freeze.py) | 冻结前检查（每条蛋白级假说须已被 deep-search 处理过）→ 从仓库拼**确定性 manifest**（上下文/计数/证据分布/全量注释+历史+差异+富集/图摘要/版本/请求 hash）→ 稳定 SHA-256 → `ExperimentSnapshot(FINAL)`。版本唯一双重阻止覆盖。`verify_snapshot_integrity` 重算 checksum 防篡改。 |
| `report` | [layered_report.py](../src/application/report/layered_report.py) | `generate_experiment_report`：**只读 `snapshot.manifest`** → 校验完整性 → 渲染分层 Markdown（设计/差异/富集/结论/假说/伪理/未决 + 附录），每条带 `annotation_id`+来源+版本。`persist_experiment_report`：落库 `ReportRecord`（幂等 upsert，checksum 自洽）。 |

读完阶段 3+4，你已经看完整个知识层。

---

## 3. 五个反复出现的横切概念（认出它们，就不迷路）

1. **证据分级三态线**（见 §0.3）：`CONCLUSION`/`HYPOTHESIS`/`REFUTED`，deep-search 推动跃迁。整个系统围着它转。

2. **幂等无处不在**：`stable_annotation_id`（[identity.py](../src/pkg/experiment/identity.py)）、`stable_history_id`、确定性 `report_id`、仓库 upsert。**同一事实重跑不产生重复行** —— 这就是管线能断点续跑/重放的原因。看到 `stable_*` 就知道"这是为了重跑不重复"。

3. **依赖注入（DI）**：每个服务都接一个可注入的源（`annotation_source`/`disease_source`/`structure_provider`/`gene_resolver`/`literature_source`/`graph_store`），默认 `get_*()`。**测试注入内存/假源，生产注入真实源 —— 同一份代码两用。** 这就是为什么能离线全绿却还没连真库。

4. **来源 + 版本 + checksum**：注释带 `provenance`（来源库版本）；富集带集合 checksum；快照带 manifest checksum；报告 `sha256(content)==checksum`。一切为**可复现 + 可审计 + 防篡改**。

5. **Q 决策**：代码注释里的 `Q1/Q2/Q3/Q4/Q5` 指 [IMPLEMENTATION-CHECKLIST.md](IMPLEMENTATION-CHECKLIST.md) §2 的既定决策（如 Q2=只对差异蛋白做重点分析）。看到 `Q?` 去那查。

---

## 4. 怎么真正读完（可执行的三轮计划）

- **第 1 轮（~1 小时，骨架）**：阶段 0 两个锚文件 + 阶段 1 仓库 Protocol。读完能复述整条流程和所有数据形状。
- **第 2 轮（~2 小时，正餐）**：阶段 3 十步，每步**配着它的测试一起读**（测试是能跑的示例）：
  - `differential` → [test_differential_v3.py](../tests/test_differential_v3.py)
  - `enrichment` → [test_enrichment_v3.py](../tests/test_enrichment_v3.py)
  - `hypothesis` → [test_hypothesis_generation_v3.py](../tests/test_hypothesis_generation_v3.py)
  - `deep_search` → [test_deep_search_v3.py](../tests/test_deep_search_v3.py)
  - 整条管线 → [test_pipeline_v3.py](../tests/test_pipeline_v3.py)（`_seed()` 是最好的"输入长什么样"样例）
- **第 3 轮（~1 小时，输出 + 边界）**：阶段 4 freeze+report（配 [test_layered_report_v3.py](../tests/test_layered_report_v3.py)）+ 阶段 2 输入/API（配 [test_downstream_api_v3.py](../tests/test_downstream_api_v3.py)）。

> **跑起来看**：`.venv/bin/python -m pytest tests/test_pipeline_v3.py -q`。想看某步输出，在 `_step_*` 里 print 返回的 summary dict。

---

## 5. 关于那份"乱"的清单

[IMPLEMENTATION-CHECKLIST.md](IMPLEMENTATION-CHECKLIST.md) 的 **⬜ 是"待建"，不是"待读"**。读代码时**整段忽略 ⬜**；✅ 项就对应本指南的文件。

想**建东西**（不是读）时，⬜ 分四桶，只有一桶能单干：

| 桶 | 例子 | 能否现在做 |
|---|---|---|
| ② 纯代码 | 鉴权/审计、跨实验比较、报告 PDF | ✅ 随时 |
| ③ 卡外部 | 真连 MySQL/Neo4j/Foldseek/UniProt/文献源 | ⛔ 等 B 组 |
| ④ 运维 | 健康检查、日志、指标、备份 | 🟡 |
| ⑤ 清理 | 删旧 `application/pipeline`、`dag_engine` | 🟡 |
