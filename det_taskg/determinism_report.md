# Determinism report

- **Task**: TaskG_COORD_SCALE
- **Episodes**: 2
- **Seed**: 42
- **Partner**: (none)
- **Timing**: explicit
- **Coord method**: kernel_centralized_edf

## Result

**PASSED**

## Hashes (run1 vs run2)

- Episode log SHA-256: `5af042d6b8734e7e5dade66cda6393c1224a9797ad5c5593bbc73b2ade55f1eb` vs `5af042d6b8734e7e5dade66cda6393c1224a9797ad5c5593bbc73b2ade55f1eb` ✓
- Results canonical SHA-256: `7b075e7c39edf0496de43c3e23d65a33f21755ba8b41e8de7fe8b399ebe7b772` vs `7b075e7c39edf0496de43c3e23d65a33f21755ba8b41e8de7fe8b399ebe7b772` ✓
- v0.2 metrics canonical: identical ✓

- Receipts bundle root hash: `5317eb6bc0e2f9a881316f338200315a77f94be395fc656b976c398882387fca` vs `5317eb6bc0e2f9a881316f338200315a77f94be395fc656b976c398882387fca` ✓

When `timing=simulated`, device service-time sampling is seeded only from the provided seed (engine RNG per episode = base_seed + episode index).