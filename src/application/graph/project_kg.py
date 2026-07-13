"""把 MySQL 事实投影成两层知识图谱（L3）。

读 :class:`ExperimentRepository` 里已落库的事实（蛋白/基因、CTD 疾病结论、蛋白级假说、
L2 差异），按 Q3 双节点（``Protein``/``Gene`` 以 ``ENCODED_BY`` 缝合）+ Q4 两层
（通用 KG / 本次实验 KG）投影成节点与边，经 :class:`GraphStore` 端口幂等写入。
MySQL 仍是事实唯一来源（Q5）；节点/边只带 canonical key + 轻量属性 + ``mysql_ref``。

结构近邻（``STRUCTURAL_NEIGHBOR``）从仓库中的轻量 evidence 读取；KG 投影只 materialize
通过 projection policy 的高信号关系，完整 provider payload 仍留在 MySQL。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any

from pkg.experiment import (
    AnnotationTargetType,
    ExperimentRepository,
    FusedCandidate,
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
from pkg.graph.identity import (
    canonical_gene_identity,
    canonical_protein_key,
    canonical_relation_key,
    normalize_gene_symbol,
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
_GRAPH_SCHEMA_VERSION = "2"


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
    generic_neighbor_evidence = repo.list_neighbor_evidence(experiment_id)
    fused_candidates = repo.list_fused_candidates(experiment_id)
    policy = projection_policy or DEFAULT_PROJECTION_POLICY

    accession_by_protein_id = {
        p.protein_id: canonical_protein_key(p.accession) for p in proteins
    }
    gene_refs_by_symbol: dict[str, set[NodeRef]] = {}

    nodes: dict[tuple[NodeLabel, str], GraphNode] = {}
    edges: dict[tuple[EdgeType, str], GraphEdge] = {}

    def _add_node(node: GraphNode) -> None:
        nodes[(node.label, node.key)] = node

    def _add_edge(edge: GraphEdge) -> None:
        edges[(edge.type, edge.key)] = edge

    def _general_protein(accession: str) -> NodeRef:
        key = canonical_protein_key(accession)
        ref = NodeRef(NodeLabel.PROTEIN, key)
        if (ref.label, ref.key) not in nodes:
            _add_node(
                GraphNode(
                    label=NodeLabel.PROTEIN,
                    key=key,
                    scope=GraphScope.GENERAL,
                    properties={"accession": key},
                    mysql_ref={"accession": key},
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
            key=protein_ref.key,
            scope=GraphScope.GENERAL,
            properties={
                "accession": protein_ref.key,
                "raw_accession": protein.accession,
                "organism": protein.organism,
                "taxon_id": protein.taxon_id,
            },
            mysql_ref={"accession": protein_ref.key},
        )
        gene_identity = canonical_gene_identity(
            protein.gene,
            taxon_id=protein.taxon_id,
            meta=protein.meta,
        )
        gene_ref = NodeRef(NodeLabel.GENE, gene_identity.key)
        gene_refs_by_symbol.setdefault(gene_identity.symbol, set()).add(gene_ref)
        _add_node(
            GraphNode(
                label=NodeLabel.GENE,
                key=gene_identity.key,
                scope=GraphScope.GENERAL,
                properties=gene_identity.properties,
                mysql_ref={
                    "gene": gene_identity.symbol,
                    "taxon_id": gene_identity.taxon_id,
                    "ncbi_gene_id": gene_identity.ncbi_gene_id,
                },
            )
        )
        _add_edge(
            GraphEdge(
                type=EdgeType.ENCODED_BY,
                start=protein_ref,
                end=gene_ref,
                key=f"{protein_ref.key}|ENCODED_BY|{gene_ref.key}",
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
            symbol = normalize_gene_symbol(ann.target)
            gene_refs = sorted(
                gene_refs_by_symbol.get(symbol, set()), key=lambda ref: ref.key
            )
            if not gene_refs:
                identity = canonical_gene_identity(
                    symbol,
                    taxon_id=context.taxon_id,
                )
                gene_ref = NodeRef(NodeLabel.GENE, identity.key)
                gene_refs = [gene_ref]
                _add_node(
                    GraphNode(
                        label=NodeLabel.GENE,
                        key=identity.key,
                        scope=GraphScope.GENERAL,
                        properties=identity.properties,
                        mysql_ref={
                            "gene": identity.symbol,
                            "taxon_id": identity.taxon_id,
                            "ncbi_gene_id": identity.ncbi_gene_id,
                        },
                    )
                )
            for gene_ref in gene_refs:
                _add_edge(
                    GraphEdge(
                        type=EdgeType.ASSOCIATED_WITH,
                        start=gene_ref,
                        end=disease_ref,
                        key=canonical_relation_key(
                            EdgeType.ASSOCIATED_WITH.value,
                            gene_ref.key,
                            disease_ref.key,
                            ann.source,
                            ann.provenance.get("db_version")
                            or ann.provenance.get("source_version")
                            or "",
                            ann.derivation.get("relation_id") or "",
                        ),
                        scope=GraphScope.GENERAL,
                        properties={
                            "evidence_level": ann.evidence_level.value,
                            "source": ann.source,
                            "source_version": ann.provenance.get("db_version")
                            or ann.provenance.get("source_version")
                            or "",
                            "source_relation_id": ann.derivation.get("relation_id") or "",
                        },
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

    # 4) 显式比较：Protein -> Comparison -> case/control Group（实验工作区）
    comparison_refs: dict[tuple[str, str], NodeRef] = {}
    for case_group_id, control_group_id in sorted(
        {(row.case_group_id, row.control_group_id) for row in differentials}
    ):
        comparison_key = (
            f"{experiment_id}:comparison:{case_group_id}:vs:{control_group_id}"
        )
        comparison_ref = NodeRef(NodeLabel.COMPARISON, comparison_key)
        comparison_refs[(case_group_id, control_group_id)] = comparison_ref
        _add_node(
            GraphNode(
                label=NodeLabel.COMPARISON,
                key=comparison_key,
                scope=GraphScope.EXPERIMENT,
                experiment_id=experiment_id,
                properties={
                    "case_group_id": case_group_id,
                    "control_group_id": control_group_id,
                },
                mysql_ref={
                    "experiment_id": experiment_id,
                    "case_group_id": case_group_id,
                    "control_group_id": control_group_id,
                },
            )
        )
        for edge_type, group_id in (
            (EdgeType.CASE_GROUP, case_group_id),
            (EdgeType.CONTROL_GROUP, control_group_id),
        ):
            _add_edge(
                GraphEdge(
                    type=edge_type,
                    start=comparison_ref,
                    end=NodeRef(NodeLabel.GROUP, f"{experiment_id}:{group_id}"),
                    key=f"{comparison_key}|{edge_type.value}|{group_id}",
                    scope=GraphScope.EXPERIMENT,
                    experiment_id=experiment_id,
                )
            )

    for diff in differentials:
        accession = accession_by_protein_id.get(diff.protein_id)
        if not accession:
            continue
        protein_ref = _general_protein(accession)
        comparison_ref = comparison_refs[
            (diff.case_group_id, diff.control_group_id)
        ]
        _add_edge(
            GraphEdge(
                type=EdgeType.DIFFERENTIAL_IN,
                start=protein_ref,
                end=comparison_ref,
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
        provider = str(properties.get("provider") or properties.get("source") or "")
        source_version = str(
            properties.get("db_version") or properties.get("provider_version") or ""
        )
        key = canonical_relation_key(
            EdgeType.STRUCTURAL_NEIGHBOR.value,
            query_ref.key,
            target_ref.key,
            provider,
            source_version,
            relation_id,
        )
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

    # 6) 多 channel 融合候选：候选完整 evidence 留 MySQL，只把高信号 protein neighbor
    # 投成实验工作区边。非 protein target 暂不投图，等 Domain/Publication 节点建模后再接。
    for candidate in fused_candidates:
        _validate_fused_candidate_evidence(
            candidate,
            structure_evidence=structure_evidence,
            generic_evidence=generic_neighbor_evidence,
        )
        _add_fused_candidate_edge(
            candidate=candidate,
            query_accession=accession_by_protein_id.get(
                candidate.query_protein_id, candidate.query_accession
            ),
            policy=policy,
            general_protein=_general_protein,
            add_edge=_add_edge,
            skip_projection=_skip_projection,
            experiment_id=experiment_id,
        )

    node_list = list(nodes.values())
    edge_list = list(edges.values())
    replacement = graph.replace_experiment_projection(
        experiment_id, node_list, edge_list
    )
    graph_manifest = _graph_manifest(node_list, edge_list)

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
        "fused_candidates": len(fused_candidates),
        "candidate_neighbors": sum(
            1 for e in edge_list if e.type is EdgeType.CANDIDATE_NEIGHBOR
        ),
        "projection_skipped": dict(sorted(skipped_projection.items())),
        "projection_replaced": replacement,
        "manifest": graph_manifest,
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
        "source_relation_id": evidence.relation_id,
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


def _validate_fused_candidate_evidence(
    candidate: FusedCandidate,
    *,
    structure_evidence: Sequence[StructureNeighborEvidence],
    generic_evidence: Sequence[Any],
) -> None:
    structure_by_id = {row.evidence_id: row for row in structure_evidence}
    generic_by_source_id: dict[str, Any] = {}
    for row in generic_evidence:
        generic_by_source_id[row.evidence_id] = row
        source_evidence_id = str(row.meta.get("source_evidence_id") or "")
        if source_evidence_id:
            generic_by_source_id[source_evidence_id] = row

    if not candidate.evidence_ids:
        raise ValueError(f"fused candidate {candidate.candidate_id} has no evidence IDs")

    actual_channels: set[str] = set()
    expected_query = canonical_protein_key(candidate.query_accession)
    expected_target = canonical_protein_key(candidate.target_id)
    for evidence_id in candidate.evidence_ids:
        structure_row = structure_by_id.get(evidence_id)
        if structure_row is not None:
            actual_channels.add("structure")
            query = canonical_protein_key(structure_row.query_accession)
            target = canonical_protein_key(structure_row.target_accession)
        else:
            generic_row = generic_by_source_id.get(evidence_id)
            if generic_row is None:
                raise ValueError(
                    f"fused candidate {candidate.candidate_id} references missing "
                    f"evidence {evidence_id}"
                )
            actual_channels.add(generic_row.channel)
            query = canonical_protein_key(generic_row.query_accession)
            target = canonical_protein_key(generic_row.target_id)
        if query != expected_query or target != expected_target:
            raise ValueError(
                f"fused candidate {candidate.candidate_id} evidence {evidence_id} "
                "does not match its query/target"
            )

    if actual_channels != set(candidate.support_channels):
        raise ValueError(
            f"fused candidate {candidate.candidate_id} channels do not match evidence: "
            f"declared={sorted(set(candidate.support_channels))}, "
            f"actual={sorted(actual_channels)}"
        )


def _add_fused_candidate_edge(
    *,
    candidate: FusedCandidate,
    query_accession: str,
    policy: ProjectionPolicy,
    general_protein: Callable[[str], NodeRef],
    add_edge: Callable[[GraphEdge], None],
    skip_projection: Callable[[str], None],
    experiment_id: str,
) -> None:
    if candidate.target_type.lower() != "protein":
        skip_projection("target_type_not_projected")
        return

    decision = policy.decide(
        ProjectionCandidate(
            channel="fusion",
            relation_type=candidate.relation_type,
            fusion_rank=candidate.fusion_rank,
            fused_score=candidate.fused_score,
            support_channels=tuple(candidate.support_channels),
        )
    )
    if not decision.projected:
        skip_projection(decision.reason)
        return

    query_ref = general_protein(query_accession)
    target_ref = general_protein(candidate.target_id)
    add_edge(
        GraphEdge(
            type=EdgeType.CANDIDATE_NEIGHBOR,
            start=query_ref,
            end=target_ref,
            key=candidate.candidate_id,
            scope=GraphScope.EXPERIMENT,
            experiment_id=experiment_id,
            properties={
                "candidate_id": candidate.candidate_id,
                "relation_type": candidate.relation_type,
                "fused_score": candidate.fused_score,
                "fusion_rank": candidate.fusion_rank,
                "support_channels": list(candidate.support_channels),
                "support_channel_count": len(set(candidate.support_channels)),
                "evidence_ids": list(candidate.evidence_ids),
                "evidence_count": len(candidate.evidence_ids),
                "projection_reason": decision.reason,
                "source": "fused_candidate",
            },
        )
    )


def _graph_manifest(
    nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]
) -> dict[str, Any]:
    node_rows = [
        {
            "label": node.label.value,
            "key": node.key,
            "scope": node.scope.value,
            "experiment_id": node.experiment_id,
            "properties": node.properties,
            "mysql_ref": node.mysql_ref,
        }
        for node in sorted(nodes, key=lambda row: (row.label.value, row.key))
    ]
    edge_rows = [
        {
            "type": edge.type.value,
            "key": edge.key,
            "scope": edge.scope.value,
            "experiment_id": edge.experiment_id,
            "start": {"label": edge.start.label.value, "key": edge.start.key},
            "end": {"label": edge.end.label.value, "key": edge.end.key},
            "properties": edge.properties,
        }
        for edge in sorted(edges, key=lambda row: (row.type.value, row.key))
    ]
    payload = {
        "schema_version": _GRAPH_SCHEMA_VERSION,
        "node_records": node_rows,
        "edge_records": edge_rows,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        **payload,
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


__all__ = ["project_experiment_kg"]
