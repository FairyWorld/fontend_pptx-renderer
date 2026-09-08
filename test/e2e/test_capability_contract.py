import json
from pathlib import Path

import pytest

from oracle.capability_contract import (
    capability_definition_fingerprint,
    load_acceptance_history,
    load_capability_registry,
    validate_acceptance_history,
)


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def capability(
    capability_id: str = "drawingml.shape.geometry.rect",
    *,
    render_mode: str = "fallback",
    fallback: str = "Render the existing flat 2D shape.",
    required_gates: list[str] | None = None,
) -> dict:
    return {
        "id": capability_id,
        "component": "shape",
        "renderMode": render_mode,
        "impact": "fidelity",
        "selectors": [
            {
                "partGlob": "ppt/slides/slide*.xml",
                "namespace": "http://schemas.openxmlformats.org/drawingml/2006/main",
                "localName": "prstGeom",
            }
        ],
        "scope": {"presets": ["rect"]},
        "fallback": fallback,
        "implementationPaths": ["src/shapes/presets.ts"],
        "requiredGates": required_gates or ["source", "unit", "browser", "docs"],
        "issueUrls": [],
    }


def test_registry_rejects_duplicate_capability_ids(tmp_path: Path):
    entry = capability("drawingml.shape.geometry.duplicate")
    path = write_json(
        tmp_path / "capabilities.json",
        {"schemaVersion": 1, "capabilities": [entry, entry]},
    )

    with pytest.raises(ValueError, match="duplicate capability id"):
        load_capability_registry(path)


def test_native_mode_requires_native_powerpoint_gate(tmp_path: Path):
    entry = capability(
        render_mode="native",
        fallback="none",
        required_gates=["source", "unit", "browser", "docs"],
    )
    path = write_json(
        tmp_path / "capabilities.json",
        {"schemaVersion": 1, "capabilities": [entry]},
    )

    with pytest.raises(ValueError, match="native-powerpoint"):
        load_capability_registry(path)


def test_non_native_mode_requires_a_fallback_description(tmp_path: Path):
    entry = capability(render_mode="approximate", fallback="")
    path = write_json(
        tmp_path / "capabilities.json",
        {"schemaVersion": 1, "capabilities": [entry]},
    )

    with pytest.raises(ValueError, match="fallback"):
        load_capability_registry(path)


def test_registry_rejects_unknown_keys_and_unsafe_paths(tmp_path: Path):
    entry = capability()
    entry["renderMdoe"] = entry["renderMode"]
    typo_path = write_json(
        tmp_path / "typo.json",
        {"schemaVersion": 1, "capabilities": [entry]},
    )
    with pytest.raises(ValueError, match="unknown keys.*renderMdoe"):
        load_capability_registry(typo_path)

    unsafe_entry = capability()
    unsafe_entry["implementationPaths"] = ["../outside.ts"]
    unsafe_path = write_json(
        tmp_path / "unsafe.json",
        {"schemaVersion": 1, "capabilities": [unsafe_entry]},
    )
    with pytest.raises(ValueError, match="repository-relative"):
        load_capability_registry(unsafe_path)


def test_acceptance_history_requires_known_capabilities_and_sha256(tmp_path: Path):
    registry_path = write_json(
        tmp_path / "capabilities.json",
        {"schemaVersion": 1, "capabilities": [capability()]},
    )
    registry = load_capability_registry(registry_path)

    unknown_path = write_json(
        tmp_path / "unknown-acceptance.json",
        {
            "schemaVersion": 1,
            "receipts": [
                {
                    "capabilityId": "drawingml.shape.geometry.unknown",
                    "definitionFingerprint": "d" * 64,
                    "acceptedRevision": "a" * 40,
                    "implementationFingerprint": "b" * 64,
                    "caseIds": ["oracle-shape-0001"],
                    "caseInputFingerprints": ["c" * 64],
                    "gates": ["source", "unit"],
                    "environment": {"oracle": "powerpoint-macos"},
                    "acceptedAt": "2026-09-09T00:00:00Z",
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="unknown capability"):
        validate_acceptance_history(registry, load_acceptance_history(unknown_path))

    invalid_hash_path = write_json(
        tmp_path / "invalid-hash-acceptance.json",
        {
            "schemaVersion": 1,
            "receipts": [
                {
                    "capabilityId": "drawingml.shape.geometry.rect",
                    "definitionFingerprint": "d" * 64,
                    "acceptedRevision": "a" * 40,
                    "implementationFingerprint": "not-a-sha256",
                    "caseIds": ["oracle-shape-0001"],
                    "caseInputFingerprints": ["c" * 64],
                    "gates": ["source", "unit"],
                    "environment": {"oracle": "powerpoint-macos"},
                    "acceptedAt": "2026-09-09T00:00:00Z",
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="implementationFingerprint"):
        load_acceptance_history(invalid_hash_path)


def test_valid_registry_and_acceptance_history_are_immutable(tmp_path: Path):
    entry = capability(
        render_mode="native",
        fallback="none",
        required_gates=["source", "unit", "browser", "native-powerpoint", "docs"],
    )
    registry = load_capability_registry(
        write_json(
            tmp_path / "capabilities.json",
            {"schemaVersion": 1, "capabilities": [entry]},
        )
    )
    history = load_acceptance_history(
        write_json(
            tmp_path / "capability-acceptance.json",
            {
                "schemaVersion": 1,
                "receipts": [
                    {
                        "capabilityId": entry["id"],
                        "definitionFingerprint": capability_definition_fingerprint(
                            registry.capabilities[0]
                        ),
                        "acceptedRevision": "a" * 40,
                        "implementationFingerprint": "b" * 64,
                        "caseIds": ["oracle-shape-0001"],
                        "caseInputFingerprints": ["c" * 64],
                        "gates": entry["requiredGates"],
                        "environment": {"oracle": "powerpoint-macos"},
                        "acceptedAt": "2026-09-09T00:00:00Z",
                    }
                ],
            },
        )
    )

    validate_acceptance_history(registry, history)
    assert registry.capabilities[0].scope == {"presets": ("rect",)}
    assert history.receipts[0].case_ids == ("oracle-shape-0001",)
    with pytest.raises(AttributeError):
        registry.capabilities[0].id = "changed"  # type: ignore[misc]


def test_tracked_capability_contract_is_valid():
    registry = load_capability_registry(Path("oracle/capabilities.json"))
    history = load_acceptance_history(Path("oracle/capability-acceptance.json"))

    validate_acceptance_history(registry, history)
    assert len(registry.capabilities) == 12
