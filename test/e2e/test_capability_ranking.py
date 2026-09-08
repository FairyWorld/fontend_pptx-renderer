from pathlib import Path

import pytest

from oracle.capability_contract import load_capability_registry
from oracle.capability_ranking import (
    LedgerRow,
    build_work_packet,
    rank_capabilities,
)


def row(
    capability_id: str,
    *,
    impact: str = "fidelity",
    current_issues: int = 0,
    observed: int = 0,
    failure: str = "none",
    oracle_ready: bool = False,
    dependency_depth: int = 0,
    evidence_state: str = "observed",
    render_mode: str = "fallback",
    blockers: tuple[str, ...] = (),
) -> LedgerRow:
    return LedgerRow(
        capability_id=capability_id,
        impact=impact,
        current_issue_count=current_issues,
        observed_unique_packages=observed,
        failure_kind=failure,
        oracle_ready=oracle_ready,
        dependency_depth=dependency_depth,
        evidence_state=evidence_state,
        render_mode=render_mode,
        blockers=blockers,
        issue_urls=(),
    )


def test_missing_real_deck_feature_precedes_unobserved_enhancement():
    ranked = rank_capabilities(
        [
            row("presentation.animation.timing", impact="enhancement", observed=0),
            row("drawingml.shape.3d.top-bevel-contour", impact="missing", observed=3),
        ]
    )

    assert [item.capability_id for item in ranked] == [
        "drawingml.shape.3d.top-bevel-contour",
        "presentation.animation.timing",
    ]


def test_ranking_uses_documented_lexicographic_order():
    ranked = rank_capabilities(
        [
            row("cap.f", current_issues=1, observed=2, failure="review-warning"),
            row("cap.e", current_issues=1, observed=2, failure="native-failure"),
            row("cap.d", current_issues=1, observed=2, failure="runtime-error"),
            row("cap.c", current_issues=1, observed=3, failure="none"),
            row("cap.b", current_issues=2, observed=0, failure="none"),
            row("cap.a", impact="semantics", current_issues=0, observed=0),
        ]
    )

    assert [item.capability_id for item in ranked] == [
        "cap.a",
        "cap.b",
        "cap.c",
        "cap.d",
        "cap.e",
        "cap.f",
    ]
    assert ranked[1].priority_labels[:3] == (
        ("impact", "fidelity"),
        ("currentIssueCount", "2"),
        ("observedUniquePackages", "0"),
    )


def test_oracle_readiness_then_dependency_depth_then_id_break_ties():
    ranked = rank_capabilities(
        [
            row("cap.d", oracle_ready=False, dependency_depth=0),
            row("cap.c", oracle_ready=True, dependency_depth=2),
            row("cap.b", oracle_ready=True, dependency_depth=1),
            row("cap.a", oracle_ready=True, dependency_depth=1),
        ]
    )

    assert [item.capability_id for item in ranked] == ["cap.a", "cap.b", "cap.c", "cap.d"]


def test_ranking_rejects_invalid_or_duplicate_rows():
    with pytest.raises(ValueError, match="duplicate ledger capability"):
        rank_capabilities([row("cap.a"), row("cap.a")])
    with pytest.raises(ValueError, match="non-negative"):
        rank_capabilities([row("cap.a", observed=-1)])
    with pytest.raises(ValueError, match="failure kind"):
        rank_capabilities([row("cap.a", failure="mystery")])


def test_work_packet_contains_one_bounded_donut_matrix():
    registry = load_capability_registry(Path("oracle/capabilities.json"))
    selected = rank_capabilities(
        [
            row(
                "drawingml.shape.geometry.adjustment.donut",
                observed=2,
                failure="native-failure",
                oracle_ready=True,
                blockers=("refresh-current-native-report",),
            )
        ]
    )[0]

    packet = build_work_packet(selected, registry)

    assert packet["schemaVersion"] == 1
    assert packet["capabilityId"] == "drawingml.shape.geometry.adjustment.donut"
    assert packet["acceptedScope"]["bounds"] == [0, 50000]
    assert packet["caseMatrix"]["adjustment"] == [0, 25000, 50000]
    assert packet["caseMatrix"]["aspectRatio"] == ["square", "wide", "tall"]
    assert packet["caseMatrix"]["container"] == [
        "standalone",
        "grouped",
        "picture-clip-sentinel",
    ]
    assert packet["blockers"] == ["refresh-current-native-report"]
    assert packet["rollbackConditions"]
    assert packet["requiredGates"] == list(
        registry.by_id()[selected.capability_id].required_gates
    )
