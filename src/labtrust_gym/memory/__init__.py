"""
Memory hardening: authenticated writes, schema-limited content, TTL/decay, poison filtering.

MemoryStore: put(entry, writer_agent_id, signature, ttl); get(query, role_id) with filtering.
Validators: poison pattern detection, instruction-override detection.
"""

from labtrust_gym.memory.validators import (
    MEM_POISON_DETECTED,
    MEM_WRITE_SCHEMA_FAIL,
    check_instruction_override,
    check_poison,
    check_poison_and_instruction_override,
    filter_poison_from_entries,
    load_memory_policy,
    validate_entry_schema,
)
from labtrust_gym.memory.store import (
    MEM_RETRIEVAL_FILTERED,
    MEM_WRITE_UNAUTHENTICATED,
    MemoryStore,
    load_memory_policy_from_root,
)

__all__ = [
    "MEM_POISON_DETECTED",
    "MEM_WRITE_SCHEMA_FAIL",
    "MEM_WRITE_UNAUTHENTICATED",
    "MEM_RETRIEVAL_FILTERED",
    "check_poison",
    "check_instruction_override",
    "check_poison_and_instruction_override",
    "validate_entry_schema",
    "filter_poison_from_entries",
    "load_memory_policy",
    "MemoryStore",
    "load_memory_policy_from_root",
]
