"""集中存放 Cypher 语句;store.py 引用这里的常量。不依赖包内其他模块。"""
from __future__ import annotations

# ───────────────────────── ① 约束(身份 / MERGE 去重键)─────────────────────────
CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT sample_id   IF NOT EXISTS FOR (s:Sample)       REQUIRE s.sample_id   IS UNIQUE",
    "CREATE CONSTRAINT spectrum_id IF NOT EXISTS FOR (x:Spectrum)     REQUIRE x.spectrum_id IS UNIQUE",
    "CREATE CONSTRAINT psm_id      IF NOT EXISTS FOR (p:PSM)          REQUIRE p.psm_id      IS UNIQUE",
    "CREATE CONSTRAINT peptidoform IF NOT EXISTS FOR (e:Peptide)      REQUIRE e.peptidoform IS UNIQUE",
    "CREATE CONSTRAINT protein_acc IF NOT EXISTS FOR (pr:Protein)     REQUIRE pr.accession  IS UNIQUE",
    "CREATE CONSTRAINT group_id    IF NOT EXISTS FOR (g:ProteinGroup) REQUIRE g.group_id    IS UNIQUE",
]

# ───────────────────────── ② 索引(查询 / 溯源 / FDR 加速)─────────────────────────
INDEXES: list[str] = [
    "CREATE INDEX psm_run    IF NOT EXISTS FOR (p:PSM)      ON (p.run_id)",
    "CREATE INDEX psm_qvalue IF NOT EXISTS FOR (p:PSM)      ON (p.q_value)",
    "CREATE INDEX spec_dobj  IF NOT EXISTS FOR (x:Spectrum) ON (x.data_object_id)",
    # novelty 路由 / 富集回填加速(属性还没写时索引也安全,只索引有该属性的节点)
    "CREATE INDEX pep_novel  IF NOT EXISTS FOR (e:Peptide)  ON (e.is_novel)",
    "CREATE INDEX prot_annot IF NOT EXISTS FOR (pr:Protein) ON (pr.annot_version)",
]

# ───────────────────────── ③ 主干 materialize ─────────────────────────
MERGE_TRUNK: str = """
UNWIND $rows AS r
MERGE (s:Sample {sample_id: r.sample_id})
  ON CREATE SET s.name = r.sample_name, s.condition = r.condition
MERGE (sp:Spectrum {spectrum_id: r.spectrum_id})
  ON CREATE SET sp.precursor_mz   = r.precursor_mz,
                sp.charge         = r.charge,
                sp.retention_time = r.retention_time,
                sp.scan_index     = r.scan_index,
                sp.data_object_id = r.spectra_object_id
MERGE (s)-[:PRODUCED]->(sp)
MERGE (pep:Peptide {peptidoform: r.peptidoform})
  ON CREATE SET pep.stripped_sequence = r.stripped_sequence,
                pep.length            = r.length
MERGE (psm:PSM {psm_id: r.psm_id})
  ON CREATE SET psm.score          = r.score,
                psm.q_value        = r.q_value,
                psm.aa_scores      = r.aa_scores,
                psm.search_engine  = r.search_engine,
                psm.is_decoy       = coalesce(r.is_decoy, false),
                psm.run_id         = r.run_id,
                psm.data_object_id = r.result_object_id
MERGE (sp)-[:HAS_PSM]->(psm)
MERGE (psm)-[:IDENTIFIES]->(pep)
"""

# ───────────────────────── ④ 蛋白层 materialize(数据库搜索)─────────────────────────
MERGE_PEP_PROT: str = """
UNWIND $pep_prot AS pp
MATCH (pep:Peptide {peptidoform: pp.peptidoform})
MERGE (prot:Protein {accession: pp.accession})
  ON CREATE SET prot.description = pp.description
MERGE (pep)-[:BELONGS_TO]->(prot)
"""

# ───────────────────────── ⑤⑥ 蛋白推断(按顺序执行)─────────────────────────
# 注意:GDS 内存图、wcc 是有状态的多步操作,所以拆成一个有序列表逐句跑。
INFERENCE_STEPS: list[str] = [
    # 5.0 若内存图已存在先删(第二个参数 false = 不存在也不报错)→ 幂等
    "CALL gds.graph.drop('pep_prot', false) YIELD graphName RETURN graphName",
    # 5.1 投影「肽段-蛋白」二部图(无向)
    """
    CALL gds.graph.project('pep_prot', ['Peptide','Protein'],
         { BELONGS_TO: { orientation: 'UNDIRECTED' } })
    YIELD graphName RETURN graphName
    """,
    # 5.2 弱连通分量 → 每个节点写 componentId
    "CALL gds.wcc.write('pep_prot', { writeProperty: 'componentId' }) YIELD componentCount RETURN componentCount",
    # 5.3 释放内存图
    "CALL gds.graph.drop('pep_prot', false) YIELD graphName RETURN graphName",
    # 5.4 按 componentId 聚成 ProteinGroup
    """
    MATCH (prot:Protein)
    WITH prot.componentId AS gid, collect(prot) AS members
    MERGE (g:ProteinGroup {group_id: 'grp_' + toString(gid)})
    WITH g, members UNWIND members AS prot
    MERGE (prot)-[:IN_GROUP]->(g)
    """,
    # 6.1 unique:肽段只连一个蛋白(度=1)
    """
    MATCH (pep:Peptide)-[:BELONGS_TO]->(:Protein)
    WITH pep, count(*) AS deg
    SET pep.is_unique = (deg = 1)
    """,
    # 6.2 razor(简化 parsimony):共享肽段归给 unique 肽段数最多的组
    """
    MATCH (pep:Peptide {is_unique:false})-[b:BELONGS_TO]->(:Protein)-[:IN_GROUP]->(g:ProteinGroup)
    WITH pep, b, g,
         size([ (g)<-[:IN_GROUP]-(:Protein)<-[:BELONGS_TO]-(u:Peptide)
                WHERE u.is_unique | u ]) AS evidence
    ORDER BY evidence DESC
    WITH pep, collect(b)[0] AS razor_rel
    SET razor_rel.is_razor = true
    """,
]

# ───────────────────────── ⑦ 示例分析查询(给报告层用)─────────────────────────
Q_PEPTIDE_SUPPORT: str = """
MATCH (pep:Peptide)<-[:IDENTIFIES]-(psm:PSM)
WHERE psm.is_decoy = false AND (psm.q_value IS NULL OR psm.q_value <= $max_q)
RETURN pep.peptidoform AS peptidoform, count(psm) AS spectral_support
ORDER BY spectral_support DESC
"""

Q_GROUP_SUMMARY: str = """
MATCH (g:ProteinGroup)<-[:IN_GROUP]-(prot:Protein)
OPTIONAL MATCH (prot)<-[:BELONGS_TO]-(u:Peptide {is_unique:true})
RETURN g.group_id AS group_id,
       collect(DISTINCT prot.accession) AS proteins,
       count(DISTINCT u) AS unique_peptides
ORDER BY unique_peptides DESC
"""

# ───────────────────────── ⑧ 序列 embedding + KNN 序列相似 ─────────────────────────
# 取还没 embedding 的肽（按裸序列编码；带修饰的 peptidoform 不喂模型）
Q_UNEMBEDDED: str = """
MATCH (p:Peptide)
WHERE p.embedding IS NULL AND p.stripped_sequence IS NOT NULL
RETURN p.peptidoform AS peptidoform, p.stripped_sequence AS seq
"""

# 把向量写进 Peptide 节点属性
SET_EMBEDDINGS: str = """
UNWIND $rows AS r
MATCH (p:Peptide {peptidoform: r.peptidoform})
SET p.embedding = r.embedding
"""

# gds.knn：按节点 embedding 算 topK 余弦近邻 → 写 SIMILAR_TO 边（需 Neo4j 装 GDS 插件）。
# 用 cypher 投影只取已 embedding 的肽，避免缺属性报错；空关系查询表示 KNN 只看节点属性。
KNN_STEPS: list[str] = [
    "CALL gds.graph.drop('pep_emb', false) YIELD graphName RETURN graphName",
    """
    CALL gds.graph.project.cypher(
        'pep_emb',
        'MATCH (p:Peptide) WHERE p.embedding IS NOT NULL RETURN id(p) AS id, p.embedding AS embedding',
        'MATCH (a:Peptide) WHERE false RETURN id(a) AS source, id(a) AS target'
    ) YIELD graphName RETURN graphName
    """,
    """
    CALL gds.knn.write('pep_emb', {
        nodeProperties: ['embedding'],
        topK: $k,
        similarityCutoff: $cutoff,
        writeRelationshipType: 'SIMILAR_TO',
        writeProperty: 'score'
    }) YIELD relationshipsWritten RETURN relationshipsWritten
    """,
    "CALL gds.graph.drop('pep_emb', false) YIELD graphName RETURN graphName",
]

# 查一条肽的序列近邻（给假说阶段用；无向匹配以兼顾 knn 写出的方向）
Q_SIMILAR_PEPTIDES: str = """
MATCH (p:Peptide {peptidoform: $peptidoform})-[r:SIMILAR_TO]-(q:Peptide)
RETURN q.peptidoform AS peptidoform, q.stripped_sequence AS seq, r.score AS score
ORDER BY r.score DESC
"""

# ───────────────────────── ⑨ 查库 novelty 标注(阶段3)─────────────────────────
# 命中与否都写;"搜了没命中"显式记成 db_hit=false → 区别于"还没搜"(节点上无此属性)。
# MATCH 已存在的 Peptide(主干先建),只盖标注不新建肽。
MERGE_PEP_LOOKUP: str = """
UNWIND $rows AS r
MATCH (p:Peptide {peptidoform: r.peptidoform})
SET p.db_searched = true,
    p.db_hit      = r.db_hit,
    p.is_novel    = NOT r.db_hit,
    p.db_name     = r.db_name,
    p.db_version  = r.db_version
"""

# 取还没查库的肽(db_searched 未标)→ 喂阶段3 assign_proteins(幂等只查没查过的)
Q_UNSEARCHED: str = """
MATCH (p:Peptide)
WHERE p.db_searched IS NULL AND p.stripped_sequence IS NOT NULL
RETURN p.peptidoform AS peptidoform, p.stripped_sequence AS seq
"""

# 取 novel 肽(查库没命中)→ 只能走序列层 KNN + 注释传递(给阶段6 路由用)
Q_NOVEL_PEPTIDES: str = """
MATCH (p:Peptide)
WHERE p.is_novel = true AND p.stripped_sequence IS NOT NULL
RETURN p.peptidoform AS peptidoform, p.stripped_sequence AS seq
"""

# ───────────────────────── ⑩ 蛋白注释富集(阶段3.5)─────────────────────────
# 按 accession 把 UniProt 注释写成 Protein 节点属性 + provenance;MATCH 已存在的蛋白。
MERGE_PROT_ANNOT: str = """
UNWIND $rows AS r
MATCH (pr:Protein {accession: r.accession})
SET pr.go            = r.go,
    pr.ec            = r.ec,
    pr.interpro      = r.interpro,
    pr.annot_source  = coalesce(r.source, 'UniProt'),
    pr.annot_version = r.version
"""

# 取还没富集的蛋白(annot_version 为空)→ 喂 enrich 批步(幂等只补缺的)
Q_UNANNOTATED: str = """
MATCH (pr:Protein)
WHERE pr.annot_version IS NULL
RETURN pr.accession AS accession
"""

# ───────────────────────── ⑪ 混合检索(阶段5：序列+属性召回 → RRF → rerank)─────────────────────────
# 读肽语料：裸序列 + 其所属蛋白的注释并成一个属性集合(给属性重叠召回用)。
# OPTIONAL MATCH 保留没归属/没注释的肽(attrs 退化为空)。
Q_PEPTIDE_CORPUS: str = """
MATCH (p:Peptide)
WHERE p.stripped_sequence IS NOT NULL
OPTIONAL MATCH (p)-[:BELONGS_TO]->(pr:Protein)
WITH p, collect(coalesce(pr.go, []) + coalesce(pr.ec, []) + coalesce(pr.interpro, [])) AS perprot
RETURN p.peptidoform AS peptidoform,
       p.stripped_sequence AS seq,
       reduce(acc = [], xs IN perprot | acc + xs) AS attrs
"""

# 把混合检索算出的 top-k 写成 SIMILAR_TO 边(method='hybrid' 区别于 gds.knn 那路)。
MERGE_SIMILAR: str = """
UNWIND $pairs AS pr
MATCH (a:Peptide {peptidoform: pr.src})
MATCH (b:Peptide {peptidoform: pr.dst})
MERGE (a)-[r:SIMILAR_TO]->(b)
SET r.score = pr.score, r.method = 'hybrid'
"""

# ───────────────────────── ⑫ 假说：取一条肽的相似邻居 + 其母蛋白注释(阶段6)─────────────────────────
# 无向匹配兼顾 knn/hybrid 写出的方向；先按邻居去重取最高相似度。
# 共享肽：每个母蛋白返回**独立一个 map**(不 union 压平)，保住"哪个 GO 来自哪个 accession"的出处。
Q_NEIGHBOR_ANNOTS: str = """
MATCH (p:Peptide {peptidoform: $peptidoform})-[r:SIMILAR_TO]-(q:Peptide)
WITH q, max(r.score) AS score
OPTIONAL MATCH (q)-[:BELONGS_TO]->(pr:Protein)
WITH q, score, collect(
    CASE WHEN pr IS NULL THEN null ELSE {
        accession: pr.accession,
        go:        coalesce(pr.go, []),
        ec:        coalesce(pr.ec, []),
        interpro:  coalesce(pr.interpro, [])
    } END
) AS prots
RETURN q.peptidoform AS id,
       score,
       [x IN prots WHERE x IS NOT NULL] AS proteins
"""

