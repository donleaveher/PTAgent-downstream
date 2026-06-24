# PTAgent 统一实施清单

> **用途**：本文件集中记录当前下游知识层从代码、数据、外部服务到交付验收的全部工作；后续实施进度只在这里勾选，避免散落在多个 TODO。
> **规格依据**：机制与字段以 [`project-spec.md`](project-spec.md) 为准；背景与范围以 [`PROJECT-STATUS.md`](PROJECT-STATUS.md) 为准。
> **更新日期**：2026-06-23。
> **当前基线**：`198 passed, 1 skipped`；真实 MySQL、UniProt MCP、CTD、Foldseek、Neo4j 实例、文献检索工具尚未完成端到端联调。MVP 三件（M1/M2/M3）代码 + 离线闭环已完成；M3 默认 gene 解析器（UniProt MCP）已接好；L2 差异分析 + 富集引擎/服务已落地（离线测试）；**CTD 真实数据已下载/过滤/加载验证**（2.9GB→2.6MB，34,253 直接事实）；**L3 本次实验 KG 纯代码核心已落地**（双节点 GraphStore 端口 + 内存/Neo4j 实现 + MySQL→图投影 + 离线测试），真连 Neo4j 实例待 B 组；**L4 deep-search 认知态跃迁纯代码核心已落地**（任务/证据/可注入源 + 纯状态机 + 回写 evidence_level/追加 AnnotationHistory，幂等可回放 + 人工覆盖），真实文献检索源待接；**L5 实验冻结归档纯代码核心已落地**（冻结前检查 + 内容 manifest + 稳定 checksum + FINAL 只读/阻止覆盖/版本化 + 篡改检测，离线测试），隔离 Neo4j 导出/真库并发待 B 组；**富集结果持久化已落地**（`enrichment_result` 表 + Repository + `run_disease_enrichment` 写全量结果 + study/background checksum，并入冻结 manifest）；**L6 分层报告纯代码核心已落地**（只读冻结快照 manifest → 分层 Markdown：设计/差异/富集/结论/假说/伪理/未决 + 附录，每条带 annotation_id/来源/版本，确定性 + 防篡改）；**下游管线编排（§11.2）已落地**（把上述服务按依赖序串成端到端流程；提供两种编排：纯 Python 线性 runner + **LangGraph 主图**——StateGraph 复用同一批 step + 冻结前人审批条件边 + audit log；失败隔离 + 幂等重跑 + 断点续跑 + 状态查询，离线 e2e 通过）；**对外 API（§11.1）已落地**（FastAPI 路由：实验创建/查询、跑管线、查注释/差异/富集/历史、查 KG 证据路径、冻结/快照/报告，DI 可注入，TestClient 离线测试通过）。**A 组（纯代码）+ §11 编排与 API 已全部完成**，剩余主要为 B 组外部联调与鉴权/审计。

## 状态符号

- ✅ **已完成**：代码和对应离线测试已经完成，或设计决策已经正式确定。
- 🟨 **部分完成 / 等待外部联调 / 暂缓开放**：核心代码或决策已存在，但还不能作为完整交付关闭。
- ⬜ **未完成**：仍需设计、编码、测试或部署。
- 🚫 **不在范围内**：不得重新引入当前主线。

---

## ⏭️ 剩余工作速览（下一步做什么）

> **已完成（代码 + 离线测试）**：S1 输入域 + MySQL 事实库、L1 UniProt 链、M1 CTD（**真实数据已就绪**）、L2 差异+富集、M2 Foldseek 引擎、M3 结构类比假说、MVP 离线闭环。
> 下面按「纯代码可立刻推进 / 卡外部资源 / 细化暂缓」分组；勾选与细节见对应章节。

### A · 纯代码可立刻推进（不卡外部依赖）

- 🟨 **L3 · Neo4j 通用 KG + 本次实验 KG**（§7）：把 MySQL 事实投影成**双节点**图——`Protein`/`Gene`（`ENCODED_BY`）+ `Disease`，边带 `evidence_level`、`STRUCTURAL_NEIGHBOR`、`DIFFERENTIAL`，节点带 `mysql_ref`。**纯代码核心已落地**（端口 + 内存/Neo4j 实现 + 投影 + 离线测试）；真连 Neo4j 实例（B 组）、版本化重建、deep-search 回写、Domain/Tissue 等扩展节点仍 ⬜。
- 🟨 **deep-search 认知态跃迁**（§8）：假说 +直接证据→结论 / +反证→伪理 / 冲突·无→保持，回写 `evidence_level` + 追加 `AnnotationHistory`。**纯代码核心已落地**（可注入检索源 + 纯状态机 + 幂等可回放 + 人工覆盖）；真实文献检索源（DeepXiv/MCP）、失败/超时重试仍 ⬜。
- 🟨 **实验冻结归档**（§9）：本次 KG → 只读版本化快照。**纯代码核心已落地**（`freeze_experiment` 冻结前检查 + 内容 manifest + 稳定 checksum + FINAL 只读/版本化 + `verify_snapshot_integrity` 篡改检测）；隔离 Neo4j 导出、SUPERSEDED 编排、真库版本并发仍 ⬜。
- ✅ **分层报告**（§10）：`generate_experiment_report` 从冻结快照按 结论/假说/伪理/未决 出 Markdown，绑定 `snapshot_version`，只读快照 + 确定性 + 防篡改；报告 artifact 落库（独立报告表）留后续。
- ✅ **富集结果持久化**（§4.3）：`enrichment_result` 表 + `EnrichmentRecord` 模型 + Repository（端口/内存/MySQL）；`run_disease_enrichment` 幂等写**全量**结果，记录 study/background checksum 与基因集来源版本，并入冻结 manifest（§9）。

### B · 卡真实外部资源（代码就绪，等数据/服务联调）

- 🟨 **UniProt MCP 实例**：L1 蛋白注释 + M3 gene 解析（`get_protein_annotation_source` / `get_gene_resolver` 已接好，需活实例确认工具名/参数/返回）。
- 🟨 **Foldseek 二进制 + AlphaFold DB 索引 + 查询结构**：M2 真实结构检索（引擎/解析/筛选/假源测试已过）。
- 🟨 **真实 MySQL 实例**：建库 + 跑 DDL + round-trip smoke（离线读写契约已测）。
- 🟨 **真实实验输入**：真实 Jak2/CIRI 三件套 + 定量，端到端 M1→L2→M2/M3→报告。

### C · 细化 / 暂缓（不挡主线）

- ⬜ **#3 输入修订/重存策略**：`save_bundle` upsert 会留孤儿子行——倾向「整实验替换(a)」，待定后落代码。
- ⬜ NCBI GeneID 精确映射（现按 gene symbol 大小写归一）。
- ⬜ Disease 同义词归一、CTD 版本升级策略。
- ⬜ §11 API/编排/产品接入（pipeline 串联、对外接口）——晚于知识管线。
- 🟨 免疫维度（§12 / Q6）：暂用 UniProt GO + CTD；schema 预留扩展通道。

> **A 组（纯代码）已全部完成 + 下游管线编排（§11.2）已落地**：L3 两层知识图谱 → L4 deep-search → L5 冻结归档 → L6 分层报告，外加 §4.3 富集持久化，并由下游管线编排串成端到端流程（纯 Python runner + LangGraph 主图两种），再经 **FastAPI 对外 API（§11.1）** 暴露（离线 e2e + TestClient 通过，`198 passed, 1 skipped`）。**下一步**：B 组外部联调（真连 MySQL/Neo4j/UniProt MCP/Foldseek/文献检索源）、鉴权/审计、LangGraph checkpointer/streaming 接线。各 L 的真库/外部部分见对应章节 ⬜。

---

## 0. 范围与关键决策

### 0.1 项目边界

- ✅ 输入边界确定为：实验背景 + 已鉴定标注肽段 + 已鉴定蛋白。
- ✅ 本项目负责：知识富集、差异解释、证据分级、通用 KG、本次实验 KG、deep-search、归档和报告。
- 🚫 不负责谱图采集、Casanovo de novo、查库归属、蛋白推断和 novelty。
- 🚫 不把旧肽序列 embedding/KNN 当作新版结构 KNN。
- 🚫 不自行实现 UniProt REST/TSV 在线主路径，统一调用 UniProt MCP。

### 0.2 已确定决策

- ✅ Q1：富集背景集使用本次鉴定蛋白池，不使用全基因组。
- ✅ Q2：全部蛋白做基础注释；差异蛋白才做富集、Foldseek、假说、deep-search 和重点报告。
- ✅ Q3：同时使用 `Protein` 和 `Gene` 节点，以 `ENCODED_BY` 缝合。
- ✅ Q4：公共实体/稳定事实引用通用 KG；实验判断保存在本次实验 KG；完成后冻结归档。
- ✅ Q5：MySQL 是事实唯一来源；Neo4j 负责关系遍历，通过 `GraphStore` 抽象访问。
- 🟨 Q6：当前不建设专用免疫数据库，但保持扩展通道，不关闭后续可能性。

---

## 1. 实验输入与 MySQL 事实库

### 1.1 领域模型

- ✅ `ExperimentContext`：背景、疾病、通路、物种、assay、design、生命周期。
- ✅ `ExperimentGroup`：case/control 分组。
- ✅ `PeptideRecord`：肽段、所属蛋白、谱图、置信度、组别、丰度和 Meta。
- ✅ `ProteinRecord`：accession、gene、物种、肽段引用和 Meta。
- ✅ `ProteinQuantification`：蛋白×组别×样本定量模型。
- ✅ `DifferentialResult`：log2FC、p、q、方向和显著性模型。
- ✅ `MetaAnnotation`：target、value、evidence level、source、derivation、provenance。
- ✅ `AnnotationHistory`：证据状态变化历史。
- ✅ `ExperimentSnapshot`：归档快照模型。
- ✅ `ExperimentBundle` 三件套跨引用校验：重复 ID、未知组别、未知蛋白、错误肽归属。
- ✅ 确定性 `annotation_id`，保证相同事实重跑时幂等 upsert。

### 1.2 Repository 与 MySQL

- ✅ `ExperimentRepository` 端口。
- ✅ `InMemoryExperimentRepository` 测试实现。
- ✅ MySQL 配置与环境变量。
- ✅ PyMySQL 依赖声明，运行时延迟加载。
- ✅ MySQL DDL：实验、分组、蛋白、肽、定量、差异、Meta、历史和快照。
- ✅ `MySQLExperimentStore`：Schema 初始化、Bundle 写入/读取、Meta 写入/读取、历史追加。
- ✅ MySQL 写操作事务提交、异常回滚和连接关闭测试。
- ✅ MySQL 读路径离线往返测试（忠实模拟 DictCursor）：覆盖列名映射、JSON/枚举反序列化与 datetime 时区往返（写前 tz-aware == 读回 tz-aware UTC）。
- ✅ 保留原 SQLite Session/DataObject/Run，不进行高风险一次性替换。
- 🟨 在部署环境安装更新后的依赖并创建 `ptagent_experiment` 数据库。
- 🟨 使用真实 MySQL 运行 DDL 和 Bundle round-trip smoke test。
- ⬜ 引入正式迁移机制和 schema version，不长期依赖纯 `CREATE TABLE IF NOT EXISTS`。
- ⬜ 实现 `ProteinQuantification` Repository CRUD。
- ⬜ 实现 `DifferentialResult` Repository CRUD 和仅查询差异蛋白接口。
- ✅ 实现实验快照 Repository CRUD（`save/get/list_snapshots` + `manifest` 字段；冻结服务见 §9）。
- ⬜ 增加 `db_cache`、`deep_search_evidence` 的正式表和 Repository 接口。
- ⬜ 定义重复导入、输入修订、软删除和实验取消规则。

### 1.3 输入应用层

- ✅ 原始 dict → `ExperimentBundle` 校验 → Repository 持久化入口。
- ✅ 旧 HTTP `ExperimentContext` → 新领域 `ExperimentContext` 显式转换器。
- ✅ `description + hypothesis` 确定性组合为 `raw_text`，不做隐式 LLM 改写。
- ✅ 结构化字段优先级已固定：`extra.structured_context → extra → constraints`。
- ✅ `data_object_ids`、FilterConfig 和 WorkflowPreset 通过独立映射结果保留，不污染领域 `design`。
- ✅ 修复旧 HTTP `filter_config.default_factory` 导致 Context 无法实例化的问题。
- ⬜ 将转换器接入正式实验创建 Router/Pipeline；当前已有独立应用服务和测试，尚未接生产入口。
- ⬜ 增加文件导入适配器：CSV/TSV/JSON 三件套。
- ⬜ 定义并实现 DIA-NN/其他上游已鉴定结果的字段映射；只做结果导入，不做上游鉴定。
- ⬜ 从背景原文结构化抽取 disease/pathway/organism/groups，并保留人工确认入口。
- ⬜ 提供导入错误报告：行号、字段、引用错误和修复建议。
- ⬜ 增加输入 Bundle 大数据量批量写入和性能测试。

### 1.4 原始请求版本与审计

- ✅ 增加冻结的 `ExperimentRequest` 模型和 `experiment_request` 表。
- ✅ 每次问题修改只允许严格追加下一版本，不使用 upsert 覆盖旧 `raw_question/request_payload_json`。
- ✅ 请求自动计算并校验稳定 SHA-256 content hash。
- ✅ `ExperimentContext` 保存当前结构化理解，并通过 `current_request_id` 指向当前原始请求版本。
- ✅ 增加 `ExperimentInputArtifact/experiment_input_artifact`，将 DataObject、角色、文件 hash 和上游软件绑定到具体 request version。
- ✅ 增加 `ExperimentContextRevision/experiment_context_revision`，结构化解析和人工确认采用追加版本，不覆盖旧解析。
- ✅ Router 可传入未经 DTO 丢字段的原始 payload 和完整 raw question；未传时回退到规范化 HTTP DTO。
- ✅ Repository 支持 append/get current/list history/list artifacts/list revisions，并校验连续版本与 supersedes 链。
- ✅ `ExperimentSnapshot` 模型与 DDL 已预留 request ID、version、content hash 和附件 hashes。
- ✅ 增加不可覆盖、hash 校验、版本跳号、附件绑定、解析追加和 MySQL round-trip 测试。
- 🟨 快照 Repository/冻结服务尚未实现，因此请求 hash 真正写入最终快照要在第 9 节完成。

**阶段验收：**

- 🟨 给定一份真实三件套，可以校验并完整写入/读回真实 MySQL；目前离线模型与 DB-API 契约已通过，真实数据库联调未完成。

---

## 2. UniProt 全量基础注释

### 2.1 已实现代码

- ✅ 标准 `ProteinAnnotationFact` 和 `ProteinAnnotationSource` 协议。
- ✅ `UniProtMCPAnnotationSource` 批量调用适配器。
- ✅ MCP 工具名、accession 参数名、批大小和 fallback 版本配置化。
- ✅ 兼容 `results/data/items/hits/result`、单记录和 accession→record 映射。
- ✅ 归一结构域、组织、物种、taxon、GO、EC 和 InterPro。
- ✅ 保留 MCP 工具名、数据库版本、原始字段、evidence code 和 source ref。
- ✅ 从实验 Repository 读取全部蛋白，不以差异状态过滤基础注释。
- ✅ 直接 UniProt 事实生成 `MetaAnnotation(CONCLUSION)`。
- ✅ 先写 MySQL Repository，不直接把 Neo4j 当事实源。
- ✅ 稳定 Annotation ID；重复运行不会在 Repository 中制造重复事实。
- ✅ 单元测试覆盖解析、批处理、缺失 accession、幂等性和实验隔离。

### 2.2 尚需完成

- 🟨 与师兄确认真实 MCP 工具名、输入参数和输出 Schema。
- 🟨 连接真实 Broker/Provider 完成批量调用 smoke test。
- ⬜ 对 MCP 部分批次失败实现有限重试、错误记录和可恢复续跑。
- ⬜ 将 MCP 原始响应或摘要写入 `db_cache`，避免无条件重复查询。
- ⬜ 明确 GO evidence code 分级规则：实验型证据、人工推断、电子注释是否全部保持 `CONCLUSION`。
- ⬜ 增加注释覆盖率、缺失率、调用耗时和错误率指标。
- ⬜ 第三阶段 GraphStore 完成后，将已落库事实投影到通用 KG/实验工作区。

**阶段验收：**

- 🟨 对真实实验全部 accession 调用真实 UniProt MCP，结果可幂等写入 MySQL，缺失项和版本信息可审计；当前代码与离线测试已完成，外部联调未完成。

---

## 3. CTD 基因—疾病直接证据

> **进展（代码链已落地，对标 UniProt 链；离线/假源已测）**：`parse_ctd_genes_diseases` + `CTDFileDiseaseSource`（parser/索引/直接证据过滤）、`annotate_experiment_diseases`（全量蛋白→基因→`MetaAnnotation(CONCLUSION)`，幂等）、`CtdSettings` 与 parser/服务测试均已完成。
> 另有预处理脚本 `scripts/prepare_ctd.py`：把 CTD 大文件**流式过滤**成"只含直接证据"的精简 CSV + 写 sha256/版本 manifest（过滤规则与读取端共用 `iter_direct_evidence_rows`，不漂移）。
> 下面 ⬜ 中 **parser / 直接证据过滤(3.2) / Gene 结论 / 预处理+checksum / 测试** 已由代码满足；**真实 CTD 文件已下载并过滤加载**（`data/ctd/CTD_genes_diseases.direct.csv`，34,253 直接事实，gitignored）。**仍 ⬜**：在真实实验上端到端联调、NCBI GeneID 精确映射、Disease 同义词归一、版本升级策略。

### 3.1 数据获取与规范化

- ⬜ 确认 CTD 下载文件、许可、更新频率和版本命名。
- ✅ 下载并校验：真实 `CTD_genes_diseases.csv.gz`（2.9GB，sha256 `3695825766…`）已下载；`prepare_ctd.py` 过滤为 **34,253 直接证据行**（扫描 125,219,222 行，0.03%）+ manifest，加载验证 9,114 基因。
- ✅ 实现 CTD parser 和本地索引/精简缓存（`parse_ctd_genes_diseases` + 预处理脚本产直接证据精简 CSV）。
- ⬜ 统一 Disease ID、名称和同义词。
- ⬜ 实现 Protein accession → Gene ID/Symbol 映射检查。
- ⬜ 处理大鼠蛋白、人类疾病知识和物种字段，不把跨物种关系误写为直接事实。

### 3.2 证据语义

- ⬜ 定义 curated/marker/direct 的允许规则。
- ⬜ 将 chemical-inferred 等间接关系排除出直接 `CONCLUSION`，或明确降级字段。
- ⬜ 生成 Gene 级 `MetaAnnotation(CONCLUSION)`，保留 CTD relation ID、文献和版本。
- ⬜ 将结果写入 MySQL，并为后续通用 KG 投影准备 canonical IDs。
- ⬜ 实现幂等更新、版本升级和旧版本保留策略。
- ⬜ 增加 parser、过滤规则、ID 映射和 Repository 集成测试。

**阶段验收：**

- ⬜ 输入一批实验蛋白，可以输出经过直接证据过滤、可追溯的基因—疾病结论 Meta。

---

## 4. 差异分析与富集

> **进展（L2 引擎 + 服务已落地；离线测试通过）**：`pkg/analysis/`——`compute_differential_results`（log2FC + Welch t + BH；无重复退化为 fold-change）、`over_representation`（超几何 ORA + BH，**背景=鉴定蛋白池** Q1）；`application/analysis/`——`analyze_experiment_differential`（按 role 自动选组、写 `differential_result`）、`run_disease_enrichment`（差异基因 vs 全部鉴定基因，基因集取自 CTD 结论）。定量/差异持久化复用仓库 `add_quantifications`/`add_differentials`（InMemory+MySQL 均已实现）；"仅差异蛋白"在服务内由 `list_differentials` 过滤 `is_differential` 派生。
> 下面 ⬜ 中 **差异统计(4.2)/富集统计(4.3)/数值正确性测试** 已由代码满足；**富集结果持久化已落地**（`enrichment_result` 表 + Repository + 服务写全量结果 + study/background checksum）。**仍 ⬜**：真实定量写入(4.1)、缺失值/归一化的真实数据边界、真实 case/control 联调。

### 4.1 定量输入契约

- ⬜ 明确样本重复、组别、缺失值、归一化后丰度和原始丰度字段。
- ⬜ 明确 DIA 输入的蛋白级定量是否由上游直接提供，避免在本层重复蛋白汇总。
- ⬜ 将真实定量数据写入 `protein_quantification`。
- ⬜ 校验 case/control、样本重复和可比较性。

### 4.2 差异统计

- ⬜ 实现或封装差异统计后端。
- ⬜ 计算 log2FC、p-value、BH q-value 和 direction。
- ⬜ 明确默认显著性阈值，并允许实验级配置。
- ⬜ 将全量结果写入 `differential_result`，而不只保存显著项。
- ⬜ 生成“仅差异蛋白”查询接口，供 Foldseek/deep-search 使用。
- ⬜ 处理缺失值、极端值和零值。
- ⬜ 增加已知小数据集的数值正确性测试。

### 4.3 富集分析

- ✅ 使用本次鉴定蛋白池作为背景集（Q1）。
- ✅ 明确使用的基因集来源和版本（`gene_set_source=CTD` + `gene_set_version` 取自 provenance）。
- ✅ 实现富集统计、多重检验和效应量输出（超几何 + BH + fold_enrichment）。
- ✅ 将富集**全量**结果写入 MySQL（`enrichment_result`），并保留 study/background 集合 checksum。
- ✅ 区分“集合层富集结论”（独立 `EnrichmentRecord`/表）和“单蛋白功能结论”（`MetaAnnotation`），不混淆证据语义。

**阶段验收：**

- 🟨 从 case/control 定量得到可复现的全量差异结果、差异蛋白列表和富集结果（富集已持久化到 `enrichment_result` 并带 checksum）：**离线引擎+服务+持久化测试通过**；真实定量数据联调待做。

---

## 5. AlphaFold/Foldseek 结构近邻

> **进展（结构检索引擎已落地，对标 UniProt/CTD 链；离线/假源已测）**：新建独立包 `pkg/structure/`——`StructureSearchProvider` 协议 + `StructuralNeighbor`（score/coverage/rank/taxon/relation_id/版本）+ `parse_foldseek_output` + `select_neighbors`（去自身/阈值/top-k/排名）+ `FoldseekStructureSearchProvider`（runner 可注入）+ `StructureSettings`。**不复用旧序列 KNN**。
> 已离线验证**跨物种 大鼠→人** 近邻案例。**仍 ⬜**：真实 Foldseek 二进制 + AlphaFold DB 索引/查询结构、"仅差异蛋白"编排（依赖 L2）、检索摘要持久化/`STRUCTURAL_NEIGHBOR` 图投影（依赖 §7）、物种过滤选项。

### 5.1 Provider 与运行环境

- ⬜ 定义 `StructureSearchProvider` 协议。
- ⬜ 实现 Foldseek provider；不得复用旧肽序列 KNN 作为正式实现。
- ⬜ 准备 AlphaFold DB/Foldseek 索引并记录版本、checksum 和构建参数。
- ⬜ 定义 accession → AlphaFold structure ID 映射。
- ⬜ 处理结构缺失、多结构、低置信结构和查询失败。
- ⬜ 配置 top-k、相似度阈值、覆盖度阈值和物种过滤选项。

### 5.2 检索与持久化

- ⬜ 仅对差异蛋白执行结构检索。
- ⬜ 输出 query protein、neighbor protein、score、coverage、rank、taxon 和数据库版本。
- ⬜ 将原始检索摘要写 MySQL/cache，不把大结构文件写入 Neo4j。
- ⬜ 为 `STRUCTURAL_NEIGHBOR` 图投影准备稳定关系 ID。
- ⬜ 增加 fake provider 单元测试和小型 Foldseek 集成测试。
- ⬜ 验证至少一个大鼠→人结构近邻案例。

**阶段验收：**

- ⬜ 输入差异蛋白 accession，可得到版本明确、参数完整、可复现的 top-k 结构近邻。

---

## 6. 结构近邻疾病假说与证据分级

### 6.1 基础设施

- ✅ `EvidenceLevel` 已包含 `CONCLUSION/HYPOTHESIS/REFUTED`。
- ✅ `MetaAnnotation` 已包含 source、derivation 和 provenance。
- ✅ `AnnotationHistory` 模型和 MySQL 表已存在。
- ✅ 稳定 Annotation ID 已实现。

### 6.2 新版假说生成

> **进展（M3 已落地；离线/假源 MVP 闭环已测）**：`application/knowledge/hypothesis_generation.py`——每蛋白 取结构近邻(M2) → 解析近邻 gene(`GeneResolver`) → 查近邻 gene 的 CTD 疾病(M1) → 借为 **Protein 级 `MetaAnnotation(HYPOTHESIS)`**；derivation 存全部支持近邻/score/taxon/via_gene/CTD relation，confidence=最高近邻分；**蛋白自身 gene 已有直接结论的疾病不重复出假说**；幂等。
> `get_gene_resolver` **已实现**（复用师兄的 UniProt MCP，见 `UniProtMCPGeneResolver`）——M3 默认装配不再有 `NotImplementedError`，仅待真实 MCP 联调。
> **多路融合重排（接入 `pkg.retrieval`）**：结构近邻不再只按 Foldseek 单路 `score` 排，而经 `pkg/structure/rerank.py::rerank_neighbors`——用 RRF（`pkg.retrieval.rrf`）融合 `score` + `coverage` 两路（并留 `extra_channels` 口子接序列/向量/属性召回），支持近邻按融合分重排；`confidence` 仍取最高结构分（保持兼容），新增 `rerank_confidence`/`fused_score`/`ranking`。可 `rerank=False` 退回纯 score。
> **仍 ⬜**："仅差异蛋白"编排（L2）、创建后续 deep-search 任务（§8）、背景疾病/通路优先级、把更多召回路（序列/向量）真正接成 `extra_channels`。

- ⬜ 停止使用旧“肽序列近邻→借 GO/EC”作为新版假说链。
- ⬜ 定义结构邻居疾病证据输入模型。
- ⬜ 对每个差异蛋白读取 Foldseek 近邻。
- ⬜ 查询近邻 protein→gene→CTD disease 直接关系。
- ⬜ 将借来的疾病关联生成 Protein 级 `MetaAnnotation(HYPOTHESIS)`。
- ⬜ derivation 必须保存所有支持近邻、score、via gene、CTD relation 和版本。
- ⬜ 定义多近邻共识、最高分、覆盖度和置信度算法。
- ⬜ 防止目标蛋白已有 CTD 直接证据时重复生成假说。
- ⬜ 只对实验背景相关疾病/通路优先展开，同时保留查询策略。
- ⬜ 将假说幂等写入 MySQL，并创建后续 deep-search 任务。
- ⬜ 增加纯函数测试、Repository 测试和小型端到端 MVP 测试。

**MVP 验收：**

- 🟨 输入一小批已鉴定蛋白，输出同时包含 CTD 直接 `CONCLUSION` 和 Foldseek 外推 `HYPOTHESIS` 的 Meta 表，每条均可追溯。**离线/假源闭环已通过**（`test_mvp_evidence_closure.py`）；真实 CTD/Foldseek 数据联调待做。

---

## 7. Neo4j 通用 KG 与本次实验 KG

> **进展（L3 纯代码核心已落地；离线测试通过）**：新建独立的双节点知识图谱层，与旧 PSM/肽 KNN 图（§13 待 deprecate）完全隔离。
> `pkg/graph/model.py`——节点/边模型（`NodeLabel` Protein/Gene/Disease/Group、`EdgeType` ENCODED_BY/ASSOCIATED_WITH/STRUCTURAL_NEIGHBOR/DIFFERENTIAL、`GraphScope` GENERAL/EXPERIMENT、`DiseaseLink`），节点带 `mysql_ref`、EXPERIMENT 作用域强制带 `experiment_id`。
> `pkg/graph/port.py`——`GraphStore` 端口（Protocol）+ `InMemoryGraphStore`（幂等 upsert/合并、一跳 `neighbors`、跨 `ENCODED_BY` 缝合的 `protein_diseases`、`drop_experiment` 只清工作区、带过滤的 `count_*`）。
> `pkg/graph/neo4j_store.py`——`Neo4jGraphStore`（按 label/relType 分组 MERGE、`mysql_ref`/`props_json` JSON 编码、查询标量提升、`session(database=…)`、`get_kg_store` 单例；neo4j 延迟加载）。
> `application/graph/project_kg.py`——`project_experiment_kg`：读仓库蛋白/基因、CTD 基因结论、蛋白级假说、L2 差异，按 Q3/Q4 投影成两层图，幂等可重投；结构近邻当前作为可选注入（§5.2 持久化后改读仓库）。
> **仍 ⬜（B 组/后续）**：真连 Neo4j 实例集成测试、事务/重试、版本化重建与过期清理、deep-search 回写、Domain/Tissue/Taxon 等扩展节点与 HAS_DOMAIN/EXPRESSED_IN/BELONGS_TO/IN_GROUP/HAS_ANNOTATION 等扩展边。

### 7.1 GraphStore 重构

- ✅ Neo4j 驱动和基础连接配置已存在。
- ✅ 新双节点层与旧 PSM/肽 KNN 图（`store/types/cypher`）隔离，旧图 §13 待 deprecate。
- ✅ 将 `GraphStore` 拆为应用端口（`port.GraphStore`）与 `Neo4jGraphStore` 实现（另含 `InMemoryGraphStore` 测试实现）。
- ✅ 所有业务访问经过端口（`project_kg` 只调端口方法，不拼 Cypher）。
- 🟨 Neo4j session 使用配置中的 database（`session(database=…)`）；namespace/多库隔离待真实部署验证。
- 🟨 批写（按 label/relType 分组 UNWIND）与连接关闭已实现；事务、重试、连接验证待补。

### 7.2 通用 KG

- 🟨 创建 canonical 节点约束/索引：`Protein/Gene/Disease/Group` 的 key 唯一约束已实现；`Taxon/Domain/Tissue` 暂未建模。
- 🟨 创建关系：`ENCODED_BY/ASSOCIATED_WITH/STRUCTURAL_NEIGHBOR/DIFFERENTIAL` 已实现；`HAS_DOMAIN/EXPRESSED_IN` 暂未建模。
- ✅ 节点/关系保存 canonical key + `mysql_ref`（重数据不进图，Q5）；source/version 随属性按需携带。
- ✅ 公共事实只从 MySQL 投影（`project_kg` 读仓库），不以 Neo4j 为事实源。
- ⬜ 实现按版本重建、增量更新和删除过期投影（`drop_experiment` 仅清实验工作区）。

### 7.3 本次实验 KG 工作区

- 🟨 实验作用域节点：`Group` 已建模（带 `experiment_id`）；`Experiment/Peptide` 节点暂未建（`Annotation` 当前投影为带 `evidence_level` 的边而非节点）。
- ✅ 全部蛋白保留基础 `Protein` 节点（通用 KG 字典）。
- 🟨 实验关系：`DIFFERENTIAL`（Protein→Group）已实现；`BELONGS_TO/IN_GROUP/HAS_ANNOTATION` 暂未建模。
- ✅ 公共实体通过 canonical key 引用，不复制成可修改公共事实（疾病节点 GENERAL，假说性仅落在 EXPERIMENT 边）。
- ✅ 实验判断绑定 `experiment_id` 且作用域为 EXPERIMENT，不同实验互不污染（`drop_experiment` 隔离已测）。
- ⬜ deep-search 只更新实验 Annotation/历史，不直接修改公共关系（deep-search 见 §8）。
- 🟨 Cypher 结构测试已加（不连库验形状）；真实 Neo4j 集成测试待 B 组。

**阶段验收：**

- 🟨 能从 MySQL 投影出通用 KG + 一个实验工作区，删除工作区不影响通用 KG，图节点经 `mysql_ref` 回指 MySQL：**离线（内存图库）已通过**（`test_project_kg_v3.py`）；真实 Neo4j 重建/隔离联调待做。

---

## 8. Deep-search 证据验证

> **进展（L4 纯代码核心已落地；离线测试通过）**：新建 `pkg/deep_search/`——`types.py`（`DeepSearchTask`/`EvidenceRecord`/`EvidenceStance` + `LiteratureSearchSource` 可注入协议）、`verdict.py`（纯状态机 `decide_verdict`：支持→`CONCLUSION` / 反证→`REFUTED` / 冲突·无证据→保持 `HYPOTHESIS`）、`source.py`（`InMemoryLiteratureSource` 测试源 + `get_literature_search_source` 生产工厂显式拒绝 Mock）。
> `application/knowledge/deep_search.py`——`verify_experiment_hypotheses`：取实验内 `MetaAnnotation(HYPOTHESIS)`，建任务（蛋白/基因×疾病×物种×组织×背景）→ 检索 → 裁决 → 跃迁时回写 `evidence_level` + deep-search 依据入 `derivation`，每次裁决追加 `AnnotationHistory`（保留 verdict/查询/源/版本/引用）；`override_hypothesis_verdict` 支持人工覆盖（保留操作者+理由）。**幂等**：已跃迁出 HYPOTHESIS 的不再处理，历史用确定性 `history_id` 去重。
> 为此给 `ExperimentRepository`（端口 + 内存 + MySQL）补了 `list_annotation_history`。
> **仍 ⬜（B 组/后续）**：真实文献检索源（DeepXiv/MCP）、失败/超时重试与续跑、LLM model 版本记录。

### 8.1 任务与 Provider

- ✅ 定义 `DeepSearchTask`、query strategy（确定性 `query`）、verdict（`DeepSearchVerdict`）和 evidence record（`EvidenceRecord`）。
- 🟨 检索源抽象为可注入 `LiteratureSearchSource` 协议；内存测试源 + 生产工厂占位（显式拒绝 Mock）已就绪，真实 DeepXiv/MCP 工具待接。
- ✅ 查询包含蛋白/基因、疾病、物种（organism/taxon）、组织、实验背景。
- 🟨 保存检索 query、工具、版本、原始结果引用（落 `AnnotationHistory.evidence_ref` + `derivation`）；LLM model 版本待真实工具接入后补。
- 🟨 无结果已处理（→ INSUFFICIENT 保持未决）；失败/超时的恢复与重试待补。

### 8.2 状态机

- ✅ `HYPOTHESIS + 直接支持证据 → CONCLUSION`。
- ✅ `HYPOTHESIS + 无充分证据（或冲突）→ HYPOTHESIS`，显式记录未决（`insufficient`/`conflicting` 历史）。
- ✅ `HYPOTHESIS + 反证 → REFUTED`，不删除负结果（refute_refs 落库）。
- ✅ 每次变化追加 `AnnotationHistory`，不覆盖历史原因。
- ✅ 裁决幂等；同一证据重复处理不产生重复历史（确定性 `history_id` 去重）。
- ✅ 支持人工复核/覆盖，保留操作者和理由（`override_hypothesis_verdict`）。
- ✅ deep-search 只更新实验工作区 Annotation/历史，不触碰通用 KG（不自动提升为通用知识）。

**阶段验收：**

- 🟨 对一批假说完成支持/未决/反证三类裁决，并能完整回放状态变化：**离线（内存源）已通过**（`test_deep_search_v3.py`）；真实文献检索源联调待做。

---

## 9. 实验数据库冻结归档

> **进展（L5 纯代码核心已落地；离线测试通过）**：`application/experiment/freeze.py`——`freeze_experiment`：冻结前检查（每条蛋白级疾病假说须已被 deep-search 处理，否则报 `FreezePreconditionError`，可显式放行）→ 从仓库构建**确定性内容 manifest**（输入/上下文、计数、证据等级分布、全量 Meta+历史+差异+富集内容、图投影摘要、来源/pipeline/model/params 版本、request/附件 hash）→ `compute_manifest_checksum` 稳定 SHA-256 → 建 `ExperimentSnapshot(FINAL)`，版本唯一由仓库 + DDL `UNIQUE` 双重阻止覆盖。`verify_snapshot_integrity` 重算 checksum 做篡改检测。
> 为承载冻结内容给 `ExperimentSnapshot`（模型 + DDL `manifest_json` + MySQL 存取）加了 `manifest` 字段；deep-search 之后再改事实，旧快照读回（`get_snapshot`）仍不变。
> **仍 ⬜（B 组/后续）**：冻结实验 KG 到隔离 Neo4j database/namespace 的可恢复导出物、`SUPERSEDED` 编排、跨实验 canonical ID 对齐、真库版本并发。

### 9.1 已有底座

- ✅ `ExperimentSnapshot` 领域模型（新增 `manifest` 字段承载冻结内容）。
- ✅ `experiment_snapshot` MySQL DDL（新增 `manifest_json` 列）。
- ✅ 快照状态禁止 `WORKING`。

### 9.2 冻结服务

- ✅ snapshot Repository CRUD（`save/get/list_snapshots` 已在）+ 新增 `list_annotation_history`。
- 🟨 冻结前检查：deep-search 完成 gate（假说须有历史，否则报错/可放行）已实现；来源/版本完整性的强校验从简。
- ✅ 生成输入、Meta、历史、差异结果和图投影 manifest。
- ✅ 记录来源（CTD/UniProt/Foldseek 经 provenance 归集）、pipeline、model 和参数版本。
- ✅ 计算稳定 checksum。
- 🟨 manifest 含全量内容（可恢复导出物）+ 图投影摘要；冻结实验 KG 到隔离 Neo4j database/namespace ⬜。
- ✅ 快照 `FINAL` 后只读；数据库层（DDL `UNIQUE`）和应用层（`RequestVersionConflict`）均阻止覆盖。
- ✅ 新证据创建 `1.1/2.0` 等新版本，不修改旧快照（旧版本读回不变已测）。
- ⬜ 支持 `SUPERSEDED` 但不物理删除历史（模型支持该状态；自动 supersede 编排未做）。
- 🟨 快照恢复（`get_snapshot` 带 manifest）+ 审计（manifest/历史）已可；跨实验 canonical ID 对齐 ⬜。
- 🟨 篡改检测 + 只读（阻止覆盖）测试已加；版本并发（真库）测试 ⬜。

**阶段验收：**

- 🟨 一个完成实验可以冻结、校验、读回和生成新版本，旧版本内容保持不变：**离线已通过**（`test_freeze_experiment_v3.py`）；真实 MySQL/Neo4j 导出与并发联调待做。

---

## 10. 分层报告

> **进展（L6 纯代码核心已落地；离线测试通过）**：`application/report/layered_report.py`——`generate_experiment_report(experiment_id, snapshot_version)`：定位冻结快照 → `verify_snapshot_integrity` 校验完整性（篡改即拒绝）→ **只从快照 manifest** 渲染分层 Markdown（实验设计 / 差异 / 富集 / 结论 / 假说 / 伪理 / 未决 + 附录基础注释），每条带 `annotation_id` + 来源 + 版本/文献引用，并对 markdown 算 report checksum。区分公共事实（CTD 结论、UniProt 基础注释）/ 实验观察（差异、富集）/ 推导假说。因只读冻结内容，**重复生成结果稳定**。
> **仍 ⬜（后续）**：报告 artifact/checksum/snapshot_id 落库（独立报告表）、PDF/其他格式、旧 Mock 报告节点（`pipeline/nodes/generate_report.py`）的下线、大图/多版本报告测试。

- ✅ 新版报告独立于旧 Mock（`application/report/`）；旧 Mock 节点的下线见 §13。
- ✅ 报告只从指定的冻结 `snapshot_version` 生成（读 manifest，不碰活库）。
- ✅ 生成实验设计、差异结果、富集结果、结论、假说、伪理和未决项章节。
- ✅ 每条重要陈述带 Annotation ID、来源、数据库版本或文献引用。
- ✅ 区分公共事实、实验观察和推导假说。
- ✅ 报告正文以差异蛋白与证据分级为重点，附录保留全部蛋白基础注释。
- 🟨 生成 Markdown 已实现；PDF/其他格式（绑定同一快照）⬜。
- ⬜ 将报告 artifact、checksum 和 snapshot ID 写入实验数据库（独立报告表）。
- 🟨 已加确定性/防篡改/只读快照/未知版本测试；无证据/部分失败/大图/多版本报告测试 ⬜。

**阶段验收：**

- 🟨 报告中的每个结论都能追溯到冻结快照中的事实或证据，重新生成结果稳定：**离线已通过**（`test_layered_report_v3.py`）；真实快照/大规模数据联调待做。

---

## 11. API、编排与产品接入

### 11.1 API

> **进展（下游对外 API 已落地；TestClient 离线测试通过）**：新建 FastAPI 路由 `router/downstream.py`（前缀 `/ptagent/api`，已挂入 `register_routes`）。端点：`POST /experiments`（创建/校验）、`GET /experiments/{id}`（状态）、`GET …/annotations|differentials|enrichments|history`（查询，注释可按 evidence_level 过滤）、`GET …/kg/proteins/{accession}/diseases`（从蛋白展开证据路径）、`POST …/pipeline`（跑下游管线）、`POST …/freeze`、`GET …/snapshots`、`GET …/report`、`GET /health`。事实库/图库/管线 config 经 `Depends` 注入，测试用 `dependency_overrides` 注入内存实现。

- ✅ 实验 Bundle 创建/校验/查询 API（`POST /experiments` + `GET /experiments/{id}`；校验失败 → 422）。
- 🟨 health 接口已加（`GET /health`）；MySQL schema 管理/部署命令 ⬜。
- ✅ 启动下游任务 API：`POST …/pipeline`（可传 `steps` 跑子集，等价于按需启动各任务）。
- 🟨 查询 MetaAnnotation/历史/差异蛋白 API 已加；“缺失项”查询 ⬜。
- 🟨 查询本次实验 KG：`…/kg/proteins/{acc}/diseases` 证据路径 + 注释按 evidence_level 过滤已加；更全的 KG 查询/路径展开 ⬜。
- 🟨 冻结/列快照/取报告 API 已加；跨实验比较 ⬜。
- ⬜ 接入鉴权、实验所有权和审计日志。

### 11.2 Pipeline

> **进展（下游管线编排已落地；离线 e2e 通过）**：新建独立包 `application/orchestration/`——`run_downstream_pipeline` 按依赖序串 `import → base_annotation → ctd_disease → differential → enrichment → hypothesis → kg_projection → deep_search → freeze → report`；`DownstreamPipelineConfig` 注入外部源/参数，`PipelineResult`/`StepResult` 为独立状态（不复用旧 `ExecutionResults`）。每步独立 try/except（失败隔离 + `stop_on_error`），freeze 版本已存在则跳过（幂等重跑/断点续跑），`steps=` 可只跑子集，`pipeline_status` 派生进度。与旧 Mock LangGraph 主图隔离。
> **另提供 LangGraph 主图**（`orchestration/graph.py`，旧主图风格的新实现）：`StateGraph` + 下游专用共享状态 `DownstreamState`（非旧 `ExecutionResults`）+ 节点复用同一批 `execute_step`（业务逻辑不重复）+ **冻结前 `human_approval` 条件边**（approve→freeze / modify→END / reject→END）+ audit log 逐步留痕；节点级失败隔离（下游 no-op，条件边收敛 END）。当前内存 `invoke`；接 checkpointer + `interrupt_before` 即得暂停/恢复式人在回路。
> **仍 ⬜**：旧 Mock 主线（`application/pipeline/` 的 planner/scheduler/findings/report 节点）下线（§13）、真实外部源的端到端集成（B 组）、LangGraph checkpointer/streaming 接线。

- ✅ 新版下游流程定义独立状态（`PipelineResult`/`StepResult`），不复用旧 `ExecutionResults`。
- ✅ 节点顺序：import → base annotation → CTD → differential → enrichment → hypothesis → workspace KG → deep-search → freeze → report。
- ✅ 节点支持幂等重跑、断点恢复（freeze 跳过 + `steps` 子集）、失败隔离和状态查询。
- ✅ 新管线独立于旧 Mock（planner/scheduler/findings/evidence/report）；旧 Mock 主线 `application/pipeline/` 已标记 deprecated（运行时 `DeprecationWarning` + 文档，§13），待整体移除。
- ✅ 提供 LangGraph 主图（`run_downstream_graph`，旧风格新实现）：复用同一批 step + 冻结前人审批条件边 + audit log，与纯 Python runner 共存。
- 🟨 完整端到端集成测试：离线（全假源）已通过（`test_pipeline_v3.py` 纯 runner、`test_pipeline_graph_v3.py` LangGraph、`test_downstream_api_v3.py` API）；真实外部源 e2e 归 B 组。

---

## 12. 免疫维度扩展通道

- 🟨 当前策略：不建设独立免疫数据库，使用 UniProt GO、CTD 和 deep-search。
- ✅ 文档已预留 `ImmuneProcess/ImmuneCell/Cytokine/ImmunePathway` 概念。
- ⬜ 在代码中定义 `ImmuneKnowledgeProvider` 扩展协议；当前尚未实现。
- ⬜ 在 Graph Schema 中预留免疫节点/关系迁移，但当前不批量实例化。
- ⬜ 定义专用免疫数据源的启用指标：覆盖率、重复 deep-search 成本、细胞类型精度需求。
- ⬜ 若未来启用，必须走独立适配器、版本和证据分级，不修改既有业务接口。

> 本节保持 🟨，不得标记为永久关闭；它不阻塞当前 MVP。

---

## 13. 旧代码处置

- 🟨 将旧 Mock LangGraph 主线 `application/pipeline/` 标记 deprecated（包 `__init__` 加运行时 `DeprecationWarning` + 文档，指向 `application.orchestration`）；已确认 src/tests 无引用，保守起见暂不物理删除，待确认确无外部依赖后整体移除。
- ⬜ 将 `pkg/protein_db` 标记 deprecated，停止新版调用。
- ⬜ 将 `application/graph/db_assign.py` 标记 deprecated。
- ⬜ 将 `application/graph/materializer.py` 和 Casanovo loaders 移出新版运行路径。
- ⬜ 将旧 `embed_knn.py`、肽序列 embedding/KNN 与新版 Foldseek 路径明确隔离。
- ⬜ 将旧“肽近邻→GO/EC 假说”从新版入口移除。
- ⬜ 保留仍有价值的纯函数前先证明用途；否则归档或删除。
- ⬜ 在删除旧代码前建立新版替代测试，避免误伤仍由旧 API 使用的部分。
- ⬜ 更新根 README、TODO、tests README 中过时的旧上游描述。

---

## 14. 测试、质量与运维

### 14.1 当前完成

- ✅ 实验域模型和交叉引用测试。
- ✅ Repository 内存实现测试。
- ✅ MySQL DB-API schema/write/rollback 契约测试 + 读路径往返测试（列名/JSON/枚举/时区）。
- ✅ UniProt MCP 返回归一、批量和幂等测试。
- ✅ CTD parser（直接证据过滤/大小写匹配）与基因疾病结论服务（全量/幂等/未知实验）测试。
- ✅ CTD 预处理脚本测试（过滤为直接证据精简 CSV + manifest，且产物可被生产 parser 读回；含 .gz）。
- ✅ Foldseek 结构近邻测试（解析/去自身/阈值/top-k/排名 + 跨物种 大鼠→人 假源案例）。
- ✅ M3 结构类比假说测试（借 CTD/跨物种/去重已结论/幂等）+ MVP 闭环测试（结论与假说同现、可追溯）。
- ✅ UniProt MCP gene 解析测试（多返回形态/分号取首/跳过无 gene/去重批处理）。
- ✅ L2 差异分析测试（log2FC/方向/BH/无重复退化 + 服务自动选组持久化）与富集测试（超几何显著性/背景裁剪 + 疾病富集服务接线）。
- ✅ L3 知识图谱测试：图模型/端口契约 + Neo4j Cypher 形状 + 投影服务（双节点/两层/遍历/幂等/删工作区隔离）。
- ✅ L4 deep-search 测试：纯状态机/检索源 + 服务（三态跃迁/幂等/历史回放/人工覆盖/隔离）。
- ✅ L5 冻结归档测试：FINAL 快照 + manifest/checksum、冻结前检查、只读/阻止覆盖、版本化（旧版不变）、篡改检测。
- ✅ 富集持久化测试：服务写全量结果 + study/background checksum + 幂等重跑 + MySQL 往返。
- ✅ L6 分层报告测试：分层章节/可追溯陈述、确定性、只读冻结快照、防篡改、未知版本。
- ✅ 下游管线编排测试：纯 runner 端到端 9 步全过、幂等重跑（freeze 跳过）、失败隔离、子集执行、状态查询。
- ✅ 下游 LangGraph 主图测试：approve 全流程、reject/modify 冻结前停、失败隔离、人审批路由单测、图可编译。
- ✅ 下游对外 API 测试：创建/校验(422)/查询、跑管线、KG 证据路径、快照/报告、未知实验(404)、重复冻结(409)。
- ✅ M3 结构近邻 RRF 融合重排测试：rerank_neighbors（覆盖度可反超 score / 额外通道 / 降序）+ M3 支持近邻按融合分重排、confidence 兼容、rerank=False 退回。
- ✅ 当前全量测试：`198 passed, 1 skipped`。

### 14.2 待补测试

- ⬜ 真实 MySQL 集成测试。
- ⬜ 真实 UniProt MCP 集成测试。
- ⬜ CTD parser/版本/证据过滤测试。
- ⬜ 差异统计数值正确性测试。
- ⬜ Foldseek 小数据库集成测试。
- 🟨 新 Neo4j Schema/事务/隔离测试：内存图库 + Cypher 形状测试已过；真实 Neo4j 集成测试 ⬜。
- 🟨 deep-search 状态机与幂等测试：离线（内存源）已过；真实文献检索源集成测试 ⬜。
- 🟨 快照只读、版本、checksum 和恢复测试：离线已过（manifest/checksum/只读/版本化/篡改）；真库版本并发 ⬜。
- ⬜ 从真实三件套到冻结报告的端到端测试。
- ⬜ 大规模蛋白/肽批写、图投影和检索性能测试。

### 14.3 运维与安全

- ⬜ MySQL、Neo4j、MCP、CTD、Foldseek 健康检查。
- ⬜ 结构化日志统一携带 experiment_id/run_id/snapshot_id。
- ⬜ 指标：覆盖率、缺失率、调用耗时、错误率、deep-search 队列和快照数量。
- ⬜ 密钥只通过环境/secret manager 注入，不进入日志、快照或 Git。
- ⬜ 数据库备份、恢复和保留周期。
- ⬜ 外部数据库许可和引用要求记录。
- ⬜ 生产迁移回滚方案。

---

## 15. 外部依赖清单

- 🟨 MySQL 实例、数据库、用户权限和 PyMySQL 安装。
- 🟨 UniProt MCP 的真实工具名、参数、返回 Schema 和 Provider 可用性。
- ⬜ CTD 数据下载地址、版本和许可确认。
- ⬜ AlphaFold DB/Foldseek 数据、索引、磁盘与计算资源。
- ⬜ Neo4j 实例和新版 Schema 部署；是否使用独立 database 取决于部署能力，至少保证 namespace 隔离。
- ⬜ deep-search 工具、凭证、文献引用格式和裁决策略。
- ⬜ 一份可公开或内部使用的真实小型实验三件套，作为 MVP ground truth。

---

## 16. 里程碑与完成定义

### Milestone A：数据底座

- 🟨 代码已完成；真实 MySQL round-trip 后转为 ✅。

### Milestone B：全量基础结论

- 🟨 UniProt 代码已完成；真实 MCP 联调完成后转为 ✅。
- ✅ CTD 直接疾病结论：代码 + **真实数据已验证**（9,114 基因 / 34,253 直接事实；STAT3、Casp3→Brain Ischemia 等命中）。

### Milestone C：核心 MVP

- 🟨 差异蛋白集合可查询：差异引擎+服务可产出并由 `list_differentials` 派生差异集；真实定量联调后转 ✅。
- 🟨 Foldseek 结构近邻可复现：引擎+离线测试完成；真实 Foldseek/AF DB 联调后转 ✅。
- 🟨 结构近邻借 CTD 生成假说：代码 + 离线闭环测试完成；真实数据联调后转 ✅。
- 🟨 输出结论/假说 Meta 表并通过案例验收：离线 MVP 闭环已过；真实案例待联调。

### Milestone D：知识图谱工作区

- 🟨 通用 KG 和本次实验 KG 可从 MySQL 重建：投影服务 + 离线（内存图库）已通过；真实 Neo4j 重建联调 ⬜。
- 🟨 公共知识与实验判断隔离：GENERAL/EXPERIMENT 两层 + `drop_experiment` 隔离已测；真库验证 ⬜。
- ⬜ 前端/API 可查询证据路径（端口已有 `protein_diseases`/`neighbors` 遍历；API 见 §11）。

### Milestone E：闭环交付

- 🟨 deep-search 完成三态跃迁：状态机 + 回写/历史/幂等/人工覆盖 + 离线（内存源）已通过；真实文献检索源联调 ⬜。
- 🟨 实验 KG 冻结为不可变版本：冻结服务 + manifest/checksum + 只读/版本化 + 篡改检测 + 离线已通过；隔离 Neo4j 导出/真库并发 ⬜。
- 🟨 从冻结快照生成可审计报告：分层报告 + 可追溯/确定性/防篡改 + 离线已通过；报告落库/PDF/真实数据联调 ⬜。
- ⬜ 完成真实端到端测试、部署说明和恢复演练。

---

## 17. 推荐执行顺序

1. 🟨 完成真实 MySQL 与 UniProt MCP 两个外部 smoke test。
2. 🟨 CTD parser、直接证据过滤和 gene-disease Meta：代码完成；真实文件下载/联调 ⬜。
3. ⬜ 完成定量/差异 Repository 与差异蛋白选择。
4. 🟨 Foldseek `StructureSearchProvider`：引擎+解析/筛选/假源测试完成；真实二进制/AF DB 联调 ⬜。
5. 🟨 新版结构疾病假说 + 最小 Meta 闭环：代码完成（离线 MVP 闭环测试通过）；真实数据联调 ⬜。
6. 🟨 重构 `GraphStore` 并构建通用 KG/实验工作区：端口 + 内存/Neo4j 实现 + 投影服务 + 离线测试完成；真连 Neo4j 联调 ⬜。
7. 🟨 接入 deep-search 状态机：任务/证据/可注入源 + 纯状态机 + 回写/历史/幂等/人工覆盖 + 离线测试完成；真实文献检索源联调 ⬜。
8. 🟨 实现冻结归档和版本管理：冻结前检查 + manifest + checksum + FINAL 只读/版本化 + 篡改检测 + 离线测试完成；隔离 Neo4j 导出/真库并发 ⬜。
9. 🟨 实现分层报告与 API/Pipeline 集成：分层报告（从冻结快照出可审计 Markdown）+ 离线测试完成；报告落库、API/Pipeline 集成（§11）⬜。
10. ⬜ 清理旧上游和旧 KNN 代码路径，完成生产质量验证。

---

## 18. 当前已完成文件索引

> 按模块分组（实现 + 对应测试同列），便于分辨各层归属。

### S1 · 实验输入与 MySQL 事实库

- ✅ [`src/pkg/experiment/types.py`](../src/pkg/experiment/types.py)：实验域模型（含 `EnrichmentRecord`、快照 `manifest`）。
- ✅ [`src/pkg/experiment/repository.py`](../src/pkg/experiment/repository.py)：Repository 契约与内存实现。
- ✅ [`src/pkg/experiment/schema.py`](../src/pkg/experiment/schema.py)：MySQL DDL。
- ✅ [`src/pkg/experiment/mysql_store.py`](../src/pkg/experiment/mysql_store.py)：MySQL Store。
- ✅ [`src/pkg/experiment/ingest.py`](../src/pkg/experiment/ingest.py)：三件套导入。
- ✅ [`src/pkg/experiment/identity.py`](../src/pkg/experiment/identity.py)：稳定 Annotation ID。
- ✅ [`src/application/experiment/context_mapper.py`](../src/application/experiment/context_mapper.py)：HTTP→Domain Context 显式转换。
- ✅ [`src/application/experiment/request_service.py`](../src/application/experiment/request_service.py)：不可变原始请求版本记录。
- 🧪 [`tests/pkg/test_experiment_models.py`](../tests/pkg/test_experiment_models.py)、[`tests/pkg/test_experiment_mysql_store.py`](../tests/pkg/test_experiment_mysql_store.py)、[`tests/test_experiment_context_mapper.py`](../tests/test_experiment_context_mapper.py)、[`tests/test_experiment_request_versions.py`](../tests/test_experiment_request_versions.py)。

### L1 · UniProt 全量基础注释

- ✅ [`src/pkg/annotation/knowledge.py`](../src/pkg/annotation/knowledge.py)：标准蛋白注释事实。
- ✅ [`src/pkg/annotation/uniprot_mcp.py`](../src/pkg/annotation/uniprot_mcp.py)：UniProt MCP 适配。
- ✅ [`src/application/knowledge/protein_enrichment.py`](../src/application/knowledge/protein_enrichment.py)：全量蛋白基础注释服务。
- ✅ [`src/config/annotation_settings.py`](../src/config/annotation_settings.py)：注释配置。
- 🧪 [`tests/pkg/test_uniprot_mcp_annotation.py`](../tests/pkg/test_uniprot_mcp_annotation.py)、[`tests/test_protein_enrichment_v3.py`](../tests/test_protein_enrichment_v3.py)。

### M1 · CTD 基因—疾病结论

- ✅ [`src/pkg/disease/types.py`](../src/pkg/disease/types.py)：基因-疾病事实与数据源协议。
- ✅ [`src/pkg/disease/ctd.py`](../src/pkg/disease/ctd.py)：CTD parser 与文件数据源。
- ✅ [`src/application/knowledge/disease_annotation.py`](../src/application/knowledge/disease_annotation.py)：全量基因 CTD 结论服务。
- ✅ [`src/config/ctd_settings.py`](../src/config/ctd_settings.py)：CTD 配置。
- ✅ [`scripts/prepare_ctd.py`](../scripts/prepare_ctd.py)：CTD 大文件→直接证据精简 CSV + manifest。
- 🧪 [`tests/pkg/test_ctd_parser.py`](../tests/pkg/test_ctd_parser.py)、[`tests/test_disease_annotation_v3.py`](../tests/test_disease_annotation_v3.py)、[`tests/test_prepare_ctd.py`](../tests/test_prepare_ctd.py)。

### M2 · Foldseek 结构近邻

- ✅ [`src/pkg/structure/types.py`](../src/pkg/structure/types.py)：结构近邻结果与数据源协议。
- ✅ [`src/pkg/structure/foldseek.py`](../src/pkg/structure/foldseek.py)：Foldseek 解析/筛选/检索数据源。
- ✅ [`src/pkg/structure/rerank.py`](../src/pkg/structure/rerank.py)：结构近邻多路 RRF 融合重排（复用 `pkg.retrieval`，M3 用）。
- ✅ [`src/config/structure_settings.py`](../src/config/structure_settings.py)：结构检索配置。
- 🧪 [`tests/pkg/test_foldseek_structure.py`](../tests/pkg/test_foldseek_structure.py)、[`tests/pkg/test_structure_rerank.py`](../tests/pkg/test_structure_rerank.py)。

### L2 · 差异分析 + 富集（含富集持久化）

- ✅ [`src/pkg/analysis/differential.py`](../src/pkg/analysis/differential.py)：差异分析引擎（log2FC+Welch t+BH）。
- ✅ [`src/pkg/analysis/enrichment.py`](../src/pkg/analysis/enrichment.py)：过表达富集引擎（超几何+BH）。
- ✅ [`src/application/analysis/differential_analysis.py`](../src/application/analysis/differential_analysis.py)：差异分析服务。
- ✅ [`src/application/analysis/enrichment_analysis.py`](../src/application/analysis/enrichment_analysis.py)：疾病富集服务（含持久化 + study/background checksum）。
- 🧪 [`tests/test_differential_v3.py`](../tests/test_differential_v3.py)、[`tests/test_enrichment_v3.py`](../tests/test_enrichment_v3.py)、[`tests/test_enrichment_persist_v3.py`](../tests/test_enrichment_persist_v3.py)。

### M3 · 结构类比假说

- ✅ [`src/pkg/disease/gene_resolver.py`](../src/pkg/disease/gene_resolver.py)：accession→gene 解析协议与内存实现。
- ✅ [`src/application/knowledge/hypothesis_generation.py`](../src/application/knowledge/hypothesis_generation.py)：结构类比假说服务（M3）。
- 🧪 [`tests/test_hypothesis_generation_v3.py`](../tests/test_hypothesis_generation_v3.py)、[`tests/test_mvp_evidence_closure.py`](../tests/test_mvp_evidence_closure.py)、[`tests/pkg/test_uniprot_gene_resolver.py`](../tests/pkg/test_uniprot_gene_resolver.py)。

### L3 · 本次实验 KG（Neo4j GraphStore）

- ✅ [`src/pkg/graph/model.py`](../src/pkg/graph/model.py)：双节点图模型（节点/边/作用域/DiseaseLink）。
- ✅ [`src/pkg/graph/port.py`](../src/pkg/graph/port.py)：`GraphStore` 端口 + `InMemoryGraphStore`。
- ✅ [`src/pkg/graph/neo4j_store.py`](../src/pkg/graph/neo4j_store.py)：`Neo4jGraphStore` 实现 + `get_kg_store` 单例。
- ✅ [`src/application/graph/project_kg.py`](../src/application/graph/project_kg.py)：MySQL 事实 → 两层知识图谱投影服务。
- 🧪 [`tests/pkg/test_graph_kg_store.py`](../tests/pkg/test_graph_kg_store.py)、[`tests/test_project_kg_v3.py`](../tests/test_project_kg_v3.py)。

### L4 · deep-search 认知态跃迁

- ✅ [`src/pkg/deep_search/types.py`](../src/pkg/deep_search/types.py)：任务/证据/可注入检索源协议。
- ✅ [`src/pkg/deep_search/verdict.py`](../src/pkg/deep_search/verdict.py)：纯状态机（证据→证据等级裁决）。
- ✅ [`src/pkg/deep_search/source.py`](../src/pkg/deep_search/source.py)：内存检索源 + 生产源工厂占位（拒绝 Mock）。
- ✅ [`src/application/knowledge/deep_search.py`](../src/application/knowledge/deep_search.py)：验证服务（回写 evidence_level/历史/幂等/人工覆盖）。
- 🧪 [`tests/pkg/test_deep_search_verdict.py`](../tests/pkg/test_deep_search_verdict.py)、[`tests/test_deep_search_v3.py`](../tests/test_deep_search_v3.py)。

### L5 · 实验冻结归档

- ✅ [`src/application/experiment/freeze.py`](../src/application/experiment/freeze.py)：冻结归档服务（manifest/checksum/前置检查/只读/篡改检测）。
- 🧪 [`tests/test_freeze_experiment_v3.py`](../tests/test_freeze_experiment_v3.py)。

### L6 · 分层报告

- ✅ [`src/application/report/layered_report.py`](../src/application/report/layered_report.py)：从冻结快照生成可审计 Markdown 报告（分层 + 可追溯 + 确定性）。
- 🧪 [`tests/test_layered_report_v3.py`](../tests/test_layered_report_v3.py)。

### §11.2 · 下游管线编排

- ✅ [`src/application/orchestration/pipeline.py`](../src/application/orchestration/pipeline.py)：纯 Python 线性 runner `run_downstream_pipeline`（9 步依赖序 + 失败隔离 + 幂等/断点 + 状态查询）+ 共用 `execute_step` + `pipeline_status`。
- ✅ [`src/application/orchestration/graph.py`](../src/application/orchestration/graph.py)：LangGraph 主图 `build_downstream_graph` / `run_downstream_graph`（共享状态 + 冻结前人审批条件边 + audit log，复用 `execute_step`）。
- 🧪 [`tests/test_pipeline_v3.py`](../tests/test_pipeline_v3.py)、[`tests/test_pipeline_graph_v3.py`](../tests/test_pipeline_graph_v3.py)。

### §11.1 · 下游对外 API

- ✅ [`src/router/downstream.py`](../src/router/downstream.py)：FastAPI 路由（实验创建/查询、跑管线、查注释/差异/富集/历史、KG 证据路径、冻结/快照/报告、health；DI 可注入）。
- 🧪 [`tests/test_downstream_api_v3.py`](../tests/test_downstream_api_v3.py)。
