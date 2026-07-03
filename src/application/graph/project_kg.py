"""把 MySQL 事实投影成两层知识图谱（L3）。

读 :class:`ExperimentRepository` 里已落库的事实（蛋白/基因、CTD 疾病结论、蛋白级假说、
L2 差异），按 Q3 双节点（``Protein``/``Gene`` 以 ``ENCODED_BY`` 缝合）+ Q4 两层
（通用 KG / 本次实验 KG）投影成节点与边，经 :class:`GraphStore` 端口幂等写入。
MySQL 仍是事实唯一来源（Q5）；节点/边只带 canonical key + 轻量属性 + ``mysql_ref``。

结构近邻（``STRUCTURAL_NEIGHBOR``）从仓库中的轻量 evidence 读取；KG 投影只 materialize
通过 projection policy 的高信号关系，完整 provider payload 仍留在 MySQL。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pkg.experiment import (
    AnnotationTargetType,
    ExperimentRepository,
    StructureNeighborEvidence,
    StructureSearchRun,
    get_experiment_store,
)
from pkg.graph.model import (
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphScope,
    NodeLabel,
    NodeRef,
)
from pkg.graph.neo4j_store import get_kg_store
from pkg.graph.port import GraphStore
from pkg.structure import StructuralNeighbor

from .projection_policy import (
    DEFAULT_PROJECTION_POLICY,
    ProjectionCandidate,
    ProjectionPolicy,
)

_AddStructureEdge = Callable[..., None]


def project_experiment_kg(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    store: GraphStore | None = None,
    structural_neighbors: Sequence[StructuralNeighbor] = (),
    projection_policy: ProjectionPolicy | None = None,
) -> dict[str, Any]:
    """把某实验的 MySQL 事实投影成通用 KG + 实验工作区，幂等可重投。

    返回投影摘要（各类节点/边计数）。重复调用因 key 稳定而幂等（MERGE 不增量）。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    graph = store or get_kg_store()
    graph.initialize_schema()

    proteins = repo.list_proteins(experiment_id)
    groups = repo.list_groups(experiment_id)
    annotations = repo.list_annotations(experiment_id)
    differentials = repo.list_differentials(experiment_id)
    structure_runs = {
        run.run_id: run for run in repo.list_structure_search_runs(experiment_id)
    }
    structure_evidence = repo.list_structure_neighbor_evidence(experiment_id)
    policy = projection_policy or DEFAULT_PROJECTION_POLICY

    accession_by_protein_id = {p.protein_id: p.accession for p in proteins}

    nodes: dict[tuple[NodeLabel, str], GraphNode] = {}
    edges: dict[tuple[EdgeType, str], GraphEdge] = {}

    def _add_node(node: GraphNode) -> None:
        nodes[(node.label, node.key)] = node

    def _add_edge(edge: GraphEdge) -> None:
        edges[(edge.type, edge.key)] = edge

    def _general_protein(accession: str) -> NodeRef:
        ref = NodeRef(NodeLabel.PROTEIN, accession)
        if (ref.label, ref.key) not in nodes:
            _add_node(
                GraphNode(
                    label=NodeLabel.PROTEIN,
                    key=accession,
                    scope=GraphScope.GENERAL,
                    mysql_ref={"accession": accession},
                )
            )
        return ref

    def _general_disease(disease_id: str, disease_name: str) -> NodeRef:
        _add_node(
            GraphNode(
                label=NodeLabel.DISEASE,
                key=disease_id,
                scope=GraphScope.GENERAL,
                properties={"name": disease_name},
                mysql_ref={"disease_id": disease_id},
            )
        )
        return NodeRef(NodeLabel.DISEASE, disease_id)

    # 1) 蛋白/基因 + ENCODED_BY（通用 KG 字典；Q3 双节点缝合）
    for protein in proteins:
        protein_ref = _general_protein(protein.accession)
        nodes[(protein_ref.label, protein_ref.key)] = GraphNode(
            label=NodeLabel.PROTEIN,
            key=protein.accession,
            scope=GraphScope.GENERAL,
            properties={"organism": protein.organism, "taxon_id": protein.taxon_id},
            mysql_ref={"accession": protein.accession},
        )
        gene_ref = NodeRef(NodeLabel.GENE, protein.gene)
        _add_node(
            GraphNode(
                label=NodeLabel.GENE,
                key=protein.gene,
                scope=GraphScope.GENERAL,
                mysql_ref={"gene": protein.gene},
            )
        )
        _add_edge(
            GraphEdge(
                type=EdgeType.ENCODED_BY,
                start=protein_ref,
                end=gene_ref,
                key=f"{protein.accession}|ENCODED_BY|{protein.gene}",
                scope=GraphScope.GENERAL,
            )
        )

    # 2) 疾病关联（CTD 基因结论 → 通用 KG；蛋白级假说 → 实验工作区），边带 evidence_level
    for ann in annotations:
        if not ann.attribute.startswith("disease:") or not isinstance(ann.value, dict):
            continue
        disease_id = ann.value.get("disease_id")
        if not disease_id:
            continue
        disease_ref = _general_disease(disease_id, ann.value.get("disease_name", ""))
        if ann.target_type is AnnotationTargetType.GENE:
            _add_node(
                GraphNode(
                    label=NodeLabel.GENE,
                    key=ann.target,
                    scope=GraphScope.GENERAL,
                    mysql_ref={"gene": ann.target},
                )
            )
            _add_edge(
                GraphEdge(
                    type=EdgeType.ASSOCIATED_WITH,
                    start=NodeRef(NodeLabel.GENE, ann.target),
                    end=disease_ref,
                    key=ann.annotation_id,
                    scope=GraphScope.GENERAL,
                    properties={"evidence_level": ann.evidence_level.value},
                )
            )
        elif ann.target_type is AnnotationTargetType.PROTEIN:
            accession = accession_by_protein_id.get(ann.target)
            if not accession:
                continue
            protein_ref = _general_protein(accession)
            _add_edge(
                GraphEdge(
                    type=EdgeType.ASSOCIATED_WITH,
                    start=protein_ref,
                    end=disease_ref,
                    key=ann.annotation_id,
                    scope=GraphScope.EXPERIMENT,
                    experiment_id=experiment_id,
                    properties={"evidence_level": ann.evidence_level.value},
                )
            )

    # 3) 分组节点（实验工作区）
    for group in groups:
        group_key = f"{experiment_id}:{group.group_id}"
        _add_node(
            GraphNode(
                label=NodeLabel.GROUP,
                key=group_key,
                scope=GraphScope.EXPERIMENT,
                experiment_id=experiment_id,
                properties={"label": group.label, "role": group.role.value},
                mysql_ref={"experiment_id": experiment_id, "group_id": group.group_id},
            )
        )

    # 4) 差异：Protein -(DIFFERENTIAL)-> case Group（实验工作区），边带 log2fc
    for diff in differentials:
        accession = accession_by_protein_id.get(diff.protein_id)
        if not accession:
            continue
        protein_ref = _general_protein(accession)
        group_key = f"{experiment_id}:{diff.case_group_id}"
        _add_edge(
            GraphEdge(
                type=EdgeType.DIFFERENTIAL,
                start=protein_ref,
                end=NodeRef(NodeLabel.GROUP, group_key),
                key=diff.differential_id,
                scope=GraphScope.EXPERIMENT,
                experiment_id=experiment_id,
                properties={
                    "log2fc": diff.log2fc,
                    "direction": diff.direction.value,
                    "is_differential": diff.is_differential,
                    "q_value": diff.q_value,
                    "control_group_id": diff.control_group_id,
                },
            )
        )

    # 5) 结构近邻：完整 evidence 留 MySQL；只有 policy 认为显著的关系进入 KG。
    skipped_projection: dict[str, int] = {}

    def _skip_projection(reason: str) -> None:
        skipped_projection[reason] = skipped_projection.get(reason, 0) + 1

    def _add_structure_edge(
        *,
        query_accession: str,
        target_accession: str,
        rank: int,
        score: float,
        coverage: float,
        taxon_id: int | None,
        relation_id: str,
        properties: dict[str, Any],
    ) -> None:
        decision = policy.decide(
            ProjectionCandidate(
                channel="structure",
                relation_type=EdgeType.STRUCTURAL_NEIGHBOR.value,
                rank=rank,
                score=score,
                coverage=coverage,
                support_channels=("structure",),
            )
        )
        if not decision.projected:
            _skip_projection(decision.reason)
            return
        query_ref = _general_protein(query_accession)
        target_ref = _general_protein(target_accession)
        key = relation_id or f"{query_accession}|STRUCTURAL_NEIGHBOR|{target_accession}"
        _add_edge(
            GraphEdge(
                type=EdgeType.STRUCTURAL_NEIGHBOR,
                start=query_ref,
                end=target_ref,
                key=key,
                scope=GraphScope.GENERAL,
                properties={
                    "score": score,
                    "coverage": coverage,
                    "rank": rank,
                    "taxon_id": taxon_id,
                    "channel": "structure",
                    "projection_reason": decision.reason,
                    **properties,
                },
            )
        )

    for evidence in structure_evidence:
        run = structure_runs.get(evidence.run_id)
        _add_structure_evidence_edge(
            evidence=evidence,
            run=run,
            query_accession=accession_by_protein_id.get(
                evidence.query_protein_id, evidence.query_accession
            ),
            add_structure_edge=_add_structure_edge,
        )

    # Legacy/test injection path. It is intentionally still policy-gated so
    # callers cannot bypass graph visibility thresholds.
    for neighbor in structural_neighbors:
        _add_structure_edge(
            query_accession=neighbor.query_accession,
            target_accession=neighbor.target_accession,
            rank=neighbor.rank,
            score=neighbor.score,
            coverage=neighbor.coverage,
            taxon_id=neighbor.taxon_id,
            relation_id=neighbor.relation_id,
            properties={
                "source": "injected",
                "taxon_name": neighbor.taxon_name,
            },
        )

    node_list = list(nodes.values())
    edge_list = list(edges.values())
    graph.upsert_nodes(node_list)
    graph.upsert_edges(edge_list)

    return {
        "experiment_id": experiment_id,
        "proteins": len(proteins),
        "nodes": len(node_list),
        "edges": len(edge_list),
        "nodes_by_label": {
            label.value: sum(1 for n in node_list if n.label is label)
            for label in NodeLabel
        },
        "edges_by_type": {
            etype.value: sum(1 for e in edge_list if e.type is etype)
            for etype in EdgeType
        },
        "general_nodes": sum(1 for n in node_list if n.scope is GraphScope.GENERAL),
        "experiment_nodes": sum(
            1 for n in node_list if n.scope is GraphScope.EXPERIMENT
        ),
        "structural_neighbors": sum(
            1 for e in edge_list if e.type is EdgeType.STRUCTURAL_NEIGHBOR
        ),
        "structure_neighbor_evidence": len(structure_evidence),
        "structural_neighbors_injected": len(structural_neighbors),
        "projection_skipped": dict(sorted(skipped_projection.items())),
    }


def _add_structure_evidence_edge(
    *,
    evidence: StructureNeighborEvidence,
    run: StructureSearchRun | None,
    query_accession: str,
    add_structure_edge: _AddStructureEdge,
) -> None:
    properties = {
        "source": "structure_neighbor_evidence",
        "evidence_id": evidence.evidence_id,
        "run_id": evidence.run_id,
        "taxon_name": evidence.taxon_name,
    }
    if run is not None:
        properties.update(
            {
                "provider": run.provider,
                "provider_version": run.provider_version,
                "db_version": run.db_version,
            }
        )
    add_structure_edge(
        query_accession=query_accession,
        target_accession=evidence.target_accession,
        rank=evidence.rank,
        score=evidence.score,
        coverage=evidence.coverage,
        taxon_id=evidence.taxon_id,
        relation_id=evidence.relation_id,
        properties=properties,
    )


__all__ = ["project_experiment_kg"]
