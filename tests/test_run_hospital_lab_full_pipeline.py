"""
Regression tests for scripts/run_hospital_lab_full_pipeline.py (import smoke and shared helpers).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_run_hospital_lab_full_pipeline_script_imports() -> None:
    """Ensure the pipeline script is syntactically valid and exposes main()."""
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "run_hospital_lab_full_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_hospital_lab_full_pipeline", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(getattr(mod, "main", None))
