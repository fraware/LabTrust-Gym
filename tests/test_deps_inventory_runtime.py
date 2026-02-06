"""
Runtime dependency inventory (deps_inventory_runtime.json): schema validation,
stable keys, no secrets, no filesystem path leakage.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from labtrust_gym.security.deps_inventory import (
    collect_runtime_deps,
    write_deps_inventory_runtime,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _schema_path() -> Path:
    return _repo_root() / "policy" / "schemas" / "deps_inventory_runtime.v0.1.schema.json"


def _validate_against_schema(data: dict) -> list[str]:
    """Validate data against deps_inventory_runtime.v0.1 schema; return list of error messages."""
    schema_path = _schema_path()
    if not schema_path.exists():
        return [f"Schema not found: {schema_path}"]
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema required for validation"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=data, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e)]


def test_deps_inventory_runtime_schema_valid() -> None:
    """Collected runtime inventory validates against deps_inventory_runtime.v0.1.schema.json."""
    repo_root = _repo_root()
    data = collect_runtime_deps(repo_root=repo_root)
    errors = _validate_against_schema(data)
    assert not errors, f"Schema validation failed: {errors}"


def test_deps_inventory_runtime_stable_keys() -> None:
    """Runtime inventory has required stable keys: version, python_version, platform, packages."""
    data = collect_runtime_deps(repo_root=_repo_root())
    assert data.get("version") == "0.1"
    assert "python_version" in data
    assert "platform" in data
    assert "packages" in data
    assert isinstance(data["packages"], list)
    for pkg in data["packages"]:
        assert "name" in pkg
        assert "version" in pkg
        assert isinstance(pkg["name"], str)
        assert isinstance(pkg["version"], str)


def test_deps_inventory_runtime_no_secrets() -> None:
    """Runtime inventory must not leak secrets: only version, python_version, platform, packages (name/version)."""
    data = collect_runtime_deps(repo_root=_repo_root())
    allowed_top = {"version", "python_version", "platform", "pyproject_toml_sha256", "packages"}
    assert set(data.keys()) <= allowed_top, "Only allowed top-level keys"
    for pkg in data.get("packages", []):
        assert set(pkg.keys()) <= {"name", "version"}, "Package entries only name/version"


def test_deps_inventory_runtime_no_absolute_paths() -> None:
    """Runtime inventory must not leak absolute filesystem paths (e.g. home dirs)."""
    data = collect_runtime_deps(repo_root=_repo_root())
    raw = json.dumps(data)
    # No Windows or Unix absolute path patterns in string form
    assert "\\\\" not in raw or "\\\\" not in raw.replace("\\\\", "")
    # No /home/ or /Users/ or C:\ style paths
    path_indicators = ("/home/", "/Users/", "C:\\", ":\\")
    for indicator in path_indicators:
        assert indicator not in raw, f"Inventory must not contain absolute path: {indicator!r}"


def test_write_deps_inventory_runtime_creates_file() -> None:
    """write_deps_inventory_runtime creates SECURITY/deps_inventory_runtime.json."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        repo_root = _repo_root()
        path = write_deps_inventory_runtime(out_dir, repo_root=repo_root)
        assert path == out_dir / "SECURITY" / "deps_inventory_runtime.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = _validate_against_schema(data)
        assert not errors, f"Written file must validate: {errors}"


def test_deps_inventory_runtime_package_entries_normalized() -> None:
    """Package names in inventory are normalized (no leading/trailing whitespace)."""
    data = collect_runtime_deps(repo_root=_repo_root())
    for pkg in data["packages"]:
        name = pkg["name"]
        assert name == name.strip(), "Package name must be stripped"
        assert "  " not in name, "Package name must not contain double spaces"
