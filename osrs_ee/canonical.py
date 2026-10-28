"""Canonical JSON and content hashing. Idempotency = (command_id, hash of
canonical payload): same id+hash -> replay stored result; same id, different
hash -> reject. Canonical form: UTF-8, keys sorted by code point at every
level, separators ',' ':' with no whitespace, ensure_ascii=False, no NaN/Inf."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class CanonicalizationError(ValueError):
    pass


def _check(node: Any, path: str = "$") -> None:
    if isinstance(node, bool) or node is None or isinstance(node, (str, int)):
        return
    if isinstance(node, float):
        if math.isnan(node) or math.isinf(node):
            raise CanonicalizationError(f"{path}: non-finite float")
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"{path}: non-string key {k!r}")
            _check(v, f"{path}.{k}")
        return
    if isinstance(node, list):
        for i, v in enumerate(node):
            _check(v, f"{path}[{i}]")
        return
    raise CanonicalizationError(f"{path}: unsupported type {type(node).__name__}")


def canonical_bytes(document: Any) -> bytes:
    _check(document)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(document: Any) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()
