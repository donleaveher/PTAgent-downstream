from __future__ import annotations

from application.graph.project_kg import project_experiment_kg
from application.knowledge import (
    generate_fused_neighbor_candidates,
    run_neighbor_search,
)
from pkg.experiment import (
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    InMemoryExperimentRepository,
    ProteinRecord,
    StructureNeighborEvidence,
    StructureSearchRun,
)
from pkg.graph import EdgeType, GraphScope, InMemoryGraphStore, NodeLabel, NodeRef
from pkg.retrieval import (
    DomainNeighborProvider,
    NeighborProvider,
    ProviderPersistenceAdapter,
    SequenceNeighborProvider,
)
from pkg.retrieval.providers import (
    StructureEvidencePersistenceAdapter,
    StructureEvidenceNeighborProvider,
    StructureSearchNeighborProvider,
)

EXP = "exp_neighbor_fusion"


class _FailingProvider:
    channel = "structure"
    name = "BrokenStructure"
    version = "broken"

    def search(self, accessions: list[str], *, top_k: int | None = None):
        raise RuntimeError("structure backend unavailable")


class _CountingPersistenceAdapter:
    adapter_id = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def persist(self, repository, result, context):
        self.calls += 1
        return {"custom_persisted_candidates": len(result.candidates)}


def _seed_repo() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(
                    protein_id="prot_q",
                    accession="Q_NOVEL",
                    gene="Novelx",
                    taxon_id=10116,
                )
            ],
            peptides=[],
        )
    )
    repo.save_structure_search_run(
        StructureSearchRun(
            run_id="strun_fusion",
            experiment_id=EXP,
            provider="Foldseek-AlphaFold",
            provider_version="afdb-test",
            db_version="afdb-test",
            params_hash="b" * 64,
            params={"top_k": 20},
            status="completed",
        )
    )
    repo.add_structure_neighbor_evidence(
        [
            StructureNeighborEvidence(
                evidence_id="sne_shared",
                run_id="strun_fusion",
                experiment_id=EXP,
                query_protein_id="prot_q",
                query_accession="Q_NOVEL",
                target_accession="P_SHARED",
                rank=1,
                score=0.95,
                coverage=0.9,
                taxon_id=9606,
                relation_id="Q_NOVEL->P_SHARED",
            )
        ]
    )
    return repo


def test_structure_adapters_implement_neighbor_provider_protocol() -> None:
    repo = _seed_repo()

    assert isinstance(StructureEvidenceNeighborProvider(repo, EXP), NeighborProvider)
    assert isinstance(StructureSearchNeighborProvider(repo, EXP), NeighborProvider)


def test_structure_persistence_adapter_implements_persistence_protocol() -> None:
    assert isinstance(StructureEvidencePersistenceAdapter(), ProviderPersistenceAdapter)


def test_structure_and_sequence_consensus_persists_fused_candidate_and_projects_kg() -> None:
    repo = _seed_repo()
    sequence = SequenceNeighborProvider(
        {
            "Q_NOVEL": "MPEPTIDEKAAAA",
            "P_SHARED": "MPEPTIDERAAAA",
            "P_SEQ_ONLY": "MPEPTIDENAAAA",
        },
        version="seq-test",
        top_k=2,
    )

    summary = generate_fused_neighbor_candidates(
        EXP, repository=repo, sequence_provider=sequence, top_k=5
    )

    assert summary["channels"] == {"sequence": 2, "structure": 1}
    candidates = repo.list_fused_candidates(EXP)
    by_target = {row.target_id: row for row in candidates}
    assert set(by_target) == {"P_SHARED", "P_SEQ_ONLY"}
    assert by_target["P_SHARED"].support_channels == ["sequence", "structure"]
    assert by_target["P_SHARED"].fusion_rank == 1
    assert "sne_shared" in by_target["P_SHARED"].evidence_ids
    assert by_target["P_SEQ_ONLY"].support_channels == ["sequence"]

    store = InMemoryGraphStore()
    kg = project_experiment_kg(EXP, repository=repo, store=store)

    assert kg["fused_candidates"] == 2
    assert kg["candidate_neighbors"] == 1
    assert kg["projection_skipped"] == {"support_channels<2": 1}
    edges = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "Q_NOVEL"),
        EdgeType.CANDIDATE_NEIGHBOR,
        experiment_id=EXP,
    )
    assert len(edges) == 1
    assert edges[0].scope is GraphScope.EXPERIMENT
    assert edges[0].end.key == "P_SHARED"
    assert edges[0].properties["support_channels"] == ["sequence", "structure"]


def test_structure_and_domain_consensus_persists_fused_candidate_and_projects_kg() -> None:
    repo = _seed_repo()
    domain = DomainNeighborProvider(
        {
            "Q_NOVEL": ["IPR_FERM", "IPR_KINASE", "IPR_SH2"],
            "P_SHARED": ["IPR_FERM", "IPR_KINASE", "IPR_SH2"],
            "P_DOMAIN_ONLY": ["IPR_KINASE"],
        },
        version="domain-test",
        top_k=2,
    )

    summary = generate_fused_neighbor_candidates(
        EXP,
        repository=repo,
        providers=[StructureEvidenceNeighborProvider(repo, EXP), domain],
        top_k=5,
    )

    assert summary["channels"] == {"domain": 2, "structure": 1}
    by_target = {row.target_id: row for row in repo.list_fused_candidates(EXP)}
    assert set(by_target) == {"P_SHARED", "P_DOMAIN_ONLY"}
    assert by_target["P_SHARED"].support_channels == ["domain", "structure"]
    assert by_target["P_SHARED"].fusion_rank == 1

    store = InMemoryGraphStore()
    kg = project_experiment_kg(EXP, repository=repo, store=store)

    assert kg["candidate_neighbors"] == 1
    assert kg["projection_skipped"] == {"support_channels<2": 1}
    edges = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "Q_NOVEL"),
        EdgeType.CANDIDATE_NEIGHBOR,
        experiment_id=EXP,
    )
    assert len(edges) == 1
    assert edges[0].end.key == "P_SHARED"
    assert edges[0].properties["support_channels"] == ["domain", "structure"]


def test_sequence_only_fusion_stays_persisted_but_not_projected() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot_q", accession="Q_NOVEL", gene="Novelx")
            ],
            peptides=[],
        )
    )
    sequence = SequenceNeighborProvider(
        {"Q_NOVEL": "MPEPTIDEKAAAA", "P_SEQ": "MPEPTIDERAAAA"},
        version="seq-test",
    )

    generate_fused_neighbor_candidates(EXP, repository=repo, sequence_provider=sequence)
    assert len(repo.list_fused_candidates(EXP)) == 1

    store = InMemoryGraphStore()
    kg = project_experiment_kg(EXP, repository=repo, store=store)
    assert kg["candidate_neighbors"] == 0
    assert kg["projection_skipped"] == {"support_channels<2": 1}


def test_provider_failure_does_not_block_other_neighbor_channels() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot_q", accession="Q_NOVEL", gene="Novelx")
            ],
            peptides=[],
        )
    )
    sequence = SequenceNeighborProvider(
        {"Q_NOVEL": "MPEPTIDEKAAAA", "P_SEQ": "MPEPTIDERAAAA"},
        version="seq-test",
    )

    summary = run_neighbor_search(
        EXP,
        repository=repo,
        providers=[_FailingProvider(), sequence],
    )

    assert summary["provider_errors"] == {
        "BrokenStructure": "RuntimeError: structure backend unavailable"
    }
    assert summary["channels"] == {"sequence": 1}
    assert len(repo.list_fused_candidates(EXP)) == 1


def test_neighbor_search_uses_injected_persistence_adapters() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot_q", accession="Q_NOVEL", gene="Novelx")
            ],
            peptides=[],
        )
    )
    sequence = SequenceNeighborProvider(
        {"Q_NOVEL": "MPEPTIDEKAAAA", "P_SEQ": "MPEPTIDERAAAA"},
        version="seq-test",
    )
    adapter = _CountingPersistenceAdapter()

    summary = run_neighbor_search(
        EXP,
        repository=repo,
        providers=[sequence],
        persistence_adapters=[adapter],
    )

    assert adapter.calls == 1
    assert summary["persisted"] == {"custom_persisted_candidates": 1}
    assert len(repo.list_fused_candidates(EXP)) == 1


def test_neighbor_search_persists_generic_neighbor_evidence_by_default() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot_q", accession="Q_NOVEL", gene="Novelx")
            ],
            peptides=[],
        )
    )
    sequence = SequenceNeighborProvider(
        {"Q_NOVEL": "MPEPTIDEKAAAA", "P_SEQ": "MPEPTIDERAAAA"},
        version="seq-test",
    )

    summary = run_neighbor_search(EXP, repository=repo, providers=[sequence])

    assert summary["persisted"] == {
        "neighbor_evidence": 1,
        "neighbor_search_runs": 1,
    }
    runs = repo.list_neighbor_search_runs(EXP)
    assert len(runs) == 1
    assert runs[0].provider_id == "sequence.kmer"
    assert runs[0].channel == "sequence"
    evidence = repo.list_neighbor_evidence(EXP)
    assert len(evidence) == 1
    assert evidence[0].run_id == runs[0].run_id
    assert evidence[0].query_protein_id == "prot_q"
    assert evidence[0].target_id == "P_SEQ"
    assert evidence[0].relation_type == "SEQUENCE_NEIGHBOR"


def test_generic_neighbor_persistence_is_isolated_across_experiments() -> None:
    repo = InMemoryExperimentRepository()
    for experiment_id in ("exp_neighbor_a", "exp_neighbor_b"):
        repo.save_bundle(
            ExperimentBundle(
                context=ExperimentContext(experiment_id=experiment_id, raw_text="fusion"),
                groups=[
                    ExperimentGroup(
                        group_id="case",
                        label="Case",
                        role=GroupRole.CASE,
                    )
                ],
                proteins=[
                    ProteinRecord(
                        protein_id="prot_q",
                        accession="Q_NOVEL",
                        gene="Novelx",
                    )
                ],
                peptides=[],
            )
        )
    sequence = SequenceNeighborProvider(
        {"Q_NOVEL": "MPEPTIDEKAAAA", "P_SEQ": "MPEPTIDERAAAA"},
        version="seq-test",
    )

    run_neighbor_search("exp_neighbor_a", repository=repo, providers=[sequence])
    run_neighbor_search("exp_neighbor_b", repository=repo, providers=[sequence])

    first_run = repo.list_neighbor_search_runs("exp_neighbor_a")
    second_run = repo.list_neighbor_search_runs("exp_neighbor_b")
    first_evidence = repo.list_neighbor_evidence("exp_neighbor_a")
    second_evidence = repo.list_neighbor_evidence("exp_neighbor_b")

    assert len(first_run) == len(second_run) == 1
    assert first_run[0].run_id != second_run[0].run_id
    assert len(first_evidence) == len(second_evidence) == 1
    assert first_evidence[0].evidence_id != second_evidence[0].evidence_id
    assert first_evidence[0].evidence_id.startswith("ne_")
    assert second_evidence[0].evidence_id.startswith("ne_")
    assert first_evidence[0].meta["source_evidence_id"] == second_evidence[0].meta[
        "source_evidence_id"
    ]
    assert first_evidence[0].run_id == first_run[0].run_id
    assert second_evidence[0].run_id == second_run[0].run_id


def test_neighbor_provider_can_be_built_by_registered_name() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="fusion"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot_q", accession="Q_NOVEL", gene="Novelx")
            ],
            peptides=[],
        )
    )

    summary = run_neighbor_search(
        EXP,
        repository=repo,
        provider_names=["sequence.kmer"],
        provider_options={
            "sequence.kmer": {
                "sequences": {
                    "Q_NOVEL": "MPEPTIDEKAAAA",
                    "P_SEQ": "MPEPTIDERAAAA",
                },
                "version": "seq-by-name",
            }
        },
    )

    assert summary["providers"] == ["sequence.kmer"]
    assert summary["channels"] == {"sequence": 1}
    candidates = repo.list_fused_candidates(EXP)
    assert len(candidates) == 1
    assert candidates[0].meta["channel_evidence"][0]["provider_version"] == "seq-by-name"
