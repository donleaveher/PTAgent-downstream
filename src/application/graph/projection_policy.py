"""Projection policy for deciding which evidence becomes visible KG edges.

Retrieval and fusion can keep many candidates in MySQL. The graph should only
materialize high-signal relations that are useful for traversal.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectionCandidate:
    channel: str
    relation_type: str
    rank: int | None = None
    score: float | None = None
    coverage: float | None = None
    fusion_rank: int | None = None
    fused_score: float | None = None
    support_channels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectionRule:
    relation_type: str
    max_rank: int | None = None
    min_score: float | None = None
    min_coverage: float | None = None
    max_fusion_rank: int | None = None
    min_fused_score: float | None = None
    min_support_channels: int | None = None


@dataclass(frozen=True)
class ProjectionDecision:
    projected: bool
    reason: str
    relation_type: str


@dataclass(frozen=True)
class ProjectionPolicy:
    rules: dict[str, ProjectionRule] = field(default_factory=dict)

    def decide(self, candidate: ProjectionCandidate) -> ProjectionDecision:
        rule = self.rules.get(candidate.relation_type)
        if rule is None:
            return ProjectionDecision(
                projected=False,
                reason="no_projection_rule",
                relation_type=candidate.relation_type,
            )

        failures: list[str] = []
        passes: list[str] = []

        _check_max_int(
            "rank", candidate.rank, rule.max_rank, failures=failures, passes=passes
        )
        _check_min_float(
            "score", candidate.score, rule.min_score, failures=failures, passes=passes
        )
        _check_min_float(
            "coverage",
            candidate.coverage,
            rule.min_coverage,
            failures=failures,
            passes=passes,
        )
        _check_max_int(
            "fusion_rank",
            candidate.fusion_rank,
            rule.max_fusion_rank,
            failures=failures,
            passes=passes,
        )
        _check_min_float(
            "fused_score",
            candidate.fused_score,
            rule.min_fused_score,
            failures=failures,
            passes=passes,
        )
        if rule.min_support_channels is not None:
            count = len(set(candidate.support_channels))
            if count < rule.min_support_channels:
                failures.append(f"support_channels<{rule.min_support_channels}")
            else:
                passes.append(f"support_channels>={rule.min_support_channels}")

        if failures:
            return ProjectionDecision(
                projected=False,
                reason=";".join(failures),
                relation_type=candidate.relation_type,
            )
        return ProjectionDecision(
            projected=True,
            reason=";".join(passes) if passes else "projected_by_rule",
            relation_type=candidate.relation_type,
        )


def _check_max_int(
    name: str,
    value: int | None,
    limit: int | None,
    *,
    failures: list[str],
    passes: list[str],
) -> None:
    if limit is None:
        return
    if value is None:
        failures.append(f"{name}_missing")
    elif value > limit:
        failures.append(f"{name}>{limit}")
    else:
        passes.append(f"{name}<={limit}")


def _check_min_float(
    name: str,
    value: float | None,
    limit: float | None,
    *,
    failures: list[str],
    passes: list[str],
) -> None:
    if limit is None:
        return
    if value is None:
        failures.append(f"{name}_missing")
    elif value < limit:
        failures.append(f"{name}<{limit:g}")
    else:
        passes.append(f"{name}>={limit:g}")


DEFAULT_PROJECTION_POLICY = ProjectionPolicy(
    rules={
        "STRUCTURAL_NEIGHBOR": ProjectionRule(
            relation_type="STRUCTURAL_NEIGHBOR",
            max_rank=5,
        ),
        "CANDIDATE_NEIGHBOR": ProjectionRule(
            relation_type="CANDIDATE_NEIGHBOR",
            max_fusion_rank=5,
            min_support_channels=2,
        ),
    }
)


__all__ = [
    "DEFAULT_PROJECTION_POLICY",
    "ProjectionCandidate",
    "ProjectionDecision",
    "ProjectionPolicy",
    "ProjectionRule",
]
