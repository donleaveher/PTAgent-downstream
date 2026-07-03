"""下游实验域模型。

这些类型描述项目的新输入边界：已鉴定蛋白/肽、实验背景与分组。
它们不包含谱图鉴定、查库归属或蛋白推断逻辑。
"""

from __future__ import annotations

import uuid
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """持久化域模型的共同校验策略。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GroupRole(str, Enum):
    CASE = "case"
    CONTROL = "control"


class EvidenceLevel(str, Enum):
    CONCLUSION = "CONCLUSION"
    HYPOTHESIS = "HYPOTHESIS"
    REFUTED = "REFUTED"


class AnnotationTargetType(str, Enum):
    PROTEIN = "protein"
    GENE = "gene"


class DifferentialDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    NOT_SIGNIFICANT = "not_significant"


class ExperimentStatus(str, Enum):
    WORKING = "WORKING"
    FINAL = "FINAL"
    SUPERSEDED = "SUPERSEDED"


class ContextConfirmationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ExperimentContext(StrictModel):
    experiment_id: str = Field(default_factory=lambda: _new_id("exp"), min_length=1)
    session_id: str | None = None
    title: str = ""
    raw_text: str = ""
    disease: list[str] = Field(default_factory=list)
    pathway: list[str] = Field(default_factory=list)
    organism: str = ""
    taxon_id: int | None = Field(default=None, gt=0)
    assay: str = ""
    design: dict[str, Any] = Field(default_factory=dict)
    current_request_id: str | None = None
    status: ExperimentStatus = ExperimentStatus.WORKING
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


def request_content_hash(raw_question: str, request_payload: dict[str, Any]) -> str:
    """原始问题与完整请求 payload 的稳定 SHA-256。"""

    canonical = json.dumps(
        {"raw_question": raw_question, "request_payload": request_payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExperimentRequest(StrictModel):
    """不可变的原始实验请求版本；修改问题时必须创建下一版本。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    request_id: str = Field(default_factory=lambda: _new_id("req"), min_length=1)
    experiment_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    raw_question: str = Field(min_length=1)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    submitted_by: str | None = None
    submitted_at: datetime = Field(default_factory=_utcnow)
    content_hash: str = ""
    supersedes_request_id: str | None = None

    @model_validator(mode="after")
    def _validate_version_chain_shape(self) -> "ExperimentRequest":
        if self.version == 1 and self.supersedes_request_id is not None:
            raise ValueError("request version 1 cannot supersede another request")
        if self.version > 1 and self.supersedes_request_id is None:
            raise ValueError("request version >1 must set supersedes_request_id")
        expected = request_content_hash(self.raw_question, self.request_payload)
        if self.content_hash and self.content_hash != expected:
            raise ValueError("request content_hash does not match content")
        if not self.content_hash:
            object.__setattr__(self, "content_hash", expected)
        return self


class ExperimentInputArtifact(StrictModel):
    """某一原始请求版本使用的 DataObject 引用。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    input_artifact_id: str = Field(default_factory=lambda: _new_id("eia"), min_length=1)
    experiment_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    input_role: str = Field(min_length=1)
    filename: str = ""
    file_hash: str | None = None
    file_size: int | None = Field(default=None, ge=0)
    upstream_software: str = ""
    upstream_version: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ExperimentContextRevision(StrictModel):
    """某一请求版本对应的一次结构化解析结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    revision_id: str = Field(default_factory=lambda: _new_id("ctxrev"), min_length=1)
    experiment_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    structured_context: dict[str, Any] = Field(default_factory=dict)
    parser_version: str = Field(min_length=1)
    model_version: str | None = None
    confirmation_status: ContextConfirmationStatus = ContextConfirmationStatus.PENDING
    confirmed_by: str | None = None
    parsed_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _confirmed_revision_requires_actor(self) -> "ExperimentContextRevision":
        if (
            self.confirmation_status is ContextConfirmationStatus.CONFIRMED
            and not self.confirmed_by
        ):
            raise ValueError("confirmed context revision requires confirmed_by")
        return self


class ExperimentGroup(StrictModel):
    group_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: GroupRole
    meta: dict[str, Any] = Field(default_factory=dict)


class PeptideRecord(StrictModel):
    peptide_id: str = Field(min_length=1)
    peptidoform: str = Field(min_length=1)
    stripped_sequence: str = Field(min_length=1)
    protein_id: str = Field(min_length=1)
    spectrum_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    group_label: str = Field(min_length=1)
    abundance: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ProteinRecord(StrictModel):
    protein_id: str = Field(min_length=1)
    accession: str = Field(min_length=1)
    gene: str = Field(min_length=1)
    organism: str = ""
    taxon_id: int | None = Field(default=None, gt=0)
    peptide_ids: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ProteinQuantification(StrictModel):
    quantification_id: str = Field(default_factory=lambda: _new_id("quant"))
    experiment_id: str = Field(min_length=1)
    protein_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    abundance: float
    meta: dict[str, Any] = Field(default_factory=dict)


class StructureEvidenceStatus(StrictModel):
    """结构证据通道对某个实验蛋白的解析状态。

    该表记录结构通道的可用性和缺失原因，不存 `.cif/.pdb` 大对象。
    """

    experiment_id: str = Field(min_length=1)
    protein_id: str = Field(min_length=1)
    raw_accession: str = Field(min_length=1)
    normalized_accession: str = ""
    channel: str = "structure"
    status: str = Field(min_length=1)
    reason: str = ""
    provider: str = "AlphaFoldDB"
    provider_version: str = ""
    structure_id: str = ""
    structure_format: str = ""
    local_path: str = ""
    object_uri: str = ""
    sha256: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=_utcnow)


class DifferentialResult(StrictModel):
    differential_id: str = Field(default_factory=lambda: _new_id("diff"))
    experiment_id: str = Field(min_length=1)
    protein_id: str = Field(min_length=1)
    case_group_id: str = Field(min_length=1)
    control_group_id: str = Field(min_length=1)
    log2fc: float
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0)
    direction: DifferentialDirection
    is_differential: bool
    meta: dict[str, Any] = Field(default_factory=dict)


class EnrichmentRecord(StrictModel):
    """一条富集结果（集合层统计结论，区别于单实体 MetaAnnotation）。

    保存 study/background 集合 checksum 与基因集来源版本，使结果可复现、可审计。
    """

    enrichment_id: str = Field(default_factory=lambda: _new_id("enr"))
    experiment_id: str = Field(min_length=1)
    term: str = Field(min_length=1)  # disease_id / pathway_id
    term_name: str = ""
    term_type: str = "disease"
    overlap: int = Field(ge=0)
    study_size: int = Field(ge=0)
    background_size: int = Field(ge=0)
    term_size: int = Field(ge=0)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0)
    fold_enrichment: float = Field(ge=0.0)
    is_significant: bool
    gene_set_source: str = ""
    gene_set_version: str = ""
    study_checksum: str = ""
    background_checksum: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class MetaAnnotation(StrictModel):
    annotation_id: str = Field(default_factory=lambda: _new_id("ann"))
    experiment_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    target_type: AnnotationTargetType
    attribute: str = Field(min_length=1)
    value: Any
    evidence_level: EvidenceLevel
    source: str = Field(min_length=1)
    derivation: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class AnnotationHistory(StrictModel):
    history_id: str = Field(default_factory=lambda: _new_id("ah"))
    annotation_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    from_level: EvidenceLevel | None = None
    to_level: EvidenceLevel
    verdict: str = Field(min_length=1)
    evidence_ref: dict[str, Any] = Field(default_factory=dict)
    changed_at: datetime = Field(default_factory=_utcnow)


class ExperimentSnapshot(StrictModel):
    snapshot_id: str = Field(default_factory=lambda: _new_id("snap"))
    experiment_id: str = Field(min_length=1)
    snapshot_version: str = Field(min_length=1)
    status: ExperimentStatus = ExperimentStatus.FINAL
    general_kg_version: dict[str, str] = Field(default_factory=dict)
    pipeline_version: str = Field(min_length=1)
    model_version: str | None = None
    query_and_params: dict[str, Any] = Field(default_factory=dict)
    frozen_at: datetime = Field(default_factory=_utcnow)
    checksum: str = Field(min_length=1)
    report_artifact_ref: str = ""
    request_id: str | None = None
    request_version: int | None = Field(default=None, ge=1)
    request_content_hash: str | None = None
    input_artifact_hashes: list[str] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)  # 冻结时的内容清单（读回/校验用）

    @model_validator(mode="after")
    def _must_be_archived_state(self) -> "ExperimentSnapshot":
        if self.status is ExperimentStatus.WORKING:
            raise ValueError("experiment snapshot cannot have WORKING status")
        request_fields = (
            self.request_id,
            self.request_version,
            self.request_content_hash,
        )
        if any(value is not None for value in request_fields) and not all(
            value is not None for value in request_fields
        ):
            raise ValueError(
                "snapshot request_id, request_version and request_content_hash "
                "must be set together"
            )
        return self


class ReportRecord(StrictModel):
    """落库的报告 artifact：绑定冻结快照，存内容 + checksum，可审计、可回取。

    报告是冻结快照的确定性渲染（§10/L6），故 ``report_id`` 由 ``snapshot_id`` 派生、
    按 ``(experiment_id, snapshot_version)`` 幂等 upsert：重复生成不产生新行。

    ``str_strip_whitespace=False``：``content`` 必须**逐字节存原文**，否则 strip 掉
    尾随换行会让 ``sha256(content) != checksum``，破坏 artifact 自洽性。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    report_id: str = Field(default_factory=lambda: _new_id("report"))
    experiment_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    snapshot_version: str = Field(min_length=1)
    report_format: str = "markdown"
    checksum: str = Field(min_length=1)  # content 的 SHA-256
    content: str
    sections: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    meta: dict[str, Any] = Field(default_factory=dict)


class ExperimentBundle(StrictModel):
    """输入三件套的结构化表示，并验证全部跨表引用。"""

    context: ExperimentContext
    groups: list[ExperimentGroup] = Field(min_length=1)
    peptides: list[PeptideRecord] = Field(default_factory=list)
    proteins: list[ProteinRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> "ExperimentBundle":
        group_ids = [g.group_id for g in self.groups]
        group_labels = [g.label for g in self.groups]
        protein_ids = [p.protein_id for p in self.proteins]
        peptide_ids = [p.peptide_id for p in self.peptides]

        for name, values in (
            ("group_id", group_ids),
            ("group label", group_labels),
            ("protein_id", protein_ids),
            ("peptide_id", peptide_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name} in experiment bundle")

        known_groups = set(group_labels)
        known_proteins = set(protein_ids)
        known_peptides = set(peptide_ids)
        peptide_owner = {p.peptide_id: p.protein_id for p in self.peptides}

        for peptide in self.peptides:
            if peptide.group_label not in known_groups:
                raise ValueError(
                    f"peptide {peptide.peptide_id} references unknown group label "
                    f"{peptide.group_label}"
                )
            if peptide.protein_id not in known_proteins:
                raise ValueError(
                    f"peptide {peptide.peptide_id} references unknown protein "
                    f"{peptide.protein_id}"
                )

        for protein in self.proteins:
            for peptide_id in protein.peptide_ids:
                if peptide_id not in known_peptides:
                    raise ValueError(
                        f"protein {protein.protein_id} references unknown peptide {peptide_id}"
                    )
                if peptide_owner[peptide_id] != protein.protein_id:
                    raise ValueError(
                        f"protein {protein.protein_id} does not own peptide {peptide_id}"
                    )
        return self


__all__ = [
    "AnnotationHistory",
    "AnnotationTargetType",
    "ContextConfirmationStatus",
    "DifferentialDirection",
    "DifferentialResult",
    "EnrichmentRecord",
    "EvidenceLevel",
    "ExperimentBundle",
    "ExperimentContext",
    "ExperimentContextRevision",
    "ExperimentGroup",
    "ExperimentInputArtifact",
    "ExperimentRequest",
    "ExperimentSnapshot",
    "ExperimentStatus",
    "GroupRole",
    "MetaAnnotation",
    "PeptideRecord",
    "ProteinQuantification",
    "ProteinRecord",
    "ReportRecord",
    "request_content_hash",
]
