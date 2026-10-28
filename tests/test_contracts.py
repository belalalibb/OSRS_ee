"""T20 (pure part): valid fixtures pass; every invalid fixture fails for the
reason encoded in its filename. Offline; no network, no client."""
from __future__ import annotations

import socket
import unittest
from pathlib import Path

from osrs_ee import contracts

FIXTURES = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"


class Harness(unittest.TestCase):
    def test_socket_is_blocked(self):
        with self.assertRaises(RuntimeError):
            socket.socket()


class SchemaSanity(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self):
        for contract in contracts.CONTRACTS:
            contracts._validator(contract)

    def test_unknown_contract_rejected(self):
        with self.assertRaises(KeyError):
            contracts.validate("Nope", {})

    def test_non_object_rejected(self):
        self.assertFalse(contracts.validate("AIProposal", []).ok)
        self.assertFalse(contracts.validate("AIProposal", "x").ok)


class ValidFixtures(unittest.TestCase):
    def test_every_valid_fixture_passes(self):
        count = 0
        for path in sorted((FIXTURES / "valid").rglob("*.json")):
            report = contracts.validate(path.parent.name, contracts.loads_strict(path.read_text(encoding="utf-8")))
            self.assertTrue(report.ok, f"{path.relative_to(FIXTURES)}: {report.errors}")
            count += 1
        self.assertEqual(count, 9)


class InvalidFixtures(unittest.TestCase):
    EXPECTED = {
        "unknown_version": "unsupported or missing version", "missing_lease": "'lease_id' is a required property",
        "extra_field": "Additional properties are not allowed", "epoch_zero": "less than the minimum",
        "epoch_bool": "boolean is not an integer", "secret_not_ref": "does not match", "remote_endpoint": "does not match",
        "seconds_zero": "less than the minimum", "bad_hash": "does not match", "bad_timestamp": "does not match",
        "id_is_pid": "does not match",
        "unknown_with_value": "is not of type 'null'", "known_with_null": "should not be valid under",
        "empty_fields": "should be non-empty", "unnamespaced_field": "does not match",
        "negative_state_version": "less than the minimum", "bad_consistency": "is not one of",
        "withdraw_missing_params": "is a required property", "withdraw_extra_param": "Additional properties are not allowed",
        "withdraw_zero_quantity": "less than the minimum", "noop_with_params": "Additional properties are not allowed",
        "walk_plane_4": "greater than the maximum", "unknown_operation": "is not one of",
        "quantity_bool": "boolean is not an integer", "state_version_bool": "boolean is not an integer",
        "policy_zero": "less than the minimum", "free_text_path": "is not of type 'boolean'",
        "not_sent_but_verified": "was expected", "verified_without_evidence": "should be non-empty",
        "timeout_not_attempted": "is not one of", "not_attempted_reason_none": "should not be valid under",
        "duplicate_evidence": "non-unique elements", "unknown_reason": "is not one of",
        "free_action": "is not one of", "with_parameters": "Additional properties are not allowed",
        "no_approval": "was expected", "confidence_over_1": "greater than the maximum",
        "confidence_bool": "boolean is not an integer", "extra_execute_field": "Additional properties are not allowed",
    }

    def test_every_invalid_fixture_fails_for_expected_reason(self):
        seen = set()
        for path in sorted((FIXTURES / "invalid").rglob("*.json")):
            report = contracts.validate(path.parent.name, contracts.loads_strict(path.read_text(encoding="utf-8")))
            self.assertFalse(report.ok, f"{path.relative_to(FIXTURES)} unexpectedly valid")
            expected = self.EXPECTED[path.stem]
            self.assertTrue(any(expected in e for e in report.errors), f"{path.relative_to(FIXTURES)}: expected {expected!r} in {report.errors}")
            seen.add(path.stem)
        self.assertEqual(seen, set(self.EXPECTED), "fixture set and expectation table drifted")

    def test_require_valid_raises(self):
        with self.assertRaises(contracts.ContractError) as cm:
            contracts.require_valid("AIProposal", {"schema_version": "1.0"})
        self.assertIn("AIProposal", str(cm.exception))


class StrictJson(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            contracts.loads_strict('{"a":1,"a":2}')

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            contracts.loads_strict('{"a":NaN}')

    def test_plain_json_accepted(self):
        self.assertEqual(contracts.loads_strict('{"a":[1,"x",null,true]}'), {"a": [1, "x", None, True]})
