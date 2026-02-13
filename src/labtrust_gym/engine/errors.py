"""
Engine-internal reason codes and error semantics.

Canonical reason codes for holds, blocks, and audit are in policy/reason_codes.
This module holds codes used directly by the engine (e.g. forensic freeze).
"""

# Audit log frozen (chain broken); all subsequent steps BLOCKED.
AUDIT_CHAIN_BROKEN = "AUDIT_CHAIN_BROKEN"

# Engine reason codes (canonical; policy/reason_codes holds full registry).
RC_INJECT_SPECIMEN_DUPLICATE = "RC_INJECT_SPECIMEN_DUPLICATE"
INV_TOK_001 = "INV-TOK-001"
