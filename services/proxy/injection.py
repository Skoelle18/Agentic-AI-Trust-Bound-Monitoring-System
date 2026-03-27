from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class InjectionFinding:
    category: str
    pattern: str
    snippet: str


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("identity_override", re.compile(r"\b(you are now|act as|pretend to be)\b", re.I)),
    ("instruction_override", re.compile(r"\b(ignore previous instructions|disregard|forget)\b", re.I)),
    ("extraction", re.compile(r"\b(reveal your system prompt|print your instructions)\b", re.I)),
    ("jailbreak", re.compile(r"\b(DAN mode|developer mode enabled|jailbreak)\b", re.I)),
    ("delimiter_injection", re.compile(r"(\[\[.*?instructions.*?\]\]|<\|system\|>)", re.I | re.S)),
]


def _scan_str(s: str) -> Optional[InjectionFinding]:
    for category, pat in PATTERNS:
        m = pat.search(s)
        if m:
            snippet = s[max(0, m.start() - 40) : min(len(s), m.end() + 40)]
            return InjectionFinding(category=category, pattern=pat.pattern, snippet=snippet)
    return None


def scan(obj: Any) -> Optional[InjectionFinding]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return _scan_str(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            f = scan(v)
            if f:
                return f
        return None
    if isinstance(obj, list):
        for v in obj:
            f = scan(v)
            if f:
                return f
        return None
    return None


def strip_injection(obj: Any) -> Any:
    if isinstance(obj, str):
        out = obj
        for _, pat in PATTERNS:
            out = pat.sub("[stripped]", out)
        return out
    if isinstance(obj, dict):
        return {k: strip_injection(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_injection(v) for v in obj]
    return obj

