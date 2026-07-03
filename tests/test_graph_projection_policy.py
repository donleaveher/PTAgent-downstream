from __future__ import annotations

from application.graph.projection_policy import (
    DEFAULT_PROJECTION_POLICY,
    ProjectionCandidate,
    ProjectionPolicy,
    ProjectionRule,
)


def test_default_structure_policy_projects_top_ranked_neighbors() -> None:
    decision = DEFAULT_PROJECTION_POLICY.decide(
        ProjectionCandidate(
            channel="structure",
            relation_type="STRUCTURAL_NEIGHBOR",
            rank=5,
            score=0.6,
            coverage=0.7,
            support_channels=("structure",),
        )
    )

    assert decision.projected is True
    assert decision.reason == "rank<=5"


def test_default_structure_policy_rejects_low_rank_neighbors() -> None:
    decision = DEFAULT_PROJECTION_POLICY.decide(
        ProjectionCandidate(
            channel="structure",
            relation_type="STRUCTURAL_NEIGHBOR",
            rank=6,
            score=0.99,
            coverage=0.99,
            support_channels=("structure",),
        )
    )

    assert decision.projected is False
    assert decision.reason == "rank>5"


def test_candidate_neighbor_policy_requires_fusion_rank_and_channel_support() -> None:
    decision = DEFAULT_PROJECTION_POLICY.decide(
        ProjectionCandidate(
            channel="fusion",
            relation_type="CANDIDATE_NEIGHBOR",
            fusion_rank=2,
            fused_score=0.2,
            support_channels=("sequence", "domain"),
        )
    )

    assert decision.projected is True
    assert decision.reason == "fusion_rank<=5;support_channels>=2"


def test_custom_policy_can_require_score_and_coverage() -> None:
    policy = ProjectionPolicy(
        rules={
            "STRUCTURAL_NEIGHBOR": ProjectionRule(
                relation_type="STRUCTURAL_NEIGHBOR",
                max_rank=5,
                min_score=0.8,
                min_coverage=0.5,
            )
        }
    )
    decision = policy.decide(
        ProjectionCandidate(
            channel="structure",
            relation_type="STRUCTURAL_NEIGHBOR",
            rank=1,
            score=0.7,
            coverage=0.9,
        )
    )

    assert decision.projected is False
    assert decision.reason == "score<0.8"
