"""
Reason codes and error semantics used inside the engine.

The full set of reason codes for holds, blocks, and audit is in policy/reason_codes.
This module defines the small set of codes used directly by the engine, such as
AUDIT_CHAIN_BROKEN for forensic freeze when the audit chain is invalid.
"""

# Audit log frozen (chain broken); all subsequent steps BLOCKED.
AUDIT_CHAIN_BROKEN = "AUDIT_CHAIN_BROKEN"

# Engine reason codes (canonical; policy/reason_codes holds full registry).
RC_INJECT_SPECIMEN_DUPLICATE = "RC_INJECT_SPECIMEN_DUPLICATE"
INV_TOK_001 = "INV-TOK-001"
