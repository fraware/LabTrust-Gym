"""
Testing utilities: fuzz harness and metamorphic property support.

- fuzz: seeded event-sequence generation constrained by policy/tool schemas.
- Metamorphic tests live in tests/test_metamorphic_properties.py.
"""

from labtrust_gym.testing.fuzz import (
    run_fuzz_session,
    write_reproducer,
)

__all__ = [
    "run_fuzz_session",
    "write_reproducer",
]
