"""实验事实库的 MySQL DB-API 实现。"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from .schema import MYSQL_EXPERIMENT_SCHEMA
from .repository import RequestVersionConflict
from .types import (
    AnnotationHistory,
    DifferentialResult,
    EnrichmentRecord,
    ExperimentBundle,
    ExperimentContext,
    ExperimentContextRevision,
    ExperimentGroup,
    ExperimentInputArtifact,
    ExperimentRequest,
    ExperimentSnapshot,
    MetaAnnotation,
    PeptideRecord,
    ProteinQuantification,
    ProteinRecord,
    ReportRecord,
)

ConnectionFactory = Callable[[], Any]


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _db_datetime(value: datetime) -> datetime:
    """MySQL DATETIME 不存时区；统一写入 UTC naive，读取时 Pydantic 接受。"""

    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _from_db_datetime(value: datetime | None) -> datetime | None:
    """与 _db_datetime 对称：MySQL 读回为 naive UTC，补回 tz-aware UTC，保证往返一致。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _request_from_row(row: dict[str, Any]) -> ExperimentRequest:
    return ExperimentRequest(
        request_id=row["request_id"],
        experiment_id=row["experiment_id"],
        version=int(row["version"]),
        raw_question=row["raw_question"],
        request_payload=_json_load(row["request_payload_json"], {}),
        submitted_by=row.get("submitted_by"),
        submitted_at=_from_db_datetime(row["submitted_at"]),
        content_hash=row["content_hash"],
        supersedes_request_id=row.get("supersedes_request_id"),
    )


def _artifact_from_row(row: dict[str, Any]) -> ExperimentInputArtifact:
    return ExperimentInputArtifact(
        input_artifact_id=row["input_artifact_id"],
        experiment_id=row["experiment_id"],
        request_id=row["request_id"],
        object_id=row["object_id"],
        input_role=row["input_role"],
        filename=row["filename"],
        file_hash=row.get("file_hash"),
        file_size=row.get("file_size"),
        upstream_software=row["upstream_software"],
        upstream_version=row["upstream_version"],
        created_at=_from_db_datetime(row["created_at"]),
    )


def _revision_from_row(row: dict[str, Any]) -> ExperimentContextRevision:
    return ExperimentContextRevision(
        revision_id=row["revision_id"],
        experiment_id=row["experiment_id"],
        request_id=row["request_id"],
        structured_context=_json_load(row["structured_context_json"], {}),
        parser_version=row["parser_version"],
        model_version=row.get("model_version"),
        confirmation_status=row["confirmation_status"],
        confirmed_by=row.get("confirmed_by"),
        parsed_at=_from_db_datetime(row["parsed_at"]),
    )


def _quant_from_row(row: dict[str, Any]) -> ProteinQuantification:
    return ProteinQuantification(
        quantification_id=row["quantification_id"],
        experiment_id=row["experiment_id"],
        protein_id=row["protein_id"],
        group_id=row["group_id"],
        sample_id=row["sample_id"],
        abundance=float(row["abundance"]),
        meta=_json_load(row["meta_json"], {}),
    )


def _differential_from_row(row: dict[str, Any]) -> DifferentialResult:
    p_value = row.get("p_value")
    q_value = row.get("q_value")
    return DifferentialResult(
        differential_id=row["differential_id"],
        experiment_id=row["experiment_id"],
        protein_id=row["protein_id"],
        case_group_id=row["case_group_id"],
        control_group_id=row["control_group_id"],
        log2fc=float(row["log2fc"]),
        p_value=float(p_value) if p_value is not None else None,
        q_value=float(q_value) if q_value is not None else None,
        direction=row["direction"],
        is_differential=bool(row["is_differential"]),
        meta=_json_load(row["meta_json"], {}),
    )


def _enrichment_from_row(row: dict[str, Any]) -> EnrichmentRecord:
    p_value = row.get("p_value")
    q_value = row.get("q_value")
    return EnrichmentRecord(
        enrichment_id=row["enrichment_id"],
        experiment_id=row["experiment_id"],
        term=row["term"],
        term_name=row["term_name"],
        term_type=row["term_type"],
        overlap=int(row["overlap"]),
        study_size=int(row["study_size"]),
        background_size=int(row["background_size"]),
        term_size=int(row["term_size"]),
        p_value=float(p_value) if p_value is not None else None,
        q_value=float(q_value) if q_value is not None else None,
        fold_enrichment=float(row["fold_enrichment"]),
        is_significant=bool(row["is_significant"]),
        gene_set_source=row["gene_set_source"],
        gene_set_version=row["gene_set_version"],
        study_checksum=row["study_checksum"],
        background_checksum=row["background_checksum"],
        meta=_json_load(row["meta_json"], {}),
    )


def _snapshot_from_row(row: dict[str, Any]) -> ExperimentSnapshot:
    request_version = row.get("request_version")
    return ExperimentSnapshot(
        snapshot_id=row["snapshot_id"],
        experiment_id=row["experiment_id"],
        snapshot_version=row["snapshot_version"],
        status=row["status"],
        general_kg_version=_json_load(row["general_kg_version_json"], {}),
        pipeline_version=row["pipeline_version"],
        model_version=row.get("model_version"),
        query_and_params=_json_load(row["query_and_params_json"], {}),
        frozen_at=_from_db_datetime(row["frozen_at"]),
        checksum=row["checksum"],
        report_artifact_ref=row["report_artifact_ref"],
        request_id=row.get("request_id"),
        request_version=int(request_version) if request_version is not None else None,
        request_content_hash=row.get("request_content_hash"),
        input_artifact_hashes=_json_load(row["input_artifact_hashes_json"], []),
        manifest=_json_load(row["manifest_json"], {}),
    )


def _report_from_row(row: dict[str, Any]) -> ReportRecord:
    return ReportRecord(
        report_id=row["report_id"],
        experiment_id=row["experiment_id"],
        snapshot_id=row["snapshot_id"],
        snapshot_version=row["snapshot_version"],
        report_format=row["report_format"],
        checksum=row["checksum"],
        content=row["content"],
        sections=_json_load(row["sections_json"], []),
        generated_at=_from_db_datetime(row["generated_at"]),
        meta=_json_load(row["meta_json"], {}),
    )


class MySQLExperimentStore:
    """MySQL 是实验事实的唯一来源；每个公开方法独立事务。"""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @classmethod
    def from_settings(cls) -> "MySQLExperimentStore":
        from config import get_settings

        settings = get_settings().experiment_database

        def connect() -> Any:
            try:
                import pymysql
            except ImportError as exc:  # pragma: no cover - 仅缺运行依赖时触发
                raise RuntimeError(
                    "MySQL experiment store requires PyMySQL; install project requirements"
                ) from exc
            return pymysql.connect(
                host=settings.host,
                port=settings.port,
                user=settings.user,
                password=settings.password,
                database=settings.database,
                charset=settings.charset,
                connect_timeout=settings.connect_timeout_seconds,
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
            )

        return cls(connect)

    def _write(self, callback: Callable[[Any], None]) -> None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                callback(cursor)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _read(self, callback: Callable[[Any], Any]) -> Any:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                return callback(cursor)
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        def apply(cursor: Any) -> None:
            for statement in MYSQL_EXPERIMENT_SCHEMA:
                cursor.execute(statement)

        self._write(apply)

    @staticmethod
    def _upsert_context(cursor: Any, context: ExperimentContext) -> None:
        cursor.execute(
            """
            INSERT INTO experiment_context
              (experiment_id, session_id, title, raw_text, disease_json,
               pathway_json, organism, taxon_id, assay, design_json,
               current_request_id, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              session_id=VALUES(session_id), title=VALUES(title),
              raw_text=VALUES(raw_text), disease_json=VALUES(disease_json),
              pathway_json=VALUES(pathway_json), organism=VALUES(organism),
              taxon_id=VALUES(taxon_id), assay=VALUES(assay),
              design_json=VALUES(design_json),
              current_request_id=COALESCE(VALUES(current_request_id), current_request_id),
              status=VALUES(status), updated_at=VALUES(updated_at)
            """,
            (
                context.experiment_id,
                context.session_id,
                context.title,
                context.raw_text,
                _json_dump(context.disease),
                _json_dump(context.pathway),
                context.organism,
                context.taxon_id,
                context.assay,
                _json_dump(context.design),
                context.current_request_id,
                context.status.value,
                _db_datetime(context.created_at),
                _db_datetime(context.updated_at),
            ),
        )

    def save_bundle(self, bundle: ExperimentBundle) -> None:
        context = bundle.context

        def save(cursor: Any) -> None:
            self._upsert_context(cursor, context)
            cursor.executemany(
                """
                INSERT INTO experiment_group
                  (experiment_id, group_id, label, role, meta_json)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  label=VALUES(label), role=VALUES(role), meta_json=VALUES(meta_json)
                """,
                [
                    (
                        context.experiment_id,
                        group.group_id,
                        group.label,
                        group.role.value,
                        _json_dump(group.meta),
                    )
                    for group in bundle.groups
                ],
            )
            cursor.executemany(
                """
                INSERT INTO protein
                  (experiment_id, protein_id, accession, gene_symbol, organism,
                   taxon_id, peptide_ids_json, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  accession=VALUES(accession), gene_symbol=VALUES(gene_symbol),
                  organism=VALUES(organism), taxon_id=VALUES(taxon_id),
                  peptide_ids_json=VALUES(peptide_ids_json), meta_json=VALUES(meta_json)
                """,
                [
                    (
                        context.experiment_id,
                        protein.protein_id,
                        protein.accession,
                        protein.gene,
                        protein.organism,
                        protein.taxon_id,
                        _json_dump(protein.peptide_ids),
                        _json_dump(protein.meta),
                    )
                    for protein in bundle.proteins
                ],
            )
            if bundle.peptides:
                cursor.executemany(
                    """
                    INSERT INTO peptide
                      (experiment_id, peptide_id, peptidoform, stripped_sequence,
                       protein_id, spectrum_ids_json, confidence, group_label,
                       abundance, meta_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      peptidoform=VALUES(peptidoform),
                      stripped_sequence=VALUES(stripped_sequence),
                      protein_id=VALUES(protein_id),
                      spectrum_ids_json=VALUES(spectrum_ids_json),
                      confidence=VALUES(confidence), group_label=VALUES(group_label),
                      abundance=VALUES(abundance), meta_json=VALUES(meta_json)
                    """,
                    [
                        (
                            context.experiment_id,
                            peptide.peptide_id,
                            peptide.peptidoform,
                            peptide.stripped_sequence,
                            peptide.protein_id,
                            _json_dump(peptide.spectrum_ids),
                            peptide.confidence,
                            peptide.group_label,
                            peptide.abundance,
                            _json_dump(peptide.meta),
                        )
                        for peptide in bundle.peptides
                    ],
                )

        self._write(save)

    def get_context(self, experiment_id: str) -> ExperimentContext | None:
        def fetch(cursor: Any) -> ExperimentContext | None:
            cursor.execute(
                "SELECT * FROM experiment_context WHERE experiment_id=%s",
                (experiment_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ExperimentContext(
                experiment_id=row["experiment_id"],
                session_id=row.get("session_id"),
                title=row["title"],
                raw_text=row["raw_text"],
                disease=_json_load(row["disease_json"], []),
                pathway=_json_load(row["pathway_json"], []),
                organism=row["organism"],
                taxon_id=row.get("taxon_id"),
                assay=row["assay"],
                design=_json_load(row["design_json"], {}),
                current_request_id=row.get("current_request_id"),
                status=row["status"],
                created_at=_from_db_datetime(row["created_at"]),
                updated_at=_from_db_datetime(row["updated_at"]),
            )

        return self._read(fetch)

    def append_request(
        self,
        request: ExperimentRequest,
        *,
        context: ExperimentContext,
        artifacts: Sequence[ExperimentInputArtifact] = (),
        revision: ExperimentContextRevision | None = None,
    ) -> None:
        if request.experiment_id != context.experiment_id:
            raise ValueError("request and context experiment_id must match")
        if request.raw_question != context.raw_text:
            raise ValueError("request raw_question must match context raw_text")
        artifact_keys: set[tuple[str, str]] = set()
        for artifact in artifacts:
            if artifact.experiment_id != request.experiment_id or artifact.request_id != request.request_id:
                raise ValueError("artifact must belong to request and experiment")
            key = (artifact.object_id, artifact.input_role)
            if key in artifact_keys:
                raise ValueError("duplicate object_id/input_role in request artifacts")
            artifact_keys.add(key)
        if revision and (
            revision.experiment_id != request.experiment_id
            or revision.request_id != request.request_id
        ):
            raise ValueError("context revision must belong to request and experiment")

        pointed_context = context.model_copy(
            update={
                "current_request_id": request.request_id,
                "raw_text": request.raw_question,
            },
            deep=True,
        )

        def save(cursor: Any) -> None:
            cursor.execute(
                "SELECT request_id FROM experiment_request WHERE request_id=%s",
                (request.request_id,),
            )
            if cursor.fetchone():
                raise RequestVersionConflict(f"request_id already exists: {request.request_id}")
            cursor.execute(
                """
                SELECT request_id, version FROM experiment_request
                WHERE experiment_id=%s ORDER BY version DESC LIMIT 1 FOR UPDATE
                """,
                (request.experiment_id,),
            )
            previous = cursor.fetchone()
            expected_version = int(previous["version"]) + 1 if previous else 1
            expected_supersedes = previous["request_id"] if previous else None
            if request.version != expected_version:
                raise RequestVersionConflict(
                    f"expected request version {expected_version}, got {request.version}"
                )
            if request.supersedes_request_id != expected_supersedes:
                raise RequestVersionConflict(
                    f"expected supersedes_request_id {expected_supersedes!r}, "
                    f"got {request.supersedes_request_id!r}"
                )

            self._upsert_context(cursor, pointed_context)
            try:
                cursor.execute(
                    """
                    INSERT INTO experiment_request
                      (request_id, experiment_id, version, raw_question,
                       request_payload_json, submitted_by, submitted_at, content_hash,
                       supersedes_request_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request.request_id,
                        request.experiment_id,
                        request.version,
                        request.raw_question,
                        _json_dump(request.request_payload),
                        request.submitted_by,
                        _db_datetime(request.submitted_at),
                        request.content_hash,
                        request.supersedes_request_id,
                    ),
                )
            except Exception as exc:  # 并发首版/版本撞唯一键时统一转成版本冲突
                cursor.execute(
                    """
                    SELECT request_id FROM experiment_request
                    WHERE request_id=%s OR (experiment_id=%s AND version=%s)
                    LIMIT 1
                    """,
                    (request.request_id, request.experiment_id, request.version),
                )
                if cursor.fetchone():
                    raise RequestVersionConflict(
                        f"request {request.request_id} (version {request.version}) "
                        "conflicts with an existing request"
                    ) from exc
                raise
            if artifacts:
                cursor.executemany(
                    """
                    INSERT INTO experiment_input_artifact
                      (input_artifact_id, experiment_id, request_id, object_id,
                       input_role, filename, file_hash, file_size,
                       upstream_software, upstream_version, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            artifact.input_artifact_id,
                            artifact.experiment_id,
                            artifact.request_id,
                            artifact.object_id,
                            artifact.input_role,
                            artifact.filename,
                            artifact.file_hash,
                            artifact.file_size,
                            artifact.upstream_software,
                            artifact.upstream_version,
                            _db_datetime(artifact.created_at),
                        )
                        for artifact in artifacts
                    ],
                )
            if revision:
                cursor.execute(
                    """
                    INSERT INTO experiment_context_revision
                      (revision_id, experiment_id, request_id,
                       structured_context_json, parser_version, model_version,
                       confirmation_status, confirmed_by, parsed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        revision.revision_id,
                        revision.experiment_id,
                        revision.request_id,
                        _json_dump(revision.structured_context),
                        revision.parser_version,
                        revision.model_version,
                        revision.confirmation_status.value,
                        revision.confirmed_by,
                        _db_datetime(revision.parsed_at),
                    ),
                )

        self._write(save)

    def get_request(self, request_id: str) -> ExperimentRequest | None:
        def fetch(cursor: Any) -> ExperimentRequest | None:
            cursor.execute(
                "SELECT * FROM experiment_request WHERE request_id=%s",
                (request_id,),
            )
            row = cursor.fetchone()
            return _request_from_row(row) if row else None

        return self._read(fetch)

    def get_current_request(self, experiment_id: str) -> ExperimentRequest | None:
        context = self.get_context(experiment_id)
        if context is None or context.current_request_id is None:
            return None
        return self.get_request(context.current_request_id)

    def list_requests(self, experiment_id: str) -> list[ExperimentRequest]:
        def fetch(cursor: Any) -> list[ExperimentRequest]:
            cursor.execute(
                """
                SELECT * FROM experiment_request
                WHERE experiment_id=%s ORDER BY version
                """,
                (experiment_id,),
            )
            return [_request_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def list_input_artifacts(self, request_id: str) -> list[ExperimentInputArtifact]:
        def fetch(cursor: Any) -> list[ExperimentInputArtifact]:
            cursor.execute(
                """
                SELECT * FROM experiment_input_artifact
                WHERE request_id=%s ORDER BY input_artifact_id
                """,
                (request_id,),
            )
            return [_artifact_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def list_context_revisions(self, request_id: str) -> list[ExperimentContextRevision]:
        def fetch(cursor: Any) -> list[ExperimentContextRevision]:
            cursor.execute(
                """
                SELECT * FROM experiment_context_revision
                WHERE request_id=%s ORDER BY parsed_at
                """,
                (request_id,),
            )
            return [_revision_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def append_context_revision(self, revision: ExperimentContextRevision) -> None:
        def save(cursor: Any) -> None:
            cursor.execute(
                "SELECT experiment_id FROM experiment_request WHERE request_id=%s",
                (revision.request_id,),
            )
            request = cursor.fetchone()
            if request is None:
                raise ValueError(f"unknown request_id: {revision.request_id}")
            if request["experiment_id"] != revision.experiment_id:
                raise ValueError("context revision experiment_id does not match request")
            cursor.execute(
                """
                INSERT INTO experiment_context_revision
                  (revision_id, experiment_id, request_id,
                   structured_context_json, parser_version, model_version,
                   confirmation_status, confirmed_by, parsed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    revision.revision_id,
                    revision.experiment_id,
                    revision.request_id,
                    _json_dump(revision.structured_context),
                    revision.parser_version,
                    revision.model_version,
                    revision.confirmation_status.value,
                    revision.confirmed_by,
                    _db_datetime(revision.parsed_at),
                ),
            )

        self._write(save)

    def list_groups(self, experiment_id: str) -> list[ExperimentGroup]:
        def fetch(cursor: Any) -> list[ExperimentGroup]:
            cursor.execute(
                """
                SELECT * FROM experiment_group
                WHERE experiment_id=%s ORDER BY group_id
                """,
                (experiment_id,),
            )
            return [
                ExperimentGroup(
                    group_id=row["group_id"],
                    label=row["label"],
                    role=row["role"],
                    meta=_json_load(row["meta_json"], {}),
                )
                for row in cursor.fetchall()
            ]

        return self._read(fetch)

    def list_proteins(self, experiment_id: str) -> list[ProteinRecord]:
        def fetch(cursor: Any) -> list[ProteinRecord]:
            cursor.execute(
                "SELECT * FROM protein WHERE experiment_id=%s ORDER BY protein_id",
                (experiment_id,),
            )
            return [
                ProteinRecord(
                    protein_id=row["protein_id"],
                    accession=row["accession"],
                    gene=row["gene_symbol"],
                    organism=row["organism"],
                    taxon_id=row.get("taxon_id"),
                    peptide_ids=_json_load(row["peptide_ids_json"], []),
                    meta=_json_load(row["meta_json"], {}),
                )
                for row in cursor.fetchall()
            ]

        return self._read(fetch)

    def list_peptides(self, experiment_id: str) -> list[PeptideRecord]:
        def fetch(cursor: Any) -> list[PeptideRecord]:
            cursor.execute(
                "SELECT * FROM peptide WHERE experiment_id=%s ORDER BY peptide_id",
                (experiment_id,),
            )
            return [
                PeptideRecord(
                    peptide_id=row["peptide_id"],
                    peptidoform=row["peptidoform"],
                    stripped_sequence=row["stripped_sequence"],
                    protein_id=row["protein_id"],
                    spectrum_ids=_json_load(row["spectrum_ids_json"], []),
                    confidence=float(row["confidence"]),
                    group_label=row["group_label"],
                    abundance=row.get("abundance"),
                    meta=_json_load(row["meta_json"], {}),
                )
                for row in cursor.fetchall()
            ]

        return self._read(fetch)

    def get_bundle(self, experiment_id: str) -> ExperimentBundle | None:
        context = self.get_context(experiment_id)
        if context is None:
            return None
        return ExperimentBundle(
            context=context,
            groups=self.list_groups(experiment_id),
            proteins=self.list_proteins(experiment_id),
            peptides=self.list_peptides(experiment_id),
        )

    def add_annotations(self, rows: list[MetaAnnotation]) -> int:
        if not rows:
            return 0

        def save(cursor: Any) -> None:
            cursor.executemany(
                """
                INSERT INTO meta_annotation
                  (annotation_id, experiment_id, target, target_type, attribute,
                   value_json, evidence_level, source, derivation_json,
                   provenance_json, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  target=VALUES(target), target_type=VALUES(target_type),
                  attribute=VALUES(attribute), value_json=VALUES(value_json),
                  evidence_level=VALUES(evidence_level), source=VALUES(source),
                  derivation_json=VALUES(derivation_json),
                  provenance_json=VALUES(provenance_json),
                  updated_at=VALUES(updated_at)
                """,
                [
                    (
                        row.annotation_id,
                        row.experiment_id,
                        row.target,
                        row.target_type.value,
                        row.attribute,
                        _json_dump(row.value),
                        row.evidence_level.value,
                        row.source,
                        _json_dump(row.derivation),
                        _json_dump(row.provenance),
                        _db_datetime(row.created_at),
                        _db_datetime(row.updated_at),
                    )
                    for row in rows
                ],
            )

        self._write(save)
        return len(rows)

    def list_annotations(self, experiment_id: str) -> list[MetaAnnotation]:
        def fetch(cursor: Any) -> list[MetaAnnotation]:
            cursor.execute(
                """
                SELECT * FROM meta_annotation
                WHERE experiment_id=%s ORDER BY annotation_id
                """,
                (experiment_id,),
            )
            return [
                MetaAnnotation(
                    annotation_id=row["annotation_id"],
                    experiment_id=row["experiment_id"],
                    target=row["target"],
                    target_type=row["target_type"],
                    attribute=row["attribute"],
                    value=_json_load(row["value_json"], None),
                    evidence_level=row["evidence_level"],
                    source=row["source"],
                    derivation=_json_load(row["derivation_json"], {}),
                    provenance=_json_load(row["provenance_json"], {}),
                    created_at=_from_db_datetime(row["created_at"]),
                    updated_at=_from_db_datetime(row["updated_at"]),
                )
                for row in cursor.fetchall()
            ]

        return self._read(fetch)

    def append_annotation_history(self, row: AnnotationHistory) -> None:
        def save(cursor: Any) -> None:
            cursor.execute(
                """
                INSERT INTO annotation_history
                  (history_id, annotation_id, experiment_id, from_level, to_level,
                   verdict, evidence_ref_json, changed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.history_id,
                    row.annotation_id,
                    row.experiment_id,
                    row.from_level.value if row.from_level else None,
                    row.to_level.value,
                    row.verdict,
                    _json_dump(row.evidence_ref),
                    _db_datetime(row.changed_at),
                ),
            )

        self._write(save)

    def list_annotation_history(self, experiment_id: str) -> list[AnnotationHistory]:
        def fetch(cursor: Any) -> list[AnnotationHistory]:
            cursor.execute(
                """
                SELECT * FROM annotation_history
                WHERE experiment_id=%s ORDER BY changed_at, history_id
                """,
                (experiment_id,),
            )
            return [
                AnnotationHistory(
                    history_id=row["history_id"],
                    annotation_id=row["annotation_id"],
                    experiment_id=row["experiment_id"],
                    from_level=row["from_level"],
                    to_level=row["to_level"],
                    verdict=row["verdict"],
                    evidence_ref=_json_load(row["evidence_ref_json"], {}),
                    changed_at=_from_db_datetime(row["changed_at"]),
                )
                for row in cursor.fetchall()
            ]

        return self._read(fetch)

    def add_quantifications(self, rows: list[ProteinQuantification]) -> int:
        if not rows:
            return 0

        def save(cursor: Any) -> None:
            cursor.executemany(
                """
                INSERT INTO protein_quantification
                  (quantification_id, experiment_id, protein_id, group_id,
                   sample_id, abundance, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  abundance=VALUES(abundance), meta_json=VALUES(meta_json)
                """,
                [
                    (
                        row.quantification_id,
                        row.experiment_id,
                        row.protein_id,
                        row.group_id,
                        row.sample_id,
                        row.abundance,
                        _json_dump(row.meta),
                    )
                    for row in rows
                ],
            )

        self._write(save)
        return len(rows)

    def list_quantifications(self, experiment_id: str) -> list[ProteinQuantification]:
        def fetch(cursor: Any) -> list[ProteinQuantification]:
            cursor.execute(
                """
                SELECT * FROM protein_quantification
                WHERE experiment_id=%s ORDER BY quantification_id
                """,
                (experiment_id,),
            )
            return [_quant_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def add_differentials(self, rows: list[DifferentialResult]) -> int:
        if not rows:
            return 0

        def save(cursor: Any) -> None:
            cursor.executemany(
                """
                INSERT INTO differential_result
                  (differential_id, experiment_id, protein_id, case_group_id,
                   control_group_id, log2fc, p_value, q_value, direction,
                   is_differential, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  log2fc=VALUES(log2fc), p_value=VALUES(p_value),
                  q_value=VALUES(q_value), direction=VALUES(direction),
                  is_differential=VALUES(is_differential), meta_json=VALUES(meta_json)
                """,
                [
                    (
                        row.differential_id,
                        row.experiment_id,
                        row.protein_id,
                        row.case_group_id,
                        row.control_group_id,
                        row.log2fc,
                        row.p_value,
                        row.q_value,
                        row.direction.value,
                        row.is_differential,
                        _json_dump(row.meta),
                    )
                    for row in rows
                ],
            )

        self._write(save)
        return len(rows)

    def list_differentials(self, experiment_id: str) -> list[DifferentialResult]:
        def fetch(cursor: Any) -> list[DifferentialResult]:
            cursor.execute(
                """
                SELECT * FROM differential_result
                WHERE experiment_id=%s ORDER BY differential_id
                """,
                (experiment_id,),
            )
            return [_differential_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def add_enrichments(self, rows: list[EnrichmentRecord]) -> int:
        if not rows:
            return 0

        def save(cursor: Any) -> None:
            cursor.executemany(
                """
                INSERT INTO enrichment_result
                  (enrichment_id, experiment_id, term, term_name, term_type,
                   overlap, study_size, background_size, term_size,
                   p_value, q_value, fold_enrichment, is_significant,
                   gene_set_source, gene_set_version, study_checksum,
                   background_checksum, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  term_name=VALUES(term_name), overlap=VALUES(overlap),
                  study_size=VALUES(study_size), background_size=VALUES(background_size),
                  term_size=VALUES(term_size), p_value=VALUES(p_value),
                  q_value=VALUES(q_value), fold_enrichment=VALUES(fold_enrichment),
                  is_significant=VALUES(is_significant),
                  gene_set_source=VALUES(gene_set_source),
                  gene_set_version=VALUES(gene_set_version),
                  study_checksum=VALUES(study_checksum),
                  background_checksum=VALUES(background_checksum),
                  meta_json=VALUES(meta_json)
                """,
                [
                    (
                        row.enrichment_id,
                        row.experiment_id,
                        row.term,
                        row.term_name,
                        row.term_type,
                        row.overlap,
                        row.study_size,
                        row.background_size,
                        row.term_size,
                        row.p_value,
                        row.q_value,
                        row.fold_enrichment,
                        row.is_significant,
                        row.gene_set_source,
                        row.gene_set_version,
                        row.study_checksum,
                        row.background_checksum,
                        _json_dump(row.meta),
                    )
                    for row in rows
                ],
            )

        self._write(save)
        return len(rows)

    def list_enrichments(self, experiment_id: str) -> list[EnrichmentRecord]:
        def fetch(cursor: Any) -> list[EnrichmentRecord]:
            cursor.execute(
                """
                SELECT * FROM enrichment_result
                WHERE experiment_id=%s ORDER BY enrichment_id
                """,
                (experiment_id,),
            )
            return [_enrichment_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def save_snapshot(self, snapshot: ExperimentSnapshot) -> None:
        def save(cursor: Any) -> None:
            cursor.execute(
                """
                INSERT INTO experiment_snapshot
                  (snapshot_id, experiment_id, snapshot_version, status,
                   general_kg_version_json, pipeline_version, model_version,
                   query_and_params_json, frozen_at, checksum, report_artifact_ref,
                   request_id, request_version, request_content_hash,
                   input_artifact_hashes_json, manifest_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.experiment_id,
                    snapshot.snapshot_version,
                    snapshot.status.value,
                    _json_dump(snapshot.general_kg_version),
                    snapshot.pipeline_version,
                    snapshot.model_version,
                    _json_dump(snapshot.query_and_params),
                    _db_datetime(snapshot.frozen_at),
                    snapshot.checksum,
                    snapshot.report_artifact_ref,
                    snapshot.request_id,
                    snapshot.request_version,
                    snapshot.request_content_hash,
                    _json_dump(snapshot.input_artifact_hashes),
                    _json_dump(snapshot.manifest),
                ),
            )

        self._write(save)

    def get_snapshot(self, snapshot_id: str) -> ExperimentSnapshot | None:
        def fetch(cursor: Any) -> ExperimentSnapshot | None:
            cursor.execute(
                "SELECT * FROM experiment_snapshot WHERE snapshot_id=%s",
                (snapshot_id,),
            )
            row = cursor.fetchone()
            return _snapshot_from_row(row) if row else None

        return self._read(fetch)

    def list_snapshots(self, experiment_id: str) -> list[ExperimentSnapshot]:
        def fetch(cursor: Any) -> list[ExperimentSnapshot]:
            cursor.execute(
                """
                SELECT * FROM experiment_snapshot
                WHERE experiment_id=%s ORDER BY frozen_at
                """,
                (experiment_id,),
            )
            return [_snapshot_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)

    def save_report(self, report: ReportRecord) -> None:
        def save(cursor: Any) -> None:
            cursor.execute(
                """
                INSERT INTO experiment_report
                  (report_id, experiment_id, snapshot_id, snapshot_version,
                   report_format, checksum, content, sections_json,
                   generated_at, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  snapshot_id=VALUES(snapshot_id), report_format=VALUES(report_format),
                  checksum=VALUES(checksum), content=VALUES(content),
                  sections_json=VALUES(sections_json), generated_at=VALUES(generated_at),
                  meta_json=VALUES(meta_json)
                """,
                (
                    report.report_id,
                    report.experiment_id,
                    report.snapshot_id,
                    report.snapshot_version,
                    report.report_format,
                    report.checksum,
                    report.content,
                    _json_dump(report.sections),
                    _db_datetime(report.generated_at),
                    _json_dump(report.meta),
                ),
            )

        self._write(save)

    def get_report(self, experiment_id: str, snapshot_version: str) -> ReportRecord | None:
        def fetch(cursor: Any) -> ReportRecord | None:
            cursor.execute(
                """
                SELECT * FROM experiment_report
                WHERE experiment_id=%s AND snapshot_version=%s
                """,
                (experiment_id, snapshot_version),
            )
            row = cursor.fetchone()
            return _report_from_row(row) if row else None

        return self._read(fetch)

    def list_reports(self, experiment_id: str) -> list[ReportRecord]:
        def fetch(cursor: Any) -> list[ReportRecord]:
            cursor.execute(
                """
                SELECT * FROM experiment_report
                WHERE experiment_id=%s ORDER BY generated_at
                """,
                (experiment_id,),
            )
            return [_report_from_row(row) for row in cursor.fetchall()]

        return self._read(fetch)


_store: MySQLExperimentStore | None = None


def get_experiment_store() -> MySQLExperimentStore:
    global _store
    if _store is None:
        _store = MySQLExperimentStore.from_settings()
    return _store


__all__ = ["ConnectionFactory", "MySQLExperimentStore", "get_experiment_store"]
