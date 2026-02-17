## Coordination matrix (v0.1)

Produced by: (1) `labtrust build-coordination-matrix --run <run_dir> --out <run_dir>` or `labtrust run-coordination-study --spec <spec> --out <out_dir> --llm-backend openai_live --emit-coordination-matrix`; (2) or from the coordination security pack when `labtrust package-release --profile paper_v0.1 --include-coordination-pack` is used (build-lab-coordination-report with include_matrix=True writes coordination_matrix.v0.1.json under _coordination_pack/).

Pipeline mode: llm_live for study runs; pack mode for --include-coordination-pack. Model ID and backend come from the run when applicable; see matrix JSON `spec.scope.allowed_llm_backends` and row `run_meta.llm_model_id`.
