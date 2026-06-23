# PTAgent 项目状态与改进方向（交接文档）

> **用途**：新会话的唯一入口——读完这一份即可接上完整上下文。
> **权威性**：本文 + [scope-reframing-analysis.md](scope-reframing-analysis.md) 为准。**[project-spec.md](legacy/project-spec.md) 的旧 §2/§4/§7+ 与早期"谱图进、报告出闭环"理解已被推翻**（详见第 7、10 节）。
> **统一执行清单**：全部实施任务、进度符号和验收条件集中在 [`IMPLEMENTATION-CHECKLIST.md`](IMPLEMENTATION-CHECKLIST.md)。
> **更新**：2026-06-22（新增统一实施清单）。

---

## 1. 一句话定位

我（本项目这部分）负责**下游的"知识富集 + 关联解释 + 证据分级"**：拿到**已鉴定**的蛋白/肽，用几个公共数据库给它们附加带证据等级的 Meta（疾病/结构/属性），构建知识图谱并经 deep-search 闭环成报告。**上游"谱图→肽→蛋白"的鉴定对我无感知（给定）。**

---

## 2. 范围边界

| | 内容 |
|---|---|
| **不负责（上游，给定）** | 谱图采集、Casanovo de novo、查库归属、蛋白推断、novelty —— 这些的实现细节与我无关 |
| **负责（下游）** | ①解析输入 → ②通用知识图谱富集（证据分级）→ ③在实验工作区构建本次实验 KG → ④deep-search 验证 → ⑤冻结到实验数据库 → ⑥报告 |

---

## 3. 输入 / 输出

**输入三件套：**
1. **实验背景文本**（疾病/通路/物种/分组）。例：Jak2/Stat3 通路在急性脑缺血再灌注损伤(CIRI)中的作用；AAV9 基因沉默 + tMCAO 大鼠模型；DIA 蛋白质组比较 tMCAO+shNC vs tMCAO+shJak2。
2. **标注肽段集合**：一组或多组（多组=实验/对照，**带 label**）；每条肽 →1 蛋白、→1 或多张谱图；带**置信度**；可能带 Meta（亲和力、保留时间…）。
3. **蛋白质集合**：→若干肽；带 Meta。

> **定量/差异（case vs control）是核心**——这是 DIA 差异蛋白质组，整个目的就是比较两组。（旧 spec 把定量降级，已推翻。）
> **解释范围已定**：全部已鉴定蛋白做 UniProt/CTD 基础注释并保留基础 KG 节点；差异蛋白再做富集、Foldseek 结构 KNN、假说生成、deep-search 和报告重点解释。

**输出：** 带证据等级（结论/假说/伪理）的蛋白 Meta + 本次实验关联图谱 + 只读实验 KG 快照 + 报告。

---

## 4. 数据库（师兄已定，三个基本够用）

| 库 | 角色 | 形式 | 证据语义 |
|---|---|---|---|
| **UniProt** | 蛋白属性：结构域 / 组织表达 / 物种 | **师兄已封装成 MCP 工具** —— 我调它、在其上扩展建 KG，**不自己写** | 直接注释 = 结论级事实 |
| **CTD** | 蛋白-疾病 关联 | 蛋白-疾病 KG（可下载；注意 gene 为中心、含化学物推断的间接关联，做"结论"只取 curated/marker 直接证据） | 直接命中 = **结论** |
| **AlphaFold DB** | 结构 → **找 K 近邻** | 结构相似检索，实践用 **Foldseek** 在 AF 全库搜 | 结构近邻借关联 = **假说**；**且物种无关，天然做大鼠→人桥接** |

> **关键**：KNN = **结构相似（不是序列、不是网络）**；跨物种桥接由结构 KNN 自带，**不需另建同源库**。

---

## 5. 核心机制：三态证据模型

```
鉴定蛋白 P
 ├─ UniProt(MCP) → 直接取 结构域/组织表达/物种 ─────────→ 结论级 Meta
 ├─ CTD 查疾病关联
 │     直接命中 ───────────────────────────────────────→ 结论（直接证据）
 │     未命中 ↓
 └─ AlphaFold 结构 KNN(Foldseek) 找结构近邻
        近邻在 CTD 有疾病关联 → 借过来 ──────────────────→ 假说（结构类比，跨物种）
                                                     ↓
                                       deep-search 找证据
                                       ├ 直接证据 → 升级为 结论
                                       ├ 无证据   → 仍是 假说
                                       └ 反证     → 伪理（被证伪的假说，留档不丢）
```

| 态 | 含义 | 来源 |
|---|---|---|
| **结论** | 有确切证据 | 库里直接命中 / deep-search 直接证据 |
| **假说** | 有逻辑推导、待验证 | 结构 KNN 外推 |
| **伪理** | 被证伪的假说 | deep-search 找到反证（负结果有价值，留档） |

每个 Meta 属性带 `value + evidence_level(结论/假说/伪理) + source + 推导依据(假说:哪些结构近邻)`。

---

## 6. 目标架构（通用 KG + 实验工作区 + 实验数据库归档）

- **通用知识图谱（可复用"字典"）**：从 UniProt/CTD 建蛋白属性、蛋白-疾病 KG；AlphaFold 作为结构 KNN 的相似性底座。
- **本次实验 KG（实验工作区中的可变状态）**：输入 + 补的 Meta 整合成关联图；deep-search 在这里推动“假说→结论/伪理”，允许状态变化。公共实体/稳定事实引用通用 KG，实验差异、假说、证据等级和裁决绑定 `experiment_id` 留在本次 KG。
- **实验数据库（归档层）**：验证完成后将本次实验 KG 冻结为只读快照，统一按 `experiment_id + snapshot_version` 保存；新证据或重分析创建新版本，不覆盖旧版本。它与通用知识库逻辑隔离，服务于报告交付、审计复现和跨实验比较。
- **存储（已定）**：**MySQL 是事实唯一来源**，保存事实明细、Meta、状态历史和证据；**Neo4j** 通过 `GraphStore` 抽象提供关系遍历，只存必要索引字段和 `mysql_ref`；**实验数据库**在隔离逻辑库/命名空间中保存最终快照及报告引用，权限和生命周期与通用 KG 分离。

```
通用 KG（公共事实）
        ↓ 引用
本次实验 KG（工作区，可变）
        ↓ deep-search 完成并冻结
实验数据库（只读、版本化快照）
        ↓
报告 / 审计 / 跨实验比较
```

> 本次实验中得到验证的结论仍带物种、模型、组织、处理和时间点条件，不会自动写回通用 KG；进入通用 KG 需要独立审核。

---

## 7. 当前代码真实状态（仓库现况，诚实标注）

> 大量近期代码是按**旧（已推翻）框架**写的，targeting 上游或旧 KNN 思路。下面给出处置。

| 模块 / 文件 | 现状 | 处置 |
|---|---|---|
| `src/pkg/graph/`（store/cypher/types/schema） | 有，可用，含 measured-pipeline schema | **保留但重构** schema 为"通用 KG + 本次 KG + evidence_level" |
| `src/pkg/experiment/` | **新增**：实验三件套领域模型、跨引用校验、Repository 契约、MySQL DDL/store、内存测试实现 | **S1 代码底座已完成**；待部署环境做真实 MySQL 连通与迁移验证 |
| `src/application/experiment/context_mapper.py` | **新增**：旧 HTTP Context → 新领域 Context 显式映射；原始背景/假设组合、结构化字段优先级、附件和执行配置隔离 | 已完成并测试；待接入正式实验创建 Router/Pipeline |
| `src/application/experiment/request_service.py` + request models/tables | **新增**：不可变原始请求、连续版本/supersedes、content hash、附件绑定、结构化解析版本和 Context 当前指针 | 代码与离线 MySQL round-trip 已完成；真实 MySQL 迁移/联调及最终快照写入待后续阶段 |
| `src/pkg/protein_db/` | 有（FASTA 子串查库 + I/L） | **出范围**（上游鉴定） |
| `src/application/graph/db_assign.py` | 有（查库归属 + novelty） | **出范围**（上游） |
| `src/application/graph/materializer.py` + `loaders/casanovo.py` | 有 | **出范围**（上游） |
| `src/pkg/annotation/` + `src/application/knowledge/` | **新版基础链已实现**：标准 `ProteinAnnotationFact`、UniProt MCP 批量适配器、常见返回归一、确定性 Annotation ID、全量蛋白→`MetaAnnotation(CONCLUSION)`→实验 Repository；旧 TSV/graph 链暂留兼容 | 待外部 UniProt MCP 实例确认真实工具名/参数/返回后做联调 smoke test；不自写 REST |
| `src/pkg/hypothesis/` + `hypothesize.py` | 有（KNN→取共识，按 accession 留出处） | **改投**：从"借 GO/EC"改成"**结构近邻→借 CTD 疾病关联 = 假说**" |
| `src/pkg/retrieval/` | 有（混合检索框架：稠密/稀疏/RRF/rerank） | **改投**：改成**结构相似引擎（Foldseek over AlphaFold DB）** |
| `src/pkg/embedding/` | 有（ESM 编码） | 视需要——结构 KNN 多半不需要序列 embedding |
| 测试 | 113 个通过、1 个跳过（2026-06-22） | 新增不可变请求版本、hash、附件、解析历史和 MySQL round-trip 测试 |

> 简言之：`pkg/graph` 重构保留；`hypothesis`/`retrieval`/`annotation` 三个**改投**到新机制；`protein_db`/`db_assign`/`materializer`/loaders **出范围**。

---

## 8. 路线图（按依赖排序）

> **上游已整块划掉**——不再做、勿从 [`legacy/`](legacy/) 重新引入：谱图采集 / Casanovo de novo / 查库归属 / 蛋白推断 / novelty / `materializer`+loaders / 真实工具集成（scheduler 去 Mock）。起点 = **已鉴定的肽/蛋白 + 背景**。
> 标注：🟢 可立即做 · 🟡 依赖外部（库/工具）· 🔴 阻塞于 §9 待澄清　|　代码动作见 §7（复用/改投/重构）

**底座（横切，尽早）**
- **S0 · 重写 spec** ✅：新框架已固化成根目录 [`project-spec.md`](project-spec.md)（v3.1，字段级实现契约），替换 `legacy/` 旧版。
- **S1 · 输入 schema + MySQL** ✅：已实现实验背景/分组/肽/蛋白/定量/差异/Meta/证据历史/快照领域类型，三件套跨引用校验、MySQL DDL 与 Repository；现有 SQLite Session/Run 保持不动。部署前仍需真实 MySQL 连通与迁移 smoke test。

**★ 最小闭环（MVP——先证明核心机制，可先不入图、不部署）**
- **M1 · CTD 基因-疾病** 🟡：下载 CTD 建查询；经 protein→gene 映射后，直接命中（curated/marker）= **结论**。复用 `pkg/graph` 骨架。
- **M2 · Foldseek 结构 KNN** 🟡：`retrieval` **改投**为 Foldseek over AlphaFold DB；top-k 结构近邻 → 查其 CTD 关联 = **假说**（跨物种桥）。
- **M3 · 证据分级注释器** 🟢：`hypothesis` **改投**（"KNN→共识" 改成 "结构近邻→借 CTD"）；每条 Meta 带 `value + evidence_level + source + 依据`。

> **MVP 通过判据**：喂一小批已鉴定蛋白 → 输出带"结论/假说"标注的 Meta 表。**这一步证明整个项目的核心论点**，先于一切建图/部署。

**加厚层（在 MVP 之上逐层叠）**
- **L1 · UniProt 结论 Meta** ✅/🟡：代码链已完成——从实验 Repository 读取全部蛋白，批量调用可配置 UniProt MCP，标准化结构域/组织/物种/GO/EC 等事实，以确定性 ID 幂等写入 `MetaAnnotation(CONCLUSION)`；🟡 待真实 MCP 实例联调。
- **L2 · 差异分析 + 富集** ✅(代码)/🟡(联调)：差异引擎（log2FC+Welch t+BH）+ 过表达富集（超几何+BH，背景=鉴定蛋白池）+ 服务；**富集结果已持久化**到 `enrichment_result`（带 study/background checksum、基因集来源版本），离线测试完成；🟡 真实定量数据联调待做。
- **L3 · 本次实验 KG** ✅(代码)/🟡(联调)：新建双节点知识图谱层（通用KG + 本次KG + evidence_level），`GraphStore` 端口 + 内存/Neo4j 实现 + MySQL→图投影服务 + 离线测试均已落地，与旧 `pkg/graph` PSM 图隔离；🟡 待真连 Neo4j 实例联调（详见 [实施清单 §7](IMPLEMENTATION-CHECKLIST.md)）。
- **L4 · deep-search 认知态跃迁** ✅(代码)/🟡(联调)：可注入检索源 + 纯状态机（支持→结论 / 反证→伪理 / 冲突·无→保持）+ 回写 evidence_level + 追加 AnnotationHistory（幂等可回放）+ 人工覆盖，离线测试完成；🟡 待真实文献检索源（DeepXiv/MCP）接入。
- **L5 · 实验数据库归档** ✅(代码)/🟡(联调)：`freeze_experiment` 冻结前检查 + 内容 manifest（输入/Meta/历史/差异/图摘要/版本）+ 稳定 checksum + `ExperimentSnapshot(FINAL)` 只读/版本化（阻止覆盖、旧版不变）+ 篡改检测，离线测试完成；🟡 隔离 Neo4j 导出物、真库版本并发待联调。
- **L6 · 分层报告** ✅(代码)/🟡(联调)：`generate_experiment_report` 从冻结快照 manifest 出分层 Markdown（设计/差异/富集/结论/假说/伪理/未决 + 附录），每条带 annotation_id/来源/版本，只读快照 + 确定性 + 防篡改，绑定 `snapshot_version`，离线测试完成；🟡 报告落库/PDF/真实数据联调待做。

**建议起点**：`S1 → M1/M2/M3`（最小闭环），`S0` 可并行；随后按 `L1 → L2 → L3` 加厚。

---

## 9. 决策与待师兄/PhD 澄清

1. ✅ **"统计学角度"** = 对差异蛋白集做**富集分析** + KNN 外推；**富集背景集 = 本次鉴定蛋白池**（非全基因组——检测丰度偏倚会让类别普遍虚假显著、丧失区分力）。〔决策登记见 project-spec §10〕
2. ✅ **解释对象** = 分层处理：全部鉴定蛋白做基础注释和基础节点；仅差异蛋白做富集、结构 KNN、假说、deep-search 和报告重点解释。
3. ✅ **节点粒度** = **双节点**（`Protein` 结构/属性/输入 + `Gene` 疾病/富集，`ENCODED_BY` 缝合）；结构在蛋白级、疾病在基因级各挂原生层。〔登记见 project-spec §10〕
4. ✅ **通用 KG 与本次 KG 衔接**：采用**混合模式**——公共实体/稳定事实引用通用 KG；实验差异、假说、证据等级和 deep-search 裁决落本次实验 KG；完成后冻结进实验数据库并保留来源版本。
5. ✅ **图数据库与 MySQL 边界**：Neo4j 作为图查询后端并通过 `GraphStore` 抽象；MySQL 是事实唯一来源，Neo4j 只保存关系、必要索引字段和 `mysql_ref`；实验归档使用隔离逻辑库/命名空间。
6. 🟨 **免疫维度暂缓但保持开放**：当前不建设专用免疫数据库，使用 UniProt GO + CTD + deep-search；Schema 预留 `ImmuneProcess/ImmuneCell/Cytokine/ImmunePathway`，并预留数据源适配器和导入通道，后续按实际覆盖率与精度需求启用。

---

## 10. 文档与资源索引

**当前（权威，`docs/` 根目录）：**

| 文档 | 内容 | 注意 |
|---|---|---|
| **本文 `PROJECT-STATUS.md`** | 交接总览（当前状态 + 路线） | **新会话从这里开始** |
| [IMPLEMENTATION-CHECKLIST.md](IMPLEMENTATION-CHECKLIST.md) | **全部实施任务、完成状态、外部依赖和验收标准** | **后续进度统一在此勾选** |
| [project-spec.md](project-spec.md) | **正式规格 v3.1**：字段级输入 schema + Meta 记录 + MySQL/图库表 + 实验数据库归档 + 开放问题 | **实现契约** |
| [scope-reframing-analysis.md](scope-reframing-analysis.md) | 师兄反馈的逐条分析 + 改进方向（更细） | 与本文配套 |
| [architecture.svg](architecture.svg) | **新架构总览**：输入三件套 → 通用KG富集(三库/三态) → 本次KG工作区 → deep-search → 实验数据库归档 → 分层报告 | 新框架主图 |
| [evidence-model.svg](evidence-model.svg) | **证据三态模型**：单蛋白证据分级（结论/假说）+ deep-search 状态机（→结论/伪理） | 新框架核心机制 |

**历史归档（[`legacy/`](legacy/)，已作废，勿作设计依据）：**

| 文档 | 说明 |
|---|---|
| [legacy/README.md](legacy/README.md) | 归档说明 + 旧/新对照 + 文件清单 |
| `legacy/project-spec.md` | 早期规格 v2（已被根目录 [`project-spec.md`](project-spec.md) v3.1 取代） |
| `legacy/pipeline-steps.*`、`architecture-*.svg`、`relational-graph-design.html`、`remaining-work.md`、`materializer-dataflow.md`、`phd-confirmation-checklist.*` 等 | 旧流程分镜 / 架构图 / 剩余工作 / PhD 清单 —— **含已出范围的上游**，仅历史参考 |

**记忆**：`memory/project-closed-loop-scope.md` 已同步为本框架（供 Claude 跨会话加载）。
