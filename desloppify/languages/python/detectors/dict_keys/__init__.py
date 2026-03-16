"""Dict key flow analysis — detect dead writes, phantom reads, typos, and schema drift."""

from __future__ import annotations

from .shared import TrackedDict

__all__ = [
    "TrackedDict",
    "detect_dict_key_flow",
    "detect_schema_drift",
]
