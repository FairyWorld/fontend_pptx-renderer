import json
import subprocess
from pathlib import Path

import pytest

from oracle.capability_contract import (
    PromotionReceipt,
    capability_definition_fingerprint,
    load_capability_registry,
)
from oracle.capability_evidence import (
    CapabilityEvidenceError,
    build_promotion_receipt,
    compute_implementation_fingerprint,
    compute_implementation_fingerprint_at_revision,
    compute_verification_fingerprint,
    compute_verification_fingerprint_at_revision,
    evaluate_evidence_state,
    sanitize_receipt_for_tracking,
)


SOURCE_HASH = "c" * 64
GROUND_TRUTH_HASH = "d" * 64


def build_repo_fixture(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    for relative_path, contents in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return repo


def load_capability(tmp_path: Path):
    payload = {
        "schemaVersion": 2,
        "capabilities": [
            {
                "id": "drawingml.shape.geometry.rect",
                "component": "shape",
                "renderMode": "native",
                "impact": "fidelity",
                "selectors": [],
                "scope": {"presets": ["rect"]},
                "fallback": "none",
                "implementationPaths": ["src/renderer/ShapeRenderer.ts"],
                "verificationPaths": [
                    "test/unit/renderer/ShapeRenderer.test.ts",
                ],
                "requiredGates": [
                    "source",
                    "structural",
                    "unit",
                    "browser",
                    "native-powerpoint",
                    "manual-visual",
                    "docs",
                ],
                "issueUrls": [],
            }
        ],
    }
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_capability_registry(path).capabilities[0]


def fresh_native_report(
    capability,
    implementation_fingerprint: str,
    verification_fingerprint: str,
) -> dict:
    return {
        "schemaVersion": 2,
        "capabilityId": capability.id,
        "definitionFingerprint": capability_definition_fingerprint(capability),
        "renderer": {
            "revision": "a" * 40,
            "dirty": False,
            "implementationFingerprint": implementation_fingerprint,
            "verificationFingerprint": verification_fingerprint,
        },
        "environment": {
            "oracle": "powerpoint-macos",
            "browser": {"name": "chromium", "version": "140"},
        },
        "gates": {gate: "passed" for gate in capability.required_gates},
        "caseResults": [
            {
                "caseId": "oracle-shape-0001",
                "sourceSha256": SOURCE_HASH,
                "groundTruthSha256": GROUND_TRUTH_HASH,
                "skipped": False,
                "passed": True,
                "needsReview": False,
                "manualVerdict": "not-required",
                "runtimeErrors": [],
            }
        ],
    }


def accepted_receipt(
    capability,
    implementation_fingerprint: str,
    verification_fingerprint: str,
) -> PromotionReceipt:
    return PromotionReceipt(
        capability_id=capability.id,
        definition_fingerprint=capability_definition_fingerprint(capability),
        accepted_revision="a" * 40,
        implementation_fingerprint=implementation_fingerprint,
        verification_fingerprint=verification_fingerprint,
        case_ids=("oracle-shape-0001",),
        case_input_fingerprints=(SOURCE_HASH,),
        ground_truth_fingerprints=(GROUND_TRUTH_HASH,),
        gates=capability.required_gates,
        environment={"oracle": "powerpoint-macos"},
        accepted_at="2026-09-09T00:00:00Z",
    )


@pytest.fixture
def evidence_fixture(tmp_path: Path):
    capability = load_capability(tmp_path)
    repo = build_repo_fixture(
        tmp_path,
        {
            "src/renderer/ShapeRenderer.ts": "renderer",
            "test/unit/renderer/ShapeRenderer.test.ts": "test",
            "docs/README.md": "unrelated",
        },
    )
    implementation_fingerprint = compute_implementation_fingerprint(
        repo, capability.implementation_paths
    )
    verification_fingerprint = compute_verification_fingerprint(
        repo, capability.verification_paths
    )
    return capability, repo, implementation_fingerprint, verification_fingerprint


def test_matching_receipt_and_fresh_evidence_yield_verified(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture

    state = evaluate_evidence_state(
        capability,
        accepted_receipt(capability, implementation_fingerprint, verification_fingerprint),
        fresh_native_report(capability, implementation_fingerprint, verification_fingerprint),
        repo,
    )

    assert state.name == "verified"
    assert state.reasons == ()


def test_relevant_file_change_invalidates_accepted_receipt(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    receipt = accepted_receipt(capability, implementation_fingerprint, verification_fingerprint)
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    (repo / "src/renderer/ShapeRenderer.ts").write_text("changed", encoding="utf-8")

    state = evaluate_evidence_state(capability, receipt, report, repo)

    assert state.name == "regressed"
    assert state.reasons == ("evidence:implementation-fingerprint-drift",)


def test_verification_file_change_invalidates_accepted_receipt(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    receipt = accepted_receipt(capability, implementation_fingerprint, verification_fingerprint)
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    (repo / "test/unit/renderer/ShapeRenderer.test.ts").write_text(
        "changed test", encoding="utf-8"
    )

    state = evaluate_evidence_state(capability, receipt, report, repo)

    assert state.name == "regressed"
    assert state.reasons == ("evidence:verification-fingerprint-drift",)


def test_revision_fingerprints_compare_the_same_path_sets_and_fail_closed(
    evidence_fixture,
):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert compute_implementation_fingerprint_at_revision(
        repo, capability.implementation_paths, revision
    ) == implementation_fingerprint
    assert compute_verification_fingerprint_at_revision(
        repo, capability.verification_paths, revision
    ) == verification_fingerprint

    (repo / "test/unit/renderer/ShapeRenderer.test.ts").write_text(
        "changed", encoding="utf-8"
    )
    assert compute_implementation_fingerprint_at_revision(
        repo, capability.implementation_paths, revision
    ) == compute_implementation_fingerprint(repo, capability.implementation_paths)
    assert compute_verification_fingerprint_at_revision(
        repo, capability.verification_paths, revision
    ) != compute_verification_fingerprint(repo, capability.verification_paths)

    with pytest.raises(CapabilityEvidenceError, match="Git revision cannot be read"):
        compute_verification_fingerprint_at_revision(
            repo, capability.verification_paths, "0" * 40
        )


def test_unrelated_file_change_keeps_receipt_fresh(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    receipt = accepted_receipt(capability, implementation_fingerprint, verification_fingerprint)
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    (repo / "docs/README.md").write_text("changed", encoding="utf-8")

    state = evaluate_evidence_state(capability, receipt, report, repo)

    assert state.name == "verified"


def test_dirty_report_cannot_be_promoted(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    report["renderer"]["dirty"] = True

    state = evaluate_evidence_state(capability, None, report, repo)

    assert state.name == "candidate"
    assert state.reasons == ("evidence:dirty-worktree", "evidence:missing-promotion-receipt")


def test_missing_input_hash_stops_at_reproducible(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    report["caseResults"][0].pop("sourceSha256")

    state = evaluate_evidence_state(capability, None, report, repo)

    assert state.name == "reproducible"
    assert state.reasons == ("evidence:missing-input-hash",)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda report: report["caseResults"][0].update(skipped=True),
            "evidence:skipped-required-case",
        ),
        (
            lambda report: report["gates"].update(structural="failed"),
            "gate:structural:failed",
        ),
        (
            lambda report: report["caseResults"][0].update(
                needsReview=True,
                manualVerdict=None,
            ),
            "evidence:manual-review-required",
        ),
    ],
)
def test_required_verification_failures_prevent_promotion(evidence_fixture, mutate, reason):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    mutate(report)

    state = evaluate_evidence_state(capability, None, report, repo)

    assert state.name == "candidate"
    assert reason in state.reasons


def test_build_and_sanitize_promotion_receipt(evidence_fixture):
    capability, repo, implementation_fingerprint, verification_fingerprint = evidence_fixture
    report = fresh_native_report(capability, implementation_fingerprint, verification_fingerprint)
    report["environment"]["privateCasePath"] = "/Users/example/private/source.pptx"
    report["environment"]["username"] = "example"
    report["environment"]["windowsPath"] = "C:\\Users\\example\\source.pptx"

    receipt = build_promotion_receipt(capability, report, repo, "2026-09-09T01:02:03Z")
    tracked = sanitize_receipt_for_tracking(receipt)

    assert receipt.implementation_fingerprint == implementation_fingerprint
    assert receipt.verification_fingerprint == verification_fingerprint
    assert tracked["verificationFingerprint"] == verification_fingerprint
    assert tracked["caseIds"] == ["oracle-shape-0001"]
    assert tracked["caseInputFingerprints"] == [SOURCE_HASH]
    assert tracked["groundTruthFingerprints"] == [GROUND_TRUTH_HASH]
    assert "privateCasePath" not in json.dumps(tracked)
    assert "/Users/example" not in json.dumps(tracked)
    assert "C:\\\\Users" not in json.dumps(tracked)
