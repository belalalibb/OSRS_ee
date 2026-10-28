"""Strict JSON Schema (draft 2020-12) validation for OSRS_ee contracts.

Beyond the schema: booleans are explicitly rejected where numbers are
expected; schema_version is checked first so an unknown version yields one
explicit error; ``loads_strict`` rejects duplicate keys and NaN/Infinity.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "contracts" / "schemas"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})
CONTRACTS: Mapping[str, str] = {
    "SessionLaunch": "session_launch.schema.json",
    "Observation": "observation.schema.json",
    "CommandIntent": "command_intent.schema.json",
    "ResultEvent": "result_event.schema.json",
    "AIProposal": "ai_proposal.schema.json",
}
NUMERIC_KEYS = frozenset({
    "session_epoch", "state_version", "expected_state_version", "observed_state_version",
    "max_session_seconds", "drain_timeout_seconds", "policy_version", "confidence",
    "item_id", "quantity", "x", "y", "plane",
})


class ContractError(ValueError):
    def __init__(self, contract: str, errors: list[str]):
        self.contract, self.errors = contract, errors
        super().__init__(f"{contract}: " + "; ".join(errors))


@dataclass(frozen=True)
class ValidationReport:
    contract: str
    ok: bool
    errors: tuple[str, ...]


def _load_registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
    return registry


_REGISTRY = _load_registry()
_VALIDATORS: dict[str, Draft202012Validator] = {}


def _validator(contract: str) -> Draft202012Validator:
    if contract not in CONTRACTS:
        raise KeyError(f"unknown contract {contract!r}; known: {sorted(CONTRACTS)}")
    if contract not in _VALIDATORS:
        schema = json.loads((SCHEMA_DIR / CONTRACTS[contract]).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _VALIDATORS[contract] = Draft202012Validator(schema, registry=_REGISTRY)
    return _VALIDATORS[contract]


def _reject_bool_as_number(node: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            sub = f"{path}.{key}"
            if key in NUMERIC_KEYS and isinstance(value, bool):
                errors.append(f"{sub}: boolean is not an integer/number")
            errors.extend(_reject_bool_as_number(value, sub))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            errors.extend(_reject_bool_as_number(value, f"{path}[{i}]"))
    return errors


def _format(error: ValidationError) -> str:
    loc = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path)
    return f"{loc}: {error.message}"


def validate(contract: str, document: Any) -> ValidationReport:
    """Validate ``document`` against ``contract``. Never raises for invalid data."""
    validator = _validator(contract)
    if not isinstance(document, dict):
        return ValidationReport(contract, False, ("$: document must be a JSON object",))
    version = document.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        return ValidationReport(contract, False, (f"$.schema_version: unsupported or missing version {version!r}; supported {sorted(SUPPORTED_SCHEMA_VERSIONS)}",))
    errors = [_format(e) for e in sorted(validator.iter_errors(document), key=lambda e: [str(p) for p in e.absolute_path])]
    errors.extend(_reject_bool_as_number(document))
    seen: set[str] = set()
    unique = tuple(e for e in errors if not (e in seen or seen.add(e)))
    return ValidationReport(contract, not unique, unique)


def require_valid(contract: str, document: Any) -> dict:
    report = validate(contract, document)
    if not report.ok:
        raise ContractError(contract, list(report.errors))
    return document


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r} in JSON object")
        out[k] = v
    return out


def loads_strict(text: str) -> Any:
    """json.loads that rejects duplicate keys and NaN/Infinity."""
    def _reject(name: str) -> Any:
        raise ValueError(f"non-finite number {name} not allowed")
    return json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject)
