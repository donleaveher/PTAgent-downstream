# PTAgent 项目规格（Spec）

> 版本：**v3.1 · 2026-06-21**（补充本次实验 KG 工作区与实验数据库归档生命周期）。本稿**取代** [`legacy/project-spec.md`](legacy/project-spec.md)（v2 及更早，"谱图进报告出 / KNN=序列相似 / 知识不入图"的旧框架已整体作废）。
> 权威性：与 [`PROJECT-STATUS.md`](PROJECT-STATUS.md) 同级——**PROJECT-STATUS 是交接入口与路线图，本 spec 是字段级实现契约**。二者若冲突，机制定义听本 spec、进度与优先级听 PROJECT-STATUS §8。
> 配图：[`architecture.svg`](architecture.svg)（总览）· [`evidence-model.svg`](evidence-model.svg)（三态证据）。
> 标注：问题与决策记为 **Q1–Q6**（定义见 [PROJECT-STATUS §9](PROJECT-STATUS.md)）；✅=已定，⬜=待定，🟨=当前暂缓但保持扩展通道。
> 实施进度：全部任务与完成状态统一见 [`IMPLEMENTATION-CHECKLIST.md`](IMPLEMENTATION-CHECKLIST.md)。

---

## 1. 目标与定位

本项目负责**下游知识层**：拿到**已鉴定**的肽/蛋白 + 实验背景，做 **知识富集 → 关联解释 → 证据分级**，构建通用 KG 与可变的本次实验 KG，经 deep-search 闭环后把最终状态冻结到独立的**实验数据库**，并生成分层报告。

> 一句话：给已鉴定蛋白附加**带证据等级（结论/假说/伪理）的 Meta**，构建可复用的通用知识图谱与本次实验图谱，差异（case vs control）为核心。

---

## 2. 范围边界

**在范围内（下游）：**
1. 解析输入三件套（§4），结构化落 MySQL。
2. **任务一**：建若干**通用知识图谱**（蛋白-疾病 / 属性 / 物种…），对鉴定蛋白做**证据分级注释**。
3. **任务二**：建**本次实验知识图谱**（输入 + 补的 Meta 的关联图）。
4. **差异分析**：组间比较 → 差异蛋白集 → 富集/外推。
5. **deep-search**：验证假说，驱动认知态跃迁，回写 evidence_level。
6. **报告**：按 结论/假说/伪理 分层。
7. **实验归档**：将验证完成的本次实验 KG 冻结为只读、可复现、带版本的快照，写入与通用知识库逻辑隔离的实验数据库。

**非目标（上游，给定/无感知，勿实现、勿从 `legacy/` 回流）：**
- ❌ 谱图采集、Casanovo de novo、查库归属、蛋白推断、novelty 判定
- ❌ `materializer` + loaders、真实工具集成（scheduler 去 Mock）、`protein_db`、`db_assign`
- ❌ 把 KNN 当**序列**相似（新框架 KNN = **结构**相似）
- ❌ 自己写 UniProt REST/TSV（改调师兄封好的 MCP 工具）

> 输入边界 = **已鉴定、已标注的肽/蛋白表 + 背景文本**；上游"谱图→肽→蛋白"如何得到，与本层无关。
> **解释范围（Q2✅）**：全部已鉴定蛋白进入数据平面和本次实验 KG，并接受 UniProt/CTD 直接命中的基础注释；只有差异蛋白进入富集、Foldseek 结构 KNN、假说生成和 deep-search 深度解释，报告正文也以差异蛋白为重点。非差异蛋白保留为实验背景和可追溯节点，不展开昂贵的推理链。

---

## 3. 术语

| 术语 | 定义 |
|---|---|
| **三件套** | 输入：实验背景文本 + 标注肽段集 + 蛋白集（§4） |
| **通用 KG** | 从公共库建的、**跨实验可复用**的知识底座（"字典"） |
| **本次实验 KG / Experiment Workspace KG** | 本批输入 + Meta 整合的**实例化工作图**（"这次的故事"）；处于实验工作区，deep-search 期间允许变化 |
| **实验数据库 / Experiment DB** | 与通用知识库逻辑隔离的实验结果库；统一存放各实验冻结后的只读 KG 快照、证据链、报告及版本信息，不为每个实验单独创建数据库 |
| **实验 KG 快照** | 本次实验 KG 完成验证后的不可变归档版本；以 `experiment_id + snapshot_version` 标识，修订时创建新版本而非覆盖 |
| **Meta** | 附加到蛋白/基因上的一条带证据等级的属性（§6） |
| **结论 / 假说 / 伪理** | 证据三态（evidence_level），见 §6 |
| **结构 KNN** | 用 Foldseek 在 AlphaFold DB 上做的**结构相似**近邻检索（非序列、非网络） |
| **双节点（Protein/Gene）** | 图谱同时建蛋白与基因两类节点，`(Protein)-[:ENCODED_BY]->(Gene)` 相连；结构/属性挂蛋白、疾病/富集挂基因（Q3✅） |

---

## 4. 输入规格（三件套）

> 字段名为约定（落 MySQL 见 §8）；`?` = 可选。粒度问题见 **Q3**。

### 4.1 实验背景（ExperimentContext，结构化抽取）

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_text` | text | 原始背景文本（保留） |
| `disease` | list[str] | 疾病，例 `["脑缺血再灌注损伤(CIRI)"]` |
| `pathway` | list[str] | 通路，例 `["Jak2/Stat3"]` |
| `organism` / `taxon_id` | str / int | 物种，例 大鼠 `Rattus norvegicus / 10116` |
| `assay` | str | 例 `DIA 差异蛋白质组` |
| `design` | obj | 分组设计（见 4.3 Group） |

> 背景是**指挥棒**：disease/pathway/organism 决定哪些通用 KG/关联才相关，并作报告锚点。

### 4.2 标注肽段（Peptide）

| 字段 | 类型 | 说明 |
|---|---|---|
| `peptide_id` | str | 主键 |
| `peptidoform` | str | 带修饰序列为 key；`stripped_sequence` 作属性 |
| `protein_id` | str | → 1 蛋白（FK，§4.4） |
| `spectrum_ids` | list[str] | → 1 或多张谱图 |
| `confidence` | float | 鉴定置信度 |
| `group_label` | str | 所属组别（FK → Group，§4.3）——**差异分析关键** |
| `abundance?` | float | 定量强度（具体定量字段在 L2 细化，依赖 **Q1**） |
| `meta?` | dict | 亲和力 / 保留时间 … |

### 4.3 组别（Group）— 差异核心

| 字段 | 类型 | 说明 |
|---|---|---|
| `group_id` | str | 主键 |
| `label` | str | 例 `tMCAO+shNC` / `tMCAO+shJak2` |
| `role` | enum | `case` / `control` |

### 4.4 蛋白（Protein）

| 字段 | 类型 | 说明 |
|---|---|---|
| `protein_id` | str | 主键 |
| `accession` | str | UniProt accession（接 MCP / 结构检索用） |
| `gene` | str | protein→gene 映射，锚定 `Gene` 节点（CTD 查询用；Q3✅ 双节点，必填） |
| `organism` / `taxon_id` | str / int | 物种 |
| `peptide_ids` | list[str] | → 若干肽 |
| `meta?` | dict | 输入自带 Meta |

---

## 5. 数据库与证据语义（三库，师兄已定）

| 库 | 角色 | 接入形式 | 证据语义 |
|---|---|---|---|
| **UniProt** | 蛋白属性：结构域 / 组织表达 / 物种 | **调师兄的 MCP 工具**，在其上扩展建 KG，不自写 REST/TSV | 直接注释 = **结论** |
| **CTD** | 蛋白-疾病 关联 | 可下载，建蛋白-疾病 KG | 直接命中（**curated/marker**）= **结论**；化学物推断的间接关联降为弱证据 |
| **AlphaFold DB** | 结构 → 找 K 近邻 | **Foldseek** 在 AF 全库做结构检索 | 结构近邻借其 CTD 关联 = **假说**；**物种无关 → 大鼠→人天然桥接** |

> **关键**：KNN = **结构相似**（不是序列、不是网络）。跨物种桥由结构 KNN 自带，**不另建同源库**。
> **UniProt MCP 接入契约**：工具名、accession 参数名和批大小由 `PTAGENT_ANNOTATION__*` 配置；返回经适配器统一为 `ProteinAnnotationFact`，再以确定性 ID 写入实验事实库。MySQL 写入成功后才允许后续 Neo4j 投影。
> **免疫维度（Q6🟨）**：当前不单独建设或批量导入专用免疫数据库，先使用 UniProt GO、CTD 与 deep-search；但该能力不关闭，保留后续数据源、Schema 和导入扩展通道。

**免疫扩展契约（预留、不在当前 MVP 实现）：**
- 预留节点：`ImmuneProcess`、`ImmuneCell`、`Cytokine`、`ImmunePathway`。
- 预留关系：`INVOLVED_IN`、`ACTIVE_IN`、`REGULATES`、`SECRETES/RESPONDS_TO`；所有关系沿用 `source + evidence_level + provenance`。
- 预留数据源适配器接口（如 `ImmuneKnowledgeProvider`），后续专用数据库通过适配器接入，不改动现有业务流程和 `GraphStore` 契约。
- 当前 deep-search 补到的免疫机制属于本次实验判断，落实验工作区并随快照归档，不自动写回通用 KG。
- 后续是否启用专用免疫库，根据真实项目中免疫查询覆盖率、deep-search 重复补证成本和细胞类型/细胞因子精度需求另行决策。

---

## 6. 证据三态模型（核心机制）

### 6.1 evidence_level 枚举

| 态 | 枚举 | 含义 | 来源 |
|---|---|---|---|
| **结论** | `CONCLUSION` | 有确切证据 | 库直接命中（UniProt 直接注释 / CTD curated-marker）/ deep-search 直接证据 |
| **假说** | `HYPOTHESIS` | 有逻辑推导、待验证 | 结构 KNN 外推（蛋白本身未收录，但其结构近邻被收录） |
| **伪理** | `REFUTED` | 被证伪的假说（留档，不丢） | deep-search 找到反证 |

### 6.2 Meta 记录（证据分级注释的最小单元）

```
MetaAnnotation {
  experiment_id:   str                      # 本次实验作用域；实验判断不得污染通用 KG
  target:          protein_id | gene_id     # 注释对象（Q3✅ 双节点）
  target_type:     protein | gene           # 结构域/组织/物种→protein；疾病(直接)→gene；疾病(假说,结构外推)→protein
  attribute:       str                      # 如 "disease:脑缺血" / "domain:SH2" / "tissue:brain"
  value:           any
  evidence_level:  CONCLUSION | HYPOTHESIS | REFUTED
  source:          "UniProt" | "CTD" | "Foldseek-KNN" | "deep-search"
  derivation:      obj                      # 假说: {neighbors:[accession...], via_gene, scores}；结论: {ref}
  provenance:      {ts, query, db_version, general_kg_ref}
}
```

### 6.3 认知态状态机（deep-search 驱动）

```
假说 --(直接证据)--> 结论
假说 --(无证据)----> 假说（保持）
假说 --(反证)------> 伪理（留档）
```

---

## 7. 处理流程

| # | 阶段 | 输入 | 处理 | 输出 |
|---|---|---|---|---|
| 0 | 解析输入 | 三件套 | 结构化抽取背景 + 肽/蛋白/组别落 MySQL | 输入表（§8.1） |
| 1 | **任务一·全量基础注释** | 全部已鉴定蛋白 | UniProt(MCP) 取属性=结论；CTD 直接命中=结论；全部蛋白落基础节点和 Meta | 全量基础 Meta |
| 2 | **差异分析 + 深度解释** | 组别 + 定量 | case vs control → 差异蛋白集；以本次鉴定蛋白池为背景做富集；只对差异蛋白执行 Foldseek 结构 KNN→借 CTD=假说，并进入 deep-search 队列（Q1/Q2✅） | 差异蛋白集 + 富集结果 + 假说 |
| 3 | **任务二·本次 KG** | 输入 + Meta | 按 Q4 混合模式整合关联图（带 evidence_level + 组间差异） | 本次实验 KG（§8.2） |
| 4 | **deep-search** | 假说 | 在线找证据，按 §6.3 跃迁，回写 evidence_level | 更新后的本次 KG |
| 5 | **冻结归档** | 验证完成的本次 KG | 关闭或标记未决任务，校验溯源字段，生成不可变版本并写入实验数据库 | 实验 KG 快照（§8.3） |
| 6 | **报告** | 已冻结的实验 KG 快照 | 按 结论/假说/伪理 分层呈现 | 与快照版本绑定的交付报告 |

---

## 8. 数据模型与存储

**分工原则（Q5✅）**：**MySQL 是事实唯一来源**，保存输入、定量、Meta、证据正文与状态历史；**Neo4j 是关系查询后端**，只保存节点/关系、必要索引字段和 `mysql_ref`，重数据不进图。业务代码通过 `GraphStore` 接口访问 Neo4j，避免直接绑定具体驱动和 Cypher 细节。

### 8.1 MySQL · 数据平面（关系/明细）

| 表 | 关键列 |
|---|---|
| `experiment_context` | current_request_id, raw_text（当前镜像）, disease, pathway, organism, taxon_id, assay |
| `experiment_request` | request_id, experiment_id, version, raw_question, request_payload, content_hash, supersedes_request_id；只追加不覆盖 |
| `experiment_input_artifact` | request_id, object_id, input_role, filename, file_hash, upstream software/version |
| `experiment_context_revision` | request_id, structured_context, parser/model version, confirmation status, confirmed_by |
| `experiment_group` | experiment_id, group_id, label, role, meta |
| `peptide` | peptide_id, peptidoform, stripped_sequence, protein_id, spectrum_ids, confidence, group_label, abundance?, meta |
| `protein` | protein_id, accession, gene, taxon_id, meta |
| `protein_quantification` | experiment_id, protein_id, group_id, sample_id, abundance, meta |
| `differential_result` | experiment_id, protein_id, case_group_id, control_group_id, log2fc, p, q, direction, is_differential |
| `meta_annotation` | id, target, attribute, value, **evidence_level**, source, derivation, provenance |
| `db_cache` | 公共库下载缓存（CTD / UniProt / AlphaFold） |
| `deep_search_evidence` | hypothesis_id, verdict(支持/无/反对), refs, ts |
| `annotation_history` | annotation_id, from_level, to_level, verdict, evidence_ref, changed_at；保留认知态跃迁，不覆盖历史 |

> 由师兄提供的数据平面**从 SQLite 升级到 MySQL**。

### 8.2 Neo4j · 知识图谱层

**通用 KG（复用·字典）· Q3✅ 双节点（Protein + Gene）**
- 当前节点：`Protein`（结构/属性/输入锚点）/ `Gene`（疾病/富集锚点）/ `Disease` / `Taxon` / `Domain` / `Tissue`；免疫扩展节点按 Q6 保留 Schema/适配器通道，当前不批量实例化
- **缝合边**：`(Protein)-[:ENCODED_BY]->(Gene)`（蛋白↔基因，跨层级那一跳）
- **蛋白级边**：`(Protein)-[:HAS_DOMAIN]->(Domain)`、`(Protein)-[:EXPRESSED_IN]->(Tissue)`、`(Protein)-[:STRUCTURAL_NEIGHBOR {score}]->(Protein)`（Foldseek，物种无关）
- **基因级边**：`(Gene)-[:ASSOCIATED_WITH {evidence_level, source}]->(Disease)`（CTD，直接命中=结论）
- **假说挂载**：结构近邻借疾病 → 挂在 `Protein` 上，路径 `Protein-STRUCTURAL_NEIGHBOR->Protein-ENCODED_BY->Gene-ASSOCIATED_WITH->Disease`，evidence_level=假说

**本次实验 KG（实例·故事；实验工作区中的可变状态）**
- 节点：`Experiment` / `Protein` / `Peptide` / `Group` / `Annotation`。
- 边：`(Peptide)-[:BELONGS_TO]->(Protein)`、`(Protein)-[:IN_GROUP]->(Group)`、`(Protein)-[:DIFFERENTIAL {log2fc, q, direction}]->(Group)`。
- 全部已鉴定蛋白保留基础节点与直接注释；差异蛋白才展开富集、结构近邻、假说和 deep-search 证据路径，以控制图规模和噪声。
- 公共 `Protein/Gene/Disease` 实体和稳定关系通过 `canonical_id/general_kg_ref` **引用**通用 KG，不复制成可修改的公共事实。
- 本次实验产生的差异、假说、`evidence_level`、deep-search 裁决与状态历史**实体化在 `Annotation` 中**，并绑定 `experiment_id`；同一公共关系在不同实验中可以有不同状态，互不污染。

**互链**：每个图节点带 `mysql_ref`（如 protein_id）指回 MySQL 明细。
**衔接方式（Q4✅）**：采用混合模式——公共知识引用通用 KG，本次实验判断落本次实验 KG；归档时冻结本次状态及其所引用的通用 KG 版本和来源关系 ID，而不是把实验判断写回通用 KG。

### 8.3 实验数据库 · 冻结归档层

实验数据库与通用知识库**逻辑隔离**，统一管理全部实验快照；不采用“每个实验一个数据库”。本次实验 KG 在工作区中可变，完成验证后才归档：

```
通用 KG（公共事实，持续更新）
        ↓ 引用
本次实验 KG（工作区，可变）
        ↓ deep-search 完成 + 冻结
实验数据库（只读快照，可版本化）
        ↓
报告 / 审计复现 / 跨实验比较
```

**快照主记录：**

```
ExperimentSnapshot {
  experiment_id:       str
  snapshot_id:         str
  snapshot_version:    str       # 例 1.0 / 1.1 / 2.0
  status:              FINAL | SUPERSEDED
  general_kg_version:  obj       # CTD / UniProt / AlphaFold 各自版本
  pipeline_version:    str
  model_version:       str?
  query_and_params:    obj       # Foldseek top-k/阈值、过滤和实体映射规则
  frozen_at:           datetime
  checksum:            str
  report_artifact_ref: str
}
```

**归档规则：**
1. deep-search 任务必须已完成，或明确记录为“未决”；不能静默丢弃。
2. 快照包含实验输入引用、差异结果、最终 KG、Meta、完整证据状态历史、公共知识来源 ID/版本、参数和报告引用。
3. 快照一经 `FINAL` 即只读；发现新证据或使用新版通用 KG 重分析时创建新版本，不覆盖旧版本。
4. 归档后的实验结论仍受物种、模型、组织、处理和时间点约束，**不得自动提升为通用 KG 的公共事实**；进入通用 KG 需要独立审核流程。
5. 跨实验比较通过统一 `canonical_id` 对齐实体，并显式选择快照版本。

实验数据库采用与通用知识库隔离的 MySQL schema/逻辑库保存快照主记录和明细，并在 Neo4j 中使用独立数据库或严格的实验归档命名空间保存冻结图；具体物理部署可按环境调整，但权限、写入路径和数据生命周期必须隔离。所有访问经过存储接口，不能让业务代码依赖某一种部署方式。

---

## 9. 输出规格

1. **带证据等级的蛋白 Meta**：`MetaAnnotation` 集合（§6.2），每条可溯源。
2. **本次实验关联图**：§8.2 的本次 KG，讲清"差异蛋白 × 关联 × 证据级"。
3. **实验 KG 快照**：§8.3 的只读归档版本，可审计、可复现、可用于跨实验比较。
4. **分层报告**：结论级（确证）/ 假说级（待验）/ 伪理级（被证伪），各带证据引用并绑定快照版本。

---

## 10. 开放问题与决策登记（活登记；详见 [PROJECT-STATUS §9](PROJECT-STATUS.md)）

> ✅=已定 · ⬜=待定 · 🟨=当前暂缓但保持扩展通道。本表为决策**单一真源**。

| Q | 问题 | 决策 | 影响的本 spec 处 |
|---|---|---|---|
| **Q1** | "统计学角度" + 富集背景集 | ✅ **富集分析**；**背景集 = 本次鉴定蛋白池**（非全基因组——质谱检测有丰度偏倚，全基因组背景会让类别普遍虚假显著、丧失区分力） | §4.2、§7 阶段2 |
| **Q2** | 解释对象 = 全部鉴定蛋白 vs 仅差异蛋白？ | ✅ **分层处理**：全部蛋白做基础注释并保留基础节点；差异蛋白做富集、Foldseek KNN、假说、deep-search 和报告重点解释 | §2、§7 阶段1/2、§8.2 |
| **Q3** | 节点粒度 protein vs gene？（CTD 以 gene 为中心） | ✅ **双节点**：`Protein`(结构/属性/输入) + `Gene`(疾病/富集)，`(Protein)-[:ENCODED_BY]->(Gene)` 缝合；结构=蛋白级、疾病=基因级各挂原生层 | §4.4、§6.2、§8.2 |
| **Q4** | 通用 KG ↔ 本次 KG 衔接：子图拷贝 vs 引用？ | ✅ **混合模式**：公共实体/稳定事实引用通用 KG；实验差异、假说、evidence_level 和 deep-search 裁决落本次实验 KG；完成后冻结到实验数据库，保留通用 KG 版本与来源 ID | §8.2、§8.3 |
| **Q5** | 图库选型（Neo4j？）与 MySQL 边界？ | ✅ **Neo4j + MySQL**：MySQL 是事实唯一来源；Neo4j 保存可遍历关系、必要索引字段和 `mysql_ref`；通过 `GraphStore` 抽象接入。实验归档与通用 KG 使用隔离的逻辑库/命名空间 | §8 |
| **Q6** | 是否单独建设免疫数据库？ | 🟨 **暂缓但不关闭**：当前使用 UniProt GO + CTD + deep-search，不建设专用免疫库；预留免疫节点、关系和 `ImmuneKnowledgeProvider` 接口，后续按实际覆盖率与精度需求启用 | §5、§8.2 节点 |

---

## 11. 路线图与文档关系

- **路线图**（按依赖排序 + 最小闭环 + 阻塞标注）：见 [PROJECT-STATUS §8](PROJECT-STATUS.md)。最小闭环 = `S1 输入schema → M1 CTD → M2 Foldseek → M3 注释器`。
- **范围重构逐条分析**：[scope-reframing-analysis.md](scope-reframing-analysis.md)。
- **旧框架（已作废）**：[`legacy/`](legacy/)，仅历史参考。
