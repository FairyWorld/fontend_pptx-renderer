from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from oracle.capability_contract import (
    IMPACTS,
    RENDER_MODES,
    CapabilityDefinition,
    CapabilityRegistry,
)


IMPACT_ORDER = {
    "security": 0,
    "crash": 1,
    "missing": 2,
    "semantics": 3,
    "reliability": 4,
    "fidelity": 5,
    "enhancement": 6,
}
FAILURE_ORDER = {
    "runtime-error": 0,
    "deterministic-failure": 1,
    "native-failure": 2,
    "review-warning": 3,
    "none": 4,
}
EVIDENCE_STATES = frozenset(
    {"unknown", "observed", "reproducible", "candidate", "verified", "regressed", "blocked"}
)


@dataclass(frozen=True)
class LedgerRow:
    capability_id: str
    impact: str
    current_issue_count: int
    observed_unique_packages: int
    failure_kind: str
    oracle_ready: bool
    dependency_depth: int
    evidence_state: str
    render_mode: str
    blockers: tuple[str, ...]
    issue_urls: tuple[str, ...]


@dataclass(frozen=True)
class RankedCapability:
    row: LedgerRow
    priority_key: tuple[int, int, int, int, int, int, str]
    priority_labels: tuple[tuple[str, str], ...]

    @property
    def capability_id(self) -> str:
        return self.row.capability_id


def _validate_row(row: LedgerRow) -> None:
    if not row.capability_id:
        raise ValueError("ledger capability id must not be empty")
    if row.impact not in IMPACTS or row.impact not in IMPACT_ORDER:
        raise ValueError(f"unsupported impact: {row.impact}")
    if row.current_issue_count < 0 or row.observed_unique_packages < 0:
        raise ValueError("ledger counts must be non-negative")
    if row.failure_kind not in FAILURE_ORDER:
        raise ValueError(f"unsupported failure kind: {row.failure_kind}")
    if row.dependency_depth < 0:
        raise ValueError("dependency depth must be non-negative")
    if row.evidence_state not in EVIDENCE_STATES:
        raise ValueError(f"unsupported evidence state: {row.evidence_state}")
    if row.render_mode not in RENDER_MODES:
        raise ValueError(f"unsupported render mode: {row.render_mode}")
    if len(row.blockers) != len(set(row.blockers)):
        raise ValueError(f"duplicate blockers for {row.capability_id}")


def _ranked(row: LedgerRow) -> RankedCapability:
    priority_key = (
        IMPACT_ORDER[row.impact],
        -row.current_issue_count,
        -row.observed_unique_packages,
        FAILURE_ORDER[row.failure_kind],
        0 if row.oracle_ready else 1,
        row.dependency_depth,
        row.capability_id,
    )
    priority_labels = (
        ("impact", row.impact),
        ("currentIssueCount", str(row.current_issue_count)),
        ("observedUniquePackages", str(row.observed_unique_packages)),
        ("failureKind", row.failure_kind),
        ("oracleReady", str(row.oracle_ready).lower()),
        ("dependencyDepth", str(row.dependency_depth)),
        ("capabilityId", row.capability_id),
    )
    return RankedCapability(row=row, priority_key=priority_key, priority_labels=priority_labels)


def rank_capabilities(rows: list[LedgerRow] | tuple[LedgerRow, ...]) -> tuple[RankedCapability, ...]:
    seen: set[str] = set()
    ranked: list[RankedCapability] = []
    for row in rows:
        _validate_row(row)
        if row.capability_id in seen:
            raise ValueError(f"duplicate ledger capability: {row.capability_id}")
        seen.add(row.capability_id)
        ranked.append(_ranked(row))
    return tuple(sorted(ranked, key=lambda item: item.priority_key))


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _number_values(value: Any) -> tuple[float | int, ...]:
    if not isinstance(value, tuple):
        return ()
    return tuple(item for item in value if isinstance(item, (int, float)) and not isinstance(item, bool))


def _case_matrix(capability: CapabilityDefinition) -> dict[str, list[Any]]:
    matrix: dict[str, list[Any]] = {
        "semantics": ["positive-default", "explicit-override", "inverse-opt-out"],
        "rendering": ["source-model", "dom-svg", "browser", "native-powerpoint"],
        "regression": ["target-cohort", "neighbor-sentinels"],
    }
    if capability.component in {"shape", "chart", "text"}:
        matrix["aspectRatio"] = ["square", "wide", "tall"]
    scope = capability.scope
    bounds = _number_values(scope.get("bounds"))
    defaults = _number_values(scope.get("default"))
    if len(bounds) == 2:
        matrix["adjustment"] = list(dict.fromkeys((bounds[0], *defaults, bounds[1])))
    if capability.component == "shape":
        matrix["container"] = ["standalone", "grouped", "placeholder-parent"]
        matrix["paint"] = ["solid", "theme-style-reference"]
    if capability.id == "drawingml.shape.geometry.adjustment.donut":
        matrix["container"] = ["standalone", "grouped", "picture-clip-sentinel"]
    if ".3d." in capability.id:
        matrix["operations"] = ["malformed-input", "resource-bounds", "deterministic-disposal"]
    return {key: matrix[key] for key in sorted(matrix)}


def _commands_for(capability: CapabilityDefinition) -> list[str]:
    commands = ["pnpm capability:check"]
    gates = set(capability.required_gates)
    if "unit" in gates or "structural" in gates:
        commands.append("pnpm test")
    if "browser" in gates:
        commands.append("pnpm test:browser")
    if "typecheck" in gates or capability.component in {"shape", "chart", "text"}:
        commands.append("pnpm typecheck")
    if "package-size" in gates:
        commands.append("pnpm size")
    if "native-powerpoint" in gates:
        commands.append("Run the scoped native PowerPoint oracle with matching input hashes")
    if "manual-visual" in gates:
        commands.append("Review every needs-review row and localized diff image")
    return commands


def build_work_packet(
    selected: RankedCapability,
    registry: CapabilityRegistry,
) -> dict[str, Any]:
    capability = registry.by_id().get(selected.capability_id)
    if capability is None:
        raise ValueError(f"selected capability is not registered: {selected.capability_id}")
    row = selected.row
    return {
        "schemaVersion": 1,
        "capabilityId": capability.id,
        "component": capability.component,
        "currentRenderMode": row.render_mode,
        "evidenceState": row.evidence_state,
        "acceptedScope": _thaw(capability.scope),
        "fallback": capability.fallback,
        "observations": {
            "currentIssueCount": row.current_issue_count,
            "observedUniquePackages": row.observed_unique_packages,
            "failureKind": row.failure_kind,
            "oracleReady": row.oracle_ready,
            "dependencyDepth": row.dependency_depth,
        },
        "priority": {name: value for name, value in selected.priority_labels},
        "issueUrls": list(capability.issue_urls or row.issue_urls),
        "caseMatrix": _case_matrix(capability),
        "requiredGates": list(capability.required_gates),
        "requiredCommands": _commands_for(capability),
        "blockers": list(row.blockers),
        "rollbackConditions": [
            "native-oracle-cannot-reproduce-feature",
            "source-semantics-do-not-support-assumption",
            "accepted-neighbor-regresses",
            "undeclared-fallback-or-silent-content-loss",
            "resource-or-package-budget-regresses",
            "only-stale-or-aggregate-metrics-improve",
        ],
        "documentationPaths": [
            "README.md",
            "CHANGELOG.md",
            "docs/ARCHITECTURE.md",
            "docs/TESTING.md",
            "test/e2e/oracle/README.md",
            "test/e2e/oracle/capabilities.json",
        ],
    }
