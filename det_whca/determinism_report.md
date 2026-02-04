# Determinism report

- **Task**: TaskG_COORD_SCALE
- **Episodes**: 2
- **Seed**: 42
- **Partner**: (none)
- **Timing**: explicit
- **Coord method**: kernel_whca

## Result

**PASSED**

## Hashes (run1 vs run2)

- Episode log SHA-256: `ee031fd4bb708da3e25bbb5481de344e86c70f0dc7091c1cb1946189b7f53b64` vs `ee031fd4bb708da3e25bbb5481de344e86c70f0dc7091c1cb1946189b7f53b64` ✓
- Results canonical SHA-256: `33d2d8557f6e94c75e70bab971d47d4201e3955eed0d34f8119479e61676f31c` vs `33d2d8557f6e94c75e70bab971d47d4201e3955eed0d34f8119479e61676f31c` ✓
- v0.2 metrics canonical: identical ✓

- Receipts bundle root hash: `d659ce2b7e1df83b3ed354d76b7b98ed10950b00cb76570dc9cc2263fa1080d8` vs `d659ce2b7e1df83b3ed354d76b7b98ed10950b00cb76570dc9cc2263fa1080d8` ✓

When `timing=simulated`, device service-time sampling is seeded only from the provided seed (engine RNG per episode = base_seed + episode index).