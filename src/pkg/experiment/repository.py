"""实验事实库端口。

应用层只依赖这个协议；MySQL 是正式实现，测试可使用内存实现。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

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
    ExperimentStatus,
    MetaAnnotation,
    PeptideRecord,
    ProteinQuantification,
    ProteinRecord,
    ReportRecord,
    StructureEvidenceStatus,
)


class RequestVersionConflict(ValueError):
    """请求版本不是严格追加，或试图复用已有 request ID/version。"""


@runtime_checkable
class ExperimentRepository(Protocol):
    def initialize_schema(self) -> None: ...

    def save_bundle(self, bundle: ExperimentBundle) -> None: ...

    def get_context(self, experiment_id: str) -> ExperimentContext | None: ...

    def append_request(
        self,
        request: ExperimentRequest,
        *,
        context: ExperimentContext,
        artifacts: Sequence[ExperimentInputArtifact] = (),
        revision: ExperimentContextRevision | None = None,
    ) -> None: ...

    def get_request(self, request_id: str) -> ExperimentRequest | None: ...

    def get_current_request(self, experiment_id: str) -> ExperimentRequest | None: ...

    def list_requests(self, experiment_id: str) -> list[ExperimentRequest]: ...

    def list_input_artifacts(self, request_id: str) -> list[ExperimentInputArtifact]: ...

    def list_context_revisions(self, request_id: str) -> list[ExperimentContextRevision]: ...

    def append_context_revision(self, revision: ExperimentContextRevision) -> None: ...

    def get_bundle(self, experiment_id: str) -> ExperimentBundle | None: ...

    def list_groups(self, experiment_id: str) -> list[ExperimentGroup]: ...

    def list_proteins(self, experiment_id: str) -> list[ProteinRecord]: ...

    def list_peptides(self, experiment_id: str) -> list[PeptideRecord]: ...

    def add_annotations(self, rows: list[MetaAnnotation]) -> int: ...

    def list_annotations(self, experiment_id: str) -> list[MetaAnnotation]: ...

    def append_annotation_history(self, row: AnnotationHistory) -> None: ...

    def list_annotation_history(self, experiment_id: str) -> list[AnnotationHistory]: ...

    def add_quantifications(self, rows: list[ProteinQuantification]) -> int: ...

    def list_quantifications(self, experiment_id: str) -> list[ProteinQuantification]: ...

    def add_structure_statuses(self, rows: list[StructureEvidenceStatus]) -> int: ...

    def list_structure_statuses(self, experiment_id: str) -> list[StructureEvidenceStatus]: ...

    def add_differentials(self, rows: list[DifferentialResult]) -> int: ...

    def list_differentials(self, experiment_id: str) -> list[DifferentialResult]: ...

    def add_enrichments(self, rows: list[EnrichmentRecord]) -> int: ...

    def list_enrichments(self, experiment_id: str) -> list[EnrichmentRecord]: ...

    def save_snapshot(self, snapshot: ExperimentSnapshot) -> None: ...

    def get_snapshot(self, snapshot_id: str) -> ExperimentSnapshot | None: ...

    def list_snapshots(self, experiment_id: str) -> list[ExperimentSnapshot]: ...

    def supersede_other_snapshots(
        self, experiment_id: str, *, keep_snapshot_id: str
    ) -> int: ...

    def save_report(self, report: ReportRecord) -> None: ...

    def get_report(self, experiment_id: str, snapshot_version: str) -> ReportRecord | None: ...

    def list_reports(self, experiment_id: str) -> list[ReportRecord]: ...


class InMemoryExperimentRepository:
    """确定性的测试/开发实现，不作为生产事实库。"""

    def __init__(self) -> None:
        self._bundles: dict[str, ExperimentBundle] = {}
        self._contexts: dict[str, ExperimentContext] = {}
        self._annotations: dict[str, dict[str, MetaAnnotation]] = {}
        self._history: list[AnnotationHistory] = []
        self._requests: dict[str, ExperimentRequest] = {}
        self._request_ids: dict[str, list[str]] = {}
        self._artifacts: dict[str, list[ExperimentInputArtifact]] = {}
        self._revisions: dict[str, list[ExperimentContextRevision]] = {}
        self._quantifications: dict[str, dict[str, ProteinQuantification]] = {}
        self._structure_statuses: dict[str, dict[str, StructureEvidenceStatus]] = {}
        self._differentials: dict[str, dict[str, DifferentialResult]] = {}
        self._enrichments: dict[str, dict[str, EnrichmentRecord]] = {}
        self._snapshots: dict[str, ExperimentSnapshot] = {}
        self._snapshot_ids: dict[str, list[str]] = {}
        self._reports: dict[str, dict[str, ReportRecord]] = {}

    def initialize_schema(self) -> None:
        return None

    def save_bundle(self, bundle: ExperimentBundle) -> None:
        experiment_id = bundle.context.experiment_id
        current = self._contexts.get(experiment_id)
        stored = bundle.model_copy(deep=True)
        if current:
            stored.context.created_at = current.created_at
            if stored.context.current_request_id is None:
                stored.context.current_request_id = current.current_request_id
        self._bundles[experiment_id] = stored
        self._contexts[experiment_id] = stored.context.model_copy(deep=True)

    def get_context(self, experiment_id: str) -> ExperimentContext | None:
        context = self._contexts.get(experiment_id)
        return context.model_copy(deep=True) if context else None

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
        if request.request_id in self._requests:
            raise RequestVersionConflict(f"request_id already exists: {request.request_id}")

        ids = self._request_ids.get(request.experiment_id, [])
        previous = self._requests[ids[-1]] if ids else None
        expected_version = previous.version + 1 if previous else 1
        expected_supersedes = previous.request_id if previous else None
        if request.version != expected_version:
            raise RequestVersionConflict(
                f"expected request version {expected_version}, got {request.version}"
            )
        if request.supersedes_request_id != expected_supersedes:
            raise RequestVersionConflict(
                f"expected supersedes_request_id {expected_supersedes!r}, "
                f"got {request.supersedes_request_id!r}"
            )
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

        stored_request = request.model_copy(deep=True)
        self._requests[request.request_id] = stored_request
        self._request_ids.setdefault(request.experiment_id, []).append(request.request_id)
        self._artifacts[request.request_id] = [a.model_copy(deep=True) for a in artifacts]
        self._revisions[request.request_id] = (
            [revision.model_copy(deep=True)] if revision else []
        )
        stored_context = context.model_copy(deep=True)
        stored_context.current_request_id = request.request_id
        existing = self._contexts.get(request.experiment_id)
        if existing:
            stored_context.created_at = existing.created_at
        self._contexts[request.experiment_id] = stored_context
        bundle = self._bundles.get(request.experiment_id)
        if bundle:
            bundle.context = stored_context.model_copy(deep=True)

    def get_request(self, request_id: str) -> ExperimentRequest | None:
        request = self._requests.get(request_id)
        return request.model_copy(deep=True) if request else None

    def get_current_request(self, experiment_id: str) -> ExperimentRequest | None:
        context = self._contexts.get(experiment_id)
        if not context or not context.current_request_id:
            return None
        return self.get_request(context.current_request_id)

    def list_requests(self, experiment_id: str) -> list[ExperimentRequest]:
        return [self._requests[rid].model_copy(deep=True) for rid in self._request_ids.get(experiment_id, [])]

    def list_input_artifacts(self, request_id: str) -> list[ExperimentInputArtifact]:
        return [a.model_copy(deep=True) for a in self._artifacts.get(request_id, [])]

    def list_context_revisions(self, request_id: str) -> list[ExperimentContextRevision]:
        return [r.model_copy(deep=True) for r in self._revisions.get(request_id, [])]

    def append_context_revision(self, revision: ExperimentContextRevision) -> None:
        request = self._requests.get(revision.request_id)
        if request is None:
            raise ValueError(f"unknown request_id: {revision.request_id}")
        if request.experiment_id != revision.experiment_id:
            raise ValueError("context revision experiment_id does not match request")
        revisions = self._revisions.setdefault(revision.request_id, [])
        if any(row.revision_id == revision.revision_id for row in revisions):
            raise RequestVersionConflict(
                f"revision_id already exists: {revision.revision_id}"
            )
        revisions.append(revision.model_copy(deep=True))

    def get_bundle(self, experiment_id: str) -> ExperimentBundle | None:
        bundle = self._bundles.get(experiment_id)
        if not bundle:
            return None
        out = bundle.model_copy(deep=True)
        context = self._contexts.get(experiment_id)
        if context:
            out.context = context.model_copy(deep=True)
        return out

    def list_groups(self, experiment_id: str) -> list[ExperimentGroup]:
        bundle = self._bundles.get(experiment_id)
        return [g.model_copy(deep=True) for g in bundle.groups] if bundle else []

    def list_proteins(self, experiment_id: str) -> list[ProteinRecord]:
        bundle = self._bundles.get(experiment_id)
        return [p.model_copy(deep=True) for p in bundle.proteins] if bundle else []

    def list_peptides(self, experiment_id: str) -> list[PeptideRecord]:
        bundle = self._bundles.get(experiment_id)
        return [p.model_copy(deep=True) for p in bundle.peptides] if bundle else []

    def add_annotations(self, rows: list[MetaAnnotation]) -> int:
        for row in rows:
            bucket = self._annotations.setdefault(row.experiment_id, {})
            bucket[row.annotation_id] = row.model_copy(deep=True)
        return len(rows)

    def list_annotations(self, experiment_id: str) -> list[MetaAnnotation]:
        rows = self._annotations.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]

    def append_annotation_history(self, row: AnnotationHistory) -> None:
        self._history.append(row.model_copy(deep=True))

    def list_annotation_history(self, experiment_id: str) -> list[AnnotationHistory]:
        rows = [h for h in self._history if h.experiment_id == experiment_id]
        return sorted(
            (h.model_copy(deep=True) for h in rows),
            key=lambda h: (h.changed_at, h.history_id),
        )

    def add_quantifications(self, rows: list[ProteinQuantification]) -> int:
        for row in rows:
            bucket = self._quantifications.setdefault(row.experiment_id, {})
            key = f"{row.protein_id}\0{row.group_id}\0{row.sample_id}"
            bucket[key] = row.model_copy(deep=True)
        return len(rows)

    def list_quantifications(self, experiment_id: str) -> list[ProteinQuantification]:
        rows = self._quantifications.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]

    def add_structure_statuses(self, rows: list[StructureEvidenceStatus]) -> int:
        for row in rows:
            bucket = self._structure_statuses.setdefault(row.experiment_id, {})
            key = f"{row.protein_id}\0{row.channel}"
            bucket[key] = row.model_copy(deep=True)
        return len(rows)

    def list_structure_statuses(self, experiment_id: str) -> list[StructureEvidenceStatus]:
        rows = self._structure_statuses.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]

    def add_differentials(self, rows: list[DifferentialResult]) -> int:
        for row in rows:
            bucket = self._differentials.setdefault(row.experiment_id, {})
            key = f"{row.protein_id}\0{row.case_group_id}\0{row.control_group_id}"
            bucket[key] = row.model_copy(deep=True)
        return len(rows)

    def list_differentials(self, experiment_id: str) -> list[DifferentialResult]:
        rows = self._differentials.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]

    def add_enrichments(self, rows: list[EnrichmentRecord]) -> int:
        for row in rows:
            bucket = self._enrichments.setdefault(row.experiment_id, {})
            key = f"{row.term_type}\0{row.term}"
            bucket[key] = row.model_copy(deep=True)
        return len(rows)

    def list_enrichments(self, experiment_id: str) -> list[EnrichmentRecord]:
        rows = self._enrichments.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]

    def save_snapshot(self, snapshot: ExperimentSnapshot) -> None:
        if snapshot.snapshot_id in self._snapshots:
            raise RequestVersionConflict(
                f"snapshot_id already exists: {snapshot.snapshot_id}"
            )
        for existing_id in self._snapshot_ids.get(snapshot.experiment_id, []):
            existing = self._snapshots[existing_id]
            if existing.snapshot_version == snapshot.snapshot_version:
                raise RequestVersionConflict(
                    f"snapshot version already exists: {snapshot.snapshot_version}"
                )
        self._snapshots[snapshot.snapshot_id] = snapshot.model_copy(deep=True)
        self._snapshot_ids.setdefault(snapshot.experiment_id, []).append(
            snapshot.snapshot_id
        )

    def get_snapshot(self, snapshot_id: str) -> ExperimentSnapshot | None:
        snapshot = self._snapshots.get(snapshot_id)
        return snapshot.model_copy(deep=True) if snapshot else None

    def list_snapshots(self, experiment_id: str) -> list[ExperimentSnapshot]:
        ids = self._snapshot_ids.get(experiment_id, [])
        snapshots = [self._snapshots[sid].model_copy(deep=True) for sid in ids]
        return sorted(snapshots, key=lambda snap: snap.frozen_at)

    def supersede_other_snapshots(
        self, experiment_id: str, *, keep_snapshot_id: str
    ) -> int:
        # 新版本生效 → 把该实验其余 FINAL 快照标 SUPERSEDED（不删，仍可读、仍自洽）。
        count = 0
        for sid in self._snapshot_ids.get(experiment_id, []):
            snap = self._snapshots[sid]
            if sid != keep_snapshot_id and snap.status is ExperimentStatus.FINAL:
                self._snapshots[sid] = snap.model_copy(
                    update={"status": ExperimentStatus.SUPERSEDED}
                )
                count += 1
        return count

    def save_report(self, report: ReportRecord) -> None:
        # 按 (experiment_id, snapshot_version) 幂等 upsert：确定性渲染重复落库不增行。
        bucket = self._reports.setdefault(report.experiment_id, {})
        bucket[report.snapshot_version] = report.model_copy(deep=True)

    def get_report(self, experiment_id: str, snapshot_version: str) -> ReportRecord | None:
        report = self._reports.get(experiment_id, {}).get(snapshot_version)
        return report.model_copy(deep=True) if report else None

    def list_reports(self, experiment_id: str) -> list[ReportRecord]:
        rows = self._reports.get(experiment_id, {})
        return [rows[key].model_copy(deep=True) for key in sorted(rows)]


__all__ = [
    "ExperimentRepository",
    "InMemoryExperimentRepository",
    "RequestVersionConflict",
]
