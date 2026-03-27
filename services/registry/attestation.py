from __future__ import annotations

import hashlib


def system_prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()


def verify_hash(expected: str, provided: str) -> bool:
    return expected == provided

