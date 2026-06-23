# PTAgent 项目规格（Spec）

> 版本：v2 · 2026-06-17。本稿据需求方多轮澄清重写，**取代** [relational-graph-design.html](relational-graph-design.html) 中过度设计的部分（独立知识图谱、定量/蛋白组推断在此降级为可选）。
> 配图：[architecture-closed-loop.svg](architecture-closed-loop.svg)（项目全景）

---

## 1. 一句话目标

从生物人员提供的**谱图**出发，自动：**鉴定肽段 → 归属蛋白 → 在图谱上找相似的肽/蛋白（混合相似） → 构建假说 → 在线 deep-search 找证据 → 生成报告**。**谱图进、报告出**的闭环研究 agent。

---

## 2. 范围与边界（澄清后，关键）

**在范围内：**
- 关系图谱（实测）：`Sample → Spectrum → PSM → Peptide → Protein`
- **Protein 节点带 UniProt 注释属性**（`go` / `ec` / `interpro` 等，即 §7+ Tier A）
- 图谱上的 **`SIMILAR_TO` 相似边**（**混合相似**：序列召回 + 属性/网络重排，给 KNN 用）
- 假说生成（基于混合相似的肽/蛋白 + **注释传递**）
- **在线 deep-search** 找证据（论文/疾病/症状/实验）
- 报告生成（闭环交付）
- （可选）**第二图**：STRING(PPI) / Reactome(通路) 网络投影，作假说的网络证据线（见 §7+）

**明确不在范围（除非 PhD 另定）：**
- ❌ **独立知识图谱**：疾病/症状/论文**不建节点、不入图**（蛋白注释只作 Protein *节点属性*，不算独立 KG）
- ❌ **知识落库**：deep-search 结果**瞬时使用，不持久化、不单独建库**
- ❌ 定量（LFQ/TMT/SILAC）、蛋白组（ProteinGroup/GDS-WCC）——非本期重点，按需再开

> 一句话：**图谱存"实测的肽-蛋白关系 + 混合相似关系 + 蛋白的 UniProt 注释属性"；疾病/症状/论文等外部知识全程在线、用完即走。**

---

## 3. 闭环全流程（8 阶段）

| # | 阶段 | 输入 | 处理 | 输出 |
|---|---|---|---|---|
| 1 | 谱图输入 | 生物人员 | 上传 `.mgf/.mzML` → ingest 成 DataObject | DataObject |
| 2 | de novo 肽段 | 谱图 | Casanovo（MCP 工具）推理 | 肽序列 + 置信度（mzTab） |
| 3 | 查库 → 蛋白 | 肽序列 | 比对 UniProt/FASTA，得含此肽的蛋白 | 肽→蛋白归属 |
| 4 | 关系图谱构建 | 2+3 结果 | materializer 解包入 Neo4j | `Peptide`/`Protein` 节点+边 |
| 5 | KNN 混合相似 | 图谱节点 | 序列召回(ESM+k-mer/BLAST) → RRF 融合 → 精排 → `SIMILAR_TO` 边（`gds.knn` 仅稠密一路，见 §7+） | 每个肽/蛋白的 k 近邻 |
| 6 | 构建假说 | 相似邻居 | 注释传递："相似肽借母蛋白的 GO/EC/域共识 → 可能共享某特性" | 假说列表 |
| 7 | deep-search 证据 | 假说 | 在线检索论文等找支持/否定（不入库） | 证据 |
| 8 | 报告生成 | 假说+证据 | 综合成 Markdown 报告 | **交付报告（闭环）** |

---

## 4. 数据 / 图谱模型

**三层存储**（见 [storage-tiers-lookup.svg](storage-tiers-lookup.svg)）：
- 文件（磁盘）：谱图峰（重）
- SQLite（数据平面）：DataObject 登记 + `storage_path`
- Neo4j（关系图谱）：节点/边 + 指针，**不存峰**

**图谱节点/边：**
- 实测主干（已有）：`Sample-PRODUCED→Spectrum-HAS_PSM→PSM-IDENTIFIES→Peptide`
- 蛋白归属（阶段 3）：`Peptide-BELONGS_TO→Protein`
- **Protein 注释属性（阶段 3，§7+ Tier A）**：归属时按 UniProt accession 拉注释，写成节点属性 `go` / `ec` / `interpro`（集合），供属性相似 + 注释传递用（现仅 `accession` / `description`，待补字段）
- **相似边（阶段 5）**：`(Peptide)-[:SIMILAR_TO {score}]->(Peptide)` 及/或 `(Protein)-[:SIMILAR_TO {score}]->(Protein)`，由**混合检索** top-k 写出（序列召回 + 属性/网络重排；`gds.knn` 仅作稠密召回一路，融合+精排在应用层，见 §7+）
- **可选第二图**：STRING / Reactome 网络投影（见 §7+，按需开）
- **不新增**：`Disease`/`Symptom`/`Paper` 节点

**Peptide 身份**：`peptidoform`（带修饰）为 key，`stripped_sequence` 作属性（沿用现有 C1 默认）。

---

## 5. Agent 映射（对应 README 四 Agent）

| 闭环阶段 | Agent | 现状 |
|---|---|---|
| 2 肽段 | 质谱解析 / 鉴定 Agent | 🟡 解析器+materializer 有，真 Casanovo 工具未接 |
| 3 蛋白归属 | 鉴定 Agent | ❌ 新（MCP_IO 查 UniProt/FASTA） |
| 5 KNN / 6 假说 / 7 deep-search | 生物学解释与注释 Agent | ❌ 新（gds.knn + 假说 + 在线检索；distill 现占位） |
| 8 报告 | 报告生成 Agent | 🟡 `generate_report` 占位 |

---

## 6. 实现现状

**已有底座（✅）**
- ingest / DataObject / SQLite 存取 / 类型 / 目录
- 解析器 `mztab_casanovo.py`（带测试）、`mgf.py`（除 RT）
- `pkg/graph/` schema/cypher/store/types（含 GDS 接口）
- `materializer.py` + `loaders/casanovo.py`（已验证）

**待建（❌ / 🟡）**
- 阶段 2：真实 Casanovo MCP 工具（toolCount=0）+ scheduler 去 Mock + 工具产物注册成 DataObject
- 阶段 3：查库归属步（肽→蛋白）+ 写 `BELONGS_TO`
- 阶段 4：`materialize_graph` 节点接进 LangGraph（现 0 处）
- 阶段 5：序列 embedding + `gds.knn` → `SIMILAR_TO`（cypher + store 方法）
- 阶段 6：假说生成器
- 阶段 7：deep-search 研究循环（distill_and_research 去占位）
- 阶段 8：报告生成（generate_report 去占位）
- 部署：Neo4j + GDS 插件

---

## 7. 待定决策（请 PhD / 需求方确认）

1. **A1 实际走"混合"**：de novo（Casanovo）出序列 → 查库归属蛋白；纯 de novo 不够（要蛋白）。确认匹配方式：精确 / 容错同源(BLAST)？
2. **相似度怎么算**：基于序列（编辑距离/k-mer/比对）还是 **embedding**（蛋白语言模型如 ESM + `gds.knn`）？ → **已定（混合相似），见 §7+**
3. **KNN 做在哪层**：Peptide / Protein / 两者？ → **已定（两层分工），见 §7+**
4. **假说模板**：相似邻居"共享"的是什么特性（疾病关联 / 功能 / …）？
5. **deep-search**：接现成 deep-research MCP，还是自建"搜→读→抽→再搜"循环？
6. **novel 肽阈值**：查库没命中的肽，按 `score`/`aa_scores` 卡多少（隔离 de novo 错误，避免假新肽淹没下游）？ → **见 §7+（置信度 = 相似度 × 共识度）**
7. **部署**：Neo4j 实例 + 是否装 GDS 插件（KNN 与任何图算法都依赖）。

---

## 7+ · 检索与注释传递主线（2026-06-17 定稿）

> 本节对上面 **Q2 / Q3 / Q6** 给出**已定方案**，并定下两条主线：**混合检索**（阶段5）与**注释传递**（阶段5→6 的内核）。**取代 Q2 / Q3 / Q6 原"待定"表述。**

### 主线 A：注释传递（annotation transfer / label propagation）

未记录（novel）肽自身无功能注释；其价值来自**借相似已知肽的注释来预测**。链路：

```
novel 肽 ─(序列相似检索)→ k 个相似的已知肽 ─(BELONGS_TO)→ 它们带注释的母蛋白
        ─(聚合取共识)→ GO/EC/域/通路 ─→ 该肽的"可能属性" = 假说 ─→ 阶段7 deep-search 验证
```

要点：**用谁找 ≠ 借谁的属性**。检索 novel 肽的邻居只能靠序列（下方①②）；属性（③）与网络（④）不是检索器，而是**邻居母蛋白被借走的 payload**，按 UniProt accession 取。

### 主线 B：混合检索（两阶段，对应阶段5）

- **粗筛（高召回，多路并行）**：① 稠密 ESM 序列 embedding（ANN/余弦，即现 `gds.knn`）；② 稀疏 k-mer / BLAST(DIAMOND，局部同源)。**仅这两路靠序列，novel 肽也能用。**
- **融合**：RRF（按排名倒数），**不用加权求和**——各路打分量纲不同，校准代价大。
- **精排（高精度，仅 top-N）**：序列比对(SW / BLAST bitscore) / 交叉编码器 / **LLM-judge**（读双方属性判"是否共享某特性"，与假说生成天然接续）。
- **落点**：召回各路 + 网络留在 GDS / 外部 ANN；**融合 + 精排放应用层**（`application/graph/embed_knn.py`），rerank 是 query-time、逐候选算，不塞进 Cypher 批处理。

### 已定方案（对应 Q2 / Q3 / Q6）

| 待定项 | 建议解 |
|---|---|
| **Q2 相似度** | 序列 embedding(ESM) 为主 + 稀疏同源(k-mer/BLAST)补盲 → 混合检索 + rerank（取代"二选一"）。`KNN = 序列相似` 升级为 `KNN = 混合相似`。 |
| **Q3 KNN 在哪层** | **两层分工**：肽层先跑序列两路兜底召回（novel 肽适用）；归属到蛋白后在蛋白层补属性+网络并重排。**能归属就在蛋白层传递（更稳），真·novel 才退到肽层。** |
| **Q6 novel 阈值** | 肽层传递风险高（**传递性注释错误** transitive annotation error，逐跳放大）。置信度 = 邻居相似度 × 邻居共识度；须卡门槛，单个弱邻居不得驱动自信断言。 |

### 派生决策（被上面主线锁定）

- **检索池：必须 against 全库（UniProt），非仅实测图内。** 注释要可传递，邻居必须是**已注释的已知蛋白**；只在实测肽内检索会"借无可借"。蛋白量级大 → 召回需外部 ANN(FAISS/Qdrant)，`gds.knn` 退化为稠密那一路。
- **知识图谱数：1 必建 + 1 可选，不建独立 KG。**
  - **图1（必建）**：现有实测关系图 + 把 UniProt 注释(GO/EC/InterPro)挂成 **Protein 节点属性**（Tier A）。即 `MERGE_PEP_PROT` 给 Protein 增 `go` / `ec` / `interpro` 字段。
  - **图2（可选）**：STRING(PPI) 或 Reactome(通路) 的网络投影，**仅当**假说要"功能/网络邻居"作第二证据线时建。
  - **不建**：疾病/药物/论文独立 KG（无稳定主键、更新快）→ 维持在线 deep-search（见 §2）。

> 与 §2 的一致性：此处把 UniProt 蛋白注释作为 **Protein 节点属性**写入，是对 §2"知识不入图"的**细化**——属性挂在已有 Protein 节点上（非独立 `Disease`/`Paper` 节点），疾病/论文仍**在线查、不入图**。

---

## 8. 落地优先级（最短闭环优先）

1. **阶段 4**：`materialize_graph` 节点 + 接线 + 测试（纯本地、无外部依赖、无 PhD 阻塞）。
2. **阶段 2**：真实 Casanovo 工具 + scheduler 去 Mock + 输出注册 DataObject（打通数据源头）。
3. **阶段 3**：查库归属（肽→蛋白），关系图谱补全到 Protein。
4. **阶段 5**：embedding + `gds.knn` → `SIMILAR_TO`（图谱的"智能"基础）。
5. **阶段 6/7**：假说 + deep-search（解释 Agent 主体）。
6. **阶段 8**：报告（generate_report 去占位）。

> 详细任务拆分见 [remaining-work.md](remaining-work.md)；待 PhD 决策项见 [phd-confirmation-checklist.html](phd-confirmation-checklist.html)。

---

## 9. 文档关系

- **本 spec**：项目真实范围与闭环（最新、最权威）。
- `relational-graph-design.html`：早期设计稿；**关系图谱主干 / 三层存储 / GDS 用法仍有效**，但其"独立知识图谱三层 / 定量 / 蛋白组推断"**降级为可选**，以本 spec 为准。
- `materializer-dataflow.md`：阶段 4 的参数级数据流。
- `architecture-*.svg`：架构与 schema 图。
