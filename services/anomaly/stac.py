from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


SEQUENCES: list[list[str]] = [
    ["list_directory", "read_file", "http_request"],
    ["run_query", "write_file", "http_request"],
    ["bash_exec", "read_file", "http_request"],
    ["read_file", "read_file", "read_file", "http_request"],
]


@dataclass
class STACResult:
    triggered: bool
    confidence: float
    detail: str
    matched: Optional[list[str]] = None


def check(window: list[str]) -> STACResult:
    for seq in SEQUENCES:
        n = len(seq)
        if len(window) >= n and window[-n:] == seq:
            conf = min(1.0, 0.6 + 0.1 * (n - 3))
            return STACResult(triggered=True, confidence=conf, detail="Matched dangerous tool chain", matched=seq)
    return STACResult(triggered=False, confidence=0.0, detail="ok", matched=None)

