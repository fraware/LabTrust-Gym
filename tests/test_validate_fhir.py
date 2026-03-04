"""Tests for validate-fhir (8.3): terminology value set validation."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.export.fhir_terminology import validate_bundle_against_value_sets


def test_validate_fhir_valid_code_in_value_set() -> None:
    """Bundle with Observation code inside value set: no violations."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "#Observation/obs-1",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {"coding": [{"system": "urn:labtrust:test", "code": "panel1", "display": "Panel1"}]},
                },
            }
        ],
    }
    value_sets = {"urn:labtrust:test": ["panel1", "panel2"]}
    violations = validate_bundle_against_value_sets(bundle, value_sets)
    assert violations == []


def test_validate_fhir_invalid_code_outside_value_set() -> None:
    """Bundle with code not in value set: violation reported."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "#Observation/obs-1",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {"coding": [{"system": "urn:labtrust:test", "code": "invalid_code", "display": "X"}]},
                },
            }
        ],
    }
    value_sets = {"urn:labtrust:test": ["panel1"]}
    violations = validate_bundle_against_value_sets(bundle, value_sets)
    assert len(violations) == 1
    assert violations[0]["code"] == "invalid_code"
    assert violations[0]["resourceType"] == "Observation"
    assert violations[0]["id"] == "obs-1"


def test_validate_fhir_interpretation_codes() -> None:
    """Observation.interpretation codes validated against value set."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "#Observation/obs-1",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {"coding": [{"system": "urn:labtrust:test", "code": "panel1"}]},
                    "interpretation": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                    "code": "CR",
                                }
                            ]
                        }
                    ],
                },
            }
        ],
    }
    value_sets = {
        "urn:labtrust:test": ["panel1"],
        "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation": ["CR", "H", "L"],
    }
    violations = validate_bundle_against_value_sets(bundle, value_sets)
    assert violations == []


def test_validate_fhir_cli_valid_exit_zero(tmp_path: Path) -> None:
    """validate-fhir with valid bundle and terminology: exit 0."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "#Observation/obs-1",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {"coding": [{"system": "urn:labtrust:test", "code": "panel1"}]},
                },
            }
        ],
    }
    term = {"value_sets": {"urn:labtrust:test": ["panel1"]}}
    (tmp_path / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (tmp_path / "terminology.json").write_text(json.dumps(term, indent=2), encoding="utf-8")
    repo = Path(__file__).resolve().parent.parent
    import subprocess

    result = subprocess.run(
        [
            "python",
            "-m",
            "labtrust_gym.cli.main",
            "validate-fhir",
            "--bundle",
            str(tmp_path / "bundle.json"),
            "--terminology",
            str(tmp_path / "terminology.json"),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def test_validate_fhir_cli_invalid_strict_exit_nonzero(tmp_path: Path) -> None:
    """validate-fhir with invalid code and --strict: exit non-zero."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "#Observation/obs-1",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {"coding": [{"system": "urn:labtrust:test", "code": "bad_code"}]},
                },
            }
        ],
    }
    term = {"value_sets": {"urn:labtrust:test": ["panel1"]}}
    (tmp_path / "bundle2.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (tmp_path / "term2.json").write_text(json.dumps(term, indent=2), encoding="utf-8")
    repo = Path(__file__).resolve().parent.parent
    import subprocess

    result = subprocess.run(
        [
            "python",
            "-m",
            "labtrust_gym.cli.main",
            "validate-fhir",
            "--bundle",
            str(tmp_path / "bundle2.json"),
            "--terminology",
            str(tmp_path / "term2.json"),
            "--strict",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, (result.stdout or "") + (result.stderr or "")
    assert "bad_code" in result.stderr or "bad_code" in result.stdout
