# Neo4j KG 集成 Smoke

该 smoke 验证现有的 `Neo4jGraphStore` 与 `project_experiment_kg` 能在本机真实
MySQL 和 Neo4j 服务之间工作；它不是新的生产图实现。

## 前置条件

1. `.env` 中设置 `PTAGENT_GRAPH__PASSWORD`，并与 Compose 的 `NEO4J_AUTH` 使用同一密码。
2. MySQL 与 Neo4j 容器均已运行：

   ```bash
   docker compose up -d mysql neo4j
   ```

3. Neo4j Bolt 已能认证。例如：

   ```bash
   docker compose exec neo4j cypher-shell -u neo4j -p '<.env 中的密码>' "RETURN 1 AS connected;"
   ```

## 运行

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke/neo4j_kg_mysql_smoke.py
```

脚本会创建两个带时间戳的 MySQL 测试实验；每个实验包含基因结论、蛋白级假说、差异边、
结构近邻边和融合候选边。随后它会：

1. 创建 Neo4j 约束并通过 Bolt 执行查询；
2. 将两个实验投影到 Neo4j；
3. 验证 Protein→Gene→Disease 与 Protein→Disease 遍历、结构边和候选边；
4. 重投第一个实验，验证关系幂等；
5. 删除第一个实验工作区，验证第二个实验不受影响、通用知识事实仍存在；
6. 默认也清理第二个实验工作区。

它不会删除 Neo4j 的通用节点和通用事实，因为它们属于共享知识层。若要在 Neo4j Browser
中观察第二个实验工作区，可追加 `--keep-peer-workspace`；之后可通过
`Neo4jGraphStore.drop_experiment(peer_experiment_id)` 清理该工作区。

## 状态输出

在清理主实验工作区**之前**，脚本会打印两个 JSON 对象：

- `kg_state`：该实验的工作区节点/边数量、关键 Protein/Gene/Disease/Group 节点、
  Protein→Disease 遍历结果、`STRUCTURAL_NEIGHBOR` 与 `CANDIDATE_NEIGHBOR` 边及其
  `evidence_id`/`run_id`/rank/score 等轻量属性。
- `structure_state`：MySQL 中的 `StructureSearchRun`、`StructureNeighborEvidence` 和
  `StructureEvidenceStatus`，以及融合候选使用的 `sequence_search_runs`、
  `sequence_neighbor_evidence` 与 `sequence_statuses`。本 smoke 手工写入一个已完成的
  结构检索 run、一条结构近邻和一条指向**同一邻居**的序列近邻；未做 StructureCatalog
  输入，因此 `catalog_statuses` 为空是预期结果。

这两段输出对应同一个 `experiment_id`，可用来将 Neo4j 关系回溯至 MySQL 结构检索证据。
当前图模型有 `STRUCTURAL_NEIGHBOR` 和 `CANDIDATE_NEIGHBOR`，没有单独的
`SEQUENCE_NEIGHBOR` 图边：序列的原始命中保存在 MySQL，融合后通过
`CANDIDATE_NEIGHBOR.support_channels` 和 `evidence_ids` 回指。这避免把每个检索通道的
大量明细都复制进 Neo4j。

## 真实全线实验留存与验收

独立 fixture smoke 通过后，下一步运行一次真实 Foldseek、sequence/domain fusion、CTD、
PubMed 和 Neo4j 全链路。默认脚本会清理 EXPERIMENT 工作区；人工验收时必须保留它：

```bash
.venv/bin/python \
  scripts/smoke/foldseek_sequence_domain_hypothesis_real_smoke.py \
  --include-deep-search \
  --graph-store neo4j \
  --keep-neo4j-workspace
```

保存输出中的 `experiment_id`，然后在 Neo4j Browser（`http://127.0.0.1:7474`）执行：

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

人工验收应确认 `O60674` 的前 5 个 fused candidates、`Q09178`/`JAK1` 和
`Lupus Nephritis` hypothesis 均存在；`Comparison` 同时连向 case/control；第 6–10 名
candidate 未进入 KG。PubMed 原始 evidence 必须留在 MySQL evidence ledger 与冻结快照，
而不是复制成 GENERAL 图边。

接着执行不写 Neo4j 的重建检查：

```bash
.venv/bin/python scripts/maintenance/rebuild_neo4j_v2.py \
  --experiment-id 刚生成的实验ID
```

预期输出：

```text
mode: dry-run
frozen_graph_matches: True
neo4j_changed: False
```

这一步验证 MySQL 事实、冻结图 manifest 和可重建图完全一致。更完整的生产稳定性、重启、
双实验隔离、失败恢复、规模测试和最终迁移顺序见
[`neo4j-improvement-plan.md`](neo4j-improvement-plan.md#下一阶段真实数据稳定性与生产验收)。
