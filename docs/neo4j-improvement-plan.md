# Neo4j Improvement Plan

## 目标

把当前可联调的 Neo4j 原型升级为可审计、可重建、跨物种安全、实验隔离明确的知识图谱后端；
MySQL 继续作为唯一事实源，Neo4j 只保存稳定实体、可遍历关系和必要的证据回指。

## 基线与约束

- 当前代码基线：`268 passed, 1 skipped, 1 warning`。
- 当前本机 Neo4j 只有 smoke fixture：62 个 GENERAL 节点、32 条 GENERAL 关系、
  14 个孤立节点，无 EXPERIMENT 关系。
- 不在迁移代码中自动删除已有 Neo4j 数据；旧图通过显式重建命令迁移。
- Neo4j Community 只使用默认 `neo4j` database；隔离依靠 canonical key、scope 与
  `experiment_id`，不依赖多数据库。

## 实施顺序

### Phase 1：稳定实体身份

- [x] 新增统一 canonical key 层。
- [x] Protein accession 在入图前统一归一化。
- [x] Gene key 优先使用 NCBI Gene ID；无 ID 时使用 `taxon_id + normalized symbol`。
- [x] Gene 节点保留 `symbol`、`taxon_id`、`ncbi_gene_id` 属性。
- [x] 覆盖同名跨物种、大小写、isoform/raw accession 测试。

验收：不同物种同名基因不合并；同物种大小写变体不分裂；Protein/Gene 遍历保持正确。

### Phase 2：稳定关系身份与证据完整性

- [x] CTD GENERAL 关系不再使用包含 experiment ID 的 annotation ID；改用
  gene/disease/source/version/relation ID 生成稳定 key。
- [x] STRUCTURAL_NEIGHBOR key 包含 provider 与数据库版本，避免跨版本覆盖。
- [x] GENERAL 结构边不保存某次实验专属 evidence ID；实验 evidence 留在 MySQL。
- [x] 投影 FusedCandidate 前校验 evidence ID 存在，并验证 query/target/channel 一致。
- [x] projection policy 已支持结构 score/coverage 与 fused score 注入；默认值留待真实数据校准。

验收：跨实验相同公共事实幂等；跨数据库版本可并存；伪造或错配 evidence 无法入图。

### Phase 3：原子投影与过期关系对账

- [x] GraphStore 增加 `replace_experiment_projection` 原子接口。
- [x] Neo4j 在单个 write transaction 中清理目标实验旧工作区、写节点、写边。
- [x] 写入前验证每条边的两个端点均存在于期望子图。
- [x] Neo4j 写入返回实际处理计数，禁止静默丢弃 MATCH 不到端点的边。
- [x] InMemoryGraphStore 与 Neo4jGraphStore 使用相同 replace 契约。
- [x] 使用 driver managed transaction 重试，并增加回滚边界/stale-edge 契约测试。

验收：一次投影全成或全败；重投影会删除本实验过期边；失败不留下半张图。

### Phase 4：认知状态同步与查询隔离

- [x] pipeline 改为 deep-search 后投影 KG，保证 HYPOTHESIS/CONCLUSION/REFUTED 一致。
- [x] `neighbors` 仅在提供匹配 experiment ID 时返回 EXPERIMENT 关系。
- [x] `protein_diseases` 强制实验上下文，不再隐式返回所有实验假说。
- [x] 增加跨实验不可见性与 pipeline verdict 同步测试。

验收：MySQL verdict、Neo4j 边和报告状态一致；任一实验无法读取另一实验的候选/假说边。

### Phase 5：可冻结、可恢复的图快照

- [x] KG 投影层生成按实验确定性排序的完整子图 manifest。
- [x] freeze 保存节点/边记录、图 schema version 与 checksum，而非仅计数。
- [x] snapshot integrity 通过外层 manifest checksum 同时覆盖图 manifest。
- [x] 重建工具比较 MySQL 重投影 checksum 与冻结图 checksum。

验收：快照能证明冻结时的图内容，并能检测 Neo4j 漂移或重建差异。

### Phase 6：Neo4j/GNN 属性模型

- [x] 常用节点和边特征改为 Neo4j 原生标量/数组属性。
- [x] `mysql_ref` 提升常用回指字段，JSON 仅保留不参与查询的扩展内容。
- [x] 修复 Neo4j 与 InMemory 对属性 merge 的语义差异。
- [x] 增加确定性 GNN 导出：node table、edge index、feature schema、label map。
- [x] 将差异比较显式建模为 Comparison，case/control Group 均有明确连接。

验收：常用特征可直接 Cypher 筛选；同一快照导出相同 node index/edge index。

### Phase 7：生命周期与运维安全

- [x] 增加只清理无引用 smoke/orphan GENERAL 实体的显式维护命令（默认 dry-run）。
- [x] Neo4j 端口仅绑定 `127.0.0.1`。
- [x] 固定 Neo4j 镜像补丁版本与 Python driver 上界。
- [x] Compose 增加 healthcheck；driver 增加 connectivity check、timeout、retry 配置。
- [x] 增加实验查询索引和应用关闭时 driver cleanup。

验收：默认配置不暴露局域网；服务启动可探活；清理命令不会删除仍被实验引用的公共事实。

### Phase 8：迁移与最终验收

- [x] 提供 schema v1 → v2 的显式重建脚本；默认只显示计划，不自动删库。
- [x] 在本机真实 MySQL + Neo4j 运行独立 KG smoke。
- [x] 将全线 Foldseek → fusion → PubMed pipeline 切换到真实 Neo4j 并验证。
- [x] 跑完整测试、差异检查，并更新实施清单。

验收：真实全线状态、冻结图和 Neo4j 查询一致；完整回归通过。

## 风险控制

- canonical key 和关系 key 变化属于 schema v2，不原地混用 v1/v2 图。
- 每个 phase 独立测试并更新本文件；前一阶段未通过，不进入后一阶段。
- 所有清理/重建操作显式 opt-in，先 dry-run 输出数量与目标 key。

## 当前状态

**Completed (2026-07-13)**：8 个阶段全部完成。完整回归 `280 passed, 1 skipped`；
独立 MySQL→Neo4j smoke 与 Foldseek→fusion→PubMed→Neo4j 全线 smoke 均通过；
重建 dry-run 的图 checksum 与冻结快照一致，且未修改 Neo4j。

## 下一阶段：真实数据稳定性与生产验收

> **状态：待执行。** 当前 smoke 证明功能链路可运行；以下验收用于证明真实数据、
> 容器重启、失败恢复和规模压力下仍可稳定工作。完成前不得执行 schema v2 的整图
> reset。详细的一次真实实验操作和 Cypher 查询见
> [`neo4j-smoke.md`](neo4j-smoke.md#真实全线实验留存与验收)。

### 1. 留存一份真实全线实验图并人工核查（当前优先）

运行真实 Foldseek → fusion → PubMed → Neo4j 全链路，并保留 EXPERIMENT 工作区：

```bash
.venv/bin/python \
  scripts/smoke/foldseek_sequence_domain_hypothesis_real_smoke.py \
  --include-deep-search \
  --graph-store neo4j \
  --keep-neo4j-workspace
```

记录脚本输出的 `experiment_id`。人工核查应确认：

- `O60674` 连接前 5 个 fused candidates；
- `Q09178`/`JAK1` 出现；
- `Lupus Nephritis` 的 hypothesis 连接正确；
- 每个 `Comparison` 同时连接 case 与 control；
- fusion rank 6–10 的 candidate 没有进入 KG；
- PubMed evidence 保留在 MySQL evidence ledger 和冻结快照中，未被错误复制为
  GENERAL 图边。

### 2. Neo4j Browser 查询验收（当前优先）

访问 `http://127.0.0.1:7474`，在 Browser 执行以下查询，并将查询结果与上一步的
`experiment_id`、MySQL 记录及冻结 manifest 对照：

```cypher
MATCH path=(p:Protein {key: "O60674"})-[*1..3]->(n)
RETURN path
LIMIT 100;
```

```cypher
MATCH (p:Protein {key: "O60674"})
      -[r:CANDIDATE_NEIGHBOR]->(candidate:Protein)
RETURN candidate.key,
       r.fusion_rank,
       r.fused_score,
       r.support_channels
ORDER BY r.fusion_rank;
```

```cypher
MATCH path=(p:Protein)-[:DIFFERENTIAL_IN]->(c:Comparison)
           -[:CASE_GROUP|CONTROL_GROUP]->(g:Group)
WHERE c.experiment_id = "刚生成的实验ID"
RETURN path;
```

### 3. 冻结图与 MySQL 重建一致性（当前优先）

对刚生成的实验只运行 dry-run：

```bash
.venv/bin/python scripts/maintenance/rebuild_neo4j_v2.py \
  --experiment-id 刚生成的实验ID
```

必须包含：

```text
mode: dry-run
frozen_graph_matches: True
neo4j_changed: False
```

这证明从 MySQL 事实重建出的确定性图 manifest 与冻结图 checksum 一致，且 dry-run
没有修改 Neo4j。

### 4. 容器重启后的持久化

保留上述实验工作区后执行：

```bash
docker compose restart neo4j
docker compose ps neo4j
```

待服务恢复 `healthy` 后，重新执行第 2 步 Browser 查询并确认节点、关系、原生属性和
`experiment_id` 均仍存在，且应用可以重新连接。

### 5. 两个真实实验的隔离

用两个真实 pipeline 实验重复第 1–3 步，并验证：

- GENERAL 的 Protein/Gene/Disease 可共享；
- Comparison、Group、candidate 和 hypothesis 边不跨实验；
- 用实验 A 的 ID 查询不到实验 B 的 EXPERIMENT 边；
- 删除实验 A 工作区不会影响实验 B。

现有 fixture 基线仍应保留：

```bash
.venv/bin/python scripts/smoke/neo4j_kg_mysql_smoke.py
```

### 6. 事务失败与恢复

主动构造并记录以下失败注入：candidate 引用不存在的 evidence、candidate evidence 的
query/target 不一致、写关系缺少端点、Neo4j 在投影中断开，以及重投影时 MySQL 数据变化。

每种情形的验收条件：投影整体回滚；原实验图保持完整；不留下部分节点或孤立
EXPERIMENT 边；消除故障后可再次成功投影。

### 7. 性能与规模

按下列规模运行投影与重投影：

| 规模 | Protein 数 | 目的 |
|---|---:|---|
| 小型 | 100 | 功能基线 |
| 中型 | 1,000 | 批量投影和查询延迟 |
| 大型 | 10,000+ | 内存、索引和事务压力 |

每次记录 KG 投影耗时、Neo4j 节点/关系写入速度、Protein→candidate→disease 查询时间、
freeze manifest 与 GNN export 的耗时/文件大小，以及重投影删除与写入耗时。

### 8. schema v2 正式迁移（最后执行）

仅在前述验收全部通过后，先对既有正式实验执行第 3 步 dry-run。确认后才允许执行以下
**破坏性操作**；它会清空当前 Neo4j 图，并仅从指定 MySQL 实验重建：

```bash
.venv/bin/python scripts/maintenance/rebuild_neo4j_v2.py \
  --experiment-id EXP_ID \
  --apply \
  --reset-graph \
  --confirm-reset RESET_NEO4J_V2
```
