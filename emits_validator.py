from __future__ import annotations

from pathlib import Path
from typing import List, Set
import yaml


def load_emits_vocab(path: str) -> Set[str]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    vocab = data["emits_vocab"]["canonical_set"]
    return set(vocab)


def validate_emits(emits: List[str], allowed: Set[str], *, event_id: str) -> None:
    unknown = [e for e in emits if e not in allowed]
    if unknown:
        raise AssertionError(
            f"[{event_id}] unknown emits detected: {unknown} | allowed={sorted(list(allowed))}"
        )
