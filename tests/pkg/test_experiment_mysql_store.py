"""MySQL store 的 DB-API 契约测试；不连接真实 MySQL。"""

from __future__ import annotations

import re
from datetime import timezone
from typing import Any

import pytest

from pkg.experiment import (
    AnnotationTargetType,
    ContextConfirmationStatus,
    DifferentialDirection,
    DifferentialResult,
    EnrichmentRecord,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContextRevision,
    ExperimentInputArtifact,
    ExperimentRequest,
    ExperimentSnapshot,
    MetaAnnotation,
    ProteinQuantification,
)
from pkg.experiment.mysql_store import MySQLExperimentStore
from pkg.experiment.schema import MYSQL_EXPERIMENT_SCHEMA
from tests.pkg.test_experiment_models import valid_payload


class _Cursor:
    def __init__(self, calls: list[tuple[str, str, Any]], fail_on: str | None = None) -> None:
        self.calls = calls
        self.fail_on = fail_on

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("injected db failure")
        self.calls.append(("execute", query, params))

    def executemany(self, query: str, params: Any) -> None:
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("injected db failure")
        self.calls.append(("executemany", query, params))


class _Connection:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.fail_on = fail_on
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self.calls, self.fail_on)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


def test_schema_is_applied_in_one_transaction() -> None:
    conn = _Connection()
    MySQLExperimentStore(lambda: conn).initialize_schema()
    assert len(conn.calls) == len(MYSQL_EXPERIMENT_SCHEMA)
    assert all(kind == "execute" for kind, _, _ in conn.calls)
    assert conn.commits == 1 and conn.rollbacks == 0 and conn.closed == 1


def test_save_bundle_writes_context_groups_proteins_and_peptides() -> None:
    conn = _Connection()
    store = MySQLExperimentStore(lambda: conn)
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))

    sql = " ".join(query for _, query, _ in conn.calls)
    for table in ("experiment_context", "experiment_group", "protein", "peptide"):
        assert f"INSERT INTO {table}" in sql
    assert conn.commits == 1 and conn.rollbacks == 0 and conn.closed == 1


def test_write_rolls_back_and_closes_on_failure() -> None:
    conn = _Connection(fail_on="INSERT INTO protein")
    store = MySQLExperimentStore(lambda: conn)
    with pytest.raises(RuntimeError, match="injected db failure"):
        store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed == 1


_INSERT_RE = re.compile(r"INSERT INTO (\w+)\s*\(([^)]+)\)", re.S)
_PK: dict[str, tuple[str, ...]] = {
    "experiment_context": ("experiment_id",),
    "experiment_group": ("experiment_id", "group_id"),
    "protein": ("experiment_id", "protein_id"),
    "peptide": ("experiment_id", "peptide_id"),
    "meta_annotation": ("annotation_id",),
    "annotation_history": ("history_id",),
    "experiment_request": ("request_id",),
    "experiment_input_artifact": ("input_artifact_id",),
    "experiment_context_revision": ("revision_id",),
    "experiment_snapshot": ("snapshot_id",),
    "protein_quantification": ("quantification_id",),
    "differential_result": ("differential_id",),
    "enrichment_result": ("enrichment_id",),
}


class _TableCursor:
    """忠实模拟 PyMySQL DictCursor：JSON 列回字符串、DATETIME 回 naive datetime。

    把写入的列名→值原样存表，SELECT 时按列名取回——因此写端/读端列名不一致
    （如 gene 与 gene_symbol）会立刻在往返断言里暴露。
    """

    def __init__(self, store: dict[str, dict]) -> None:
        self._store = store
        self._result: list[dict] = []

    def __enter__(self) -> "_TableCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        match = _INSERT_RE.search(query)
        if match:
            self._ingest(match, [params])
        elif "SELECT" in query.upper():
            self._select(query, params)

    def executemany(self, query: str, seq: Any) -> None:
        match = _INSERT_RE.search(query)
        if match:
            self._ingest(match, list(seq))

    def _ingest(self, match: "re.Match[str]", rows: list[Any]) -> None:
        table = match.group(1)
        columns = [c.strip() for c in match.group(2).split(",")]
        bucket = self._store.setdefault(table, {})
        for params in rows:
            row = dict(zip(columns, params))
            bucket[tuple(row[c] for c in _PK[table])] = row

    def _select(self, query: str, params: Any) -> None:
        table = re.search(r"FROM (\w+)", query).group(1)
        rows = list(self._store.get(table, {}).values())
        if params:
            where = re.search(r"WHERE (\w+)=%s", query)
            if where:
                col = where.group(1)
                rows = [row for row in rows if row.get(col) == params[0]]
        order = re.search(r"ORDER BY (\w+)", query)
        if order:
            rows = sorted(
                rows,
                key=lambda row: row[order.group(1)],
                reverse="DESC" in query[order.end() :].upper(),
            )
        if "LIMIT 1" in query.upper():
            rows = rows[:1]
        self._result = rows

    def fetchone(self) -> dict | None:
        return self._result[0] if self._result else None

    def fetchall(self) -> list[dict]:
        return list(self._result)


class _TableConnection:
    def __init__(self, store: dict[str, dict]) -> None:
        self._store = store

    def cursor(self) -> _TableCursor:
        return _TableCursor(self._store)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def _round_trip_store() -> MySQLExperimentStore:
    """所有连接共享同一张内存表，模拟跨连接持久化。"""

    shared: dict[str, dict] = {}
    return MySQLExperimentStore(lambda: _TableConnection(shared))


def test_mysql_store_round_trips_bundle() -> None:
    store = _round_trip_store()
    bundle = ExperimentBundle.model_validate(valid_payload())
    store.save_bundle(bundle)
    assert store.get_bundle("exp_1") == bundle


def test_mysql_store_maps_gene_symbol_column_to_gene_field() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    assert [p.gene for p in store.list_proteins("exp_1")] == ["Jak2"]


def test_mysql_store_reads_datetimes_as_utc_aware() -> None:
    store = _round_trip_store()
    bundle = ExperimentBundle.model_validate(valid_payload())
    store.save_bundle(bundle)
    context = store.get_context("exp_1")
    assert context is not None
    assert context.created_at.tzinfo == timezone.utc
    assert context.updated_at.tzinfo == timezone.utc
    assert context.created_at == bundle.context.created_at


def test_mysql_store_round_trips_annotations() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    annotation = MetaAnnotation(
        annotation_id="ann_1",
        experiment_id="exp_1",
        target="prot_1",
        target_type=AnnotationTargetType.PROTEIN,
        attribute="disease:CIRI",
        value={"id": "MESH:D002545", "name": "脑缺血"},
        evidence_level=EvidenceLevel.CONCLUSION,
        source="CTD",
        derivation={"ref": "CTD:rel"},
        provenance={"db_version": "2026_03"},
    )
    assert store.add_annotations([annotation]) == 1
    loaded = store.list_annotations("exp_1")
    assert loaded == [annotation]
    assert loaded[0].created_at.tzinfo == timezone.utc


def test_mysql_store_appends_and_round_trips_request_version() -> None:
    store = _round_trip_store()
    bundle = ExperimentBundle.model_validate(valid_payload())
    request = ExperimentRequest(
        request_id="req_1",
        experiment_id="exp_1",
        version=1,
        raw_question=bundle.context.raw_text,
        request_payload={"description": bundle.context.raw_text},
    )
    artifact = ExperimentInputArtifact(
        input_artifact_id="eia_1",
        experiment_id="exp_1",
        request_id="req_1",
        object_id="dobj_1",
        input_role="protein_table",
        filename="proteins.tsv",
        file_hash="sha-1",
    )
    revision = ExperimentContextRevision(
        revision_id="ctxrev_1",
        experiment_id="exp_1",
        request_id="req_1",
        structured_context={"disease": ["CIRI"]},
        parser_version="mapper-v1",
        confirmation_status=ContextConfirmationStatus.PENDING,
    )
    store.append_request(
        request,
        context=bundle.context,
        artifacts=[artifact],
        revision=revision,
    )

    assert store.get_request("req_1") == request
    assert store.get_current_request("exp_1") == request
    assert store.list_requests("exp_1") == [request]
    assert store.list_input_artifacts("req_1") == [artifact]
    assert store.list_context_revisions("req_1") == [revision]
    assert store.get_context("exp_1").current_request_id == "req_1"

    confirmed = ExperimentContextRevision(
        revision_id="ctxrev_2",
        experiment_id="exp_1",
        request_id="req_1",
        structured_context={"disease": ["CIRI"]},
        parser_version="mapper-v1",
        confirmation_status=ContextConfirmationStatus.CONFIRMED,
        confirmed_by="user_1",
    )
    store.append_context_revision(confirmed)
    assert store.list_context_revisions("req_1") == [revision, confirmed]


def test_mysql_store_round_trips_snapshot() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    snapshot = ExperimentSnapshot(
        snapshot_id="snap_1",
        experiment_id="exp_1",
        snapshot_version="1.0",
        pipeline_version="pipe-v1",
        checksum="sum-1",
        general_kg_version={"disease": "2026_03"},
        input_artifact_hashes=["sha-a", "sha-b"],
    )
    store.save_snapshot(snapshot)
    assert store.get_snapshot("snap_1") == snapshot
    assert store.list_snapshots("exp_1") == [snapshot]
    assert store.get_snapshot("snap_1").frozen_at.tzinfo == timezone.utc


def test_mysql_store_round_trips_quantification() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    quant = ProteinQuantification(
        quantification_id="q1",
        experiment_id="exp_1",
        protein_id="prot_1",
        group_id="g_case",
        sample_id="s1",
        abundance=1234.5,
    )
    assert store.add_quantifications([quant]) == 1
    assert store.list_quantifications("exp_1") == [quant]


def test_mysql_store_round_trips_differential_with_and_without_pvalues() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    significant = DifferentialResult(
        differential_id="d1",
        experiment_id="exp_1",
        protein_id="prot_1",
        case_group_id="g_case",
        control_group_id="g_ctrl",
        log2fc=2.0,
        p_value=0.01,
        q_value=0.04,
        direction=DifferentialDirection.UP,
        is_differential=True,
    )
    not_significant = DifferentialResult(
        differential_id="d2",
        experiment_id="exp_1",
        protein_id="prot_1",
        case_group_id="g_ctrl",
        control_group_id="g_case",
        log2fc=0.1,
        direction=DifferentialDirection.NOT_SIGNIFICANT,
        is_differential=False,
    )
    assert store.add_differentials([significant, not_significant]) == 2
    loaded = store.list_differentials("exp_1")
    assert loaded == [significant, not_significant]
    assert loaded[1].p_value is None and loaded[1].q_value is None
    assert loaded[0].is_differential is True and loaded[1].is_differential is False


def test_mysql_store_round_trips_enrichment() -> None:
    store = _round_trip_store()
    store.save_bundle(ExperimentBundle.model_validate(valid_payload()))
    record = EnrichmentRecord(
        enrichment_id="enr_1",
        experiment_id="exp_1",
        term="MESH:DX",
        term_name="Disease X",
        overlap=2,
        study_size=2,
        background_size=5,
        term_size=3,
        p_value=0.01,
        q_value=0.03,
        fold_enrichment=4.0,
        is_significant=True,
        gene_set_source="CTD",
        gene_set_version="2026_03",
        study_checksum="abc",
        background_checksum="def",
        meta={"overlap_genes": ["G1", "G2"]},
    )
    assert store.add_enrichments([record]) == 1
    loaded = store.list_enrichments("exp_1")
    assert loaded == [record]
    assert loaded[0].is_significant is True
    assert loaded[0].meta["overlap_genes"] == ["G1", "G2"]
