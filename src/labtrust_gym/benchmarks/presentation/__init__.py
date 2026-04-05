"""Benchmark run presentation: analytics and pipeline helpers for HTML reports."""

from __future__ import annotations

from labtrust_gym.benchmarks.presentation.pipeline import (
    BENCHMARK_BUNDLE_SCHEMA_VERSION,
    build_presentation_manifest,
    compute_run_analytics,
    default_report_out_dir,
    first_git_sha_from_rows,
    load_run_meta,
    load_run_summary,
    write_methods_matrix_csv,
)

__all__ = [
    "BENCHMARK_BUNDLE_SCHEMA_VERSION",
    "build_presentation_manifest",
    "compute_run_analytics",
    "default_report_out_dir",
    "first_git_sha_from_rows",
    "load_run_meta",
    "load_run_summary",
    "write_methods_matrix_csv",
]
