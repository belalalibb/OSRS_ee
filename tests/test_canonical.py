"""Canonicalization is deterministic and rejects ambiguous input (idempotency basis)."""
import unittest

from osrs_ee import canonical


class Canonical(unittest.TestCase):
    def test_key_order_independent(self):
        self.assertEqual(canonical.content_hash({"b": 1, "a": {"y": 2, "x": 1}}), canonical.content_hash({"a": {"x": 1, "y": 2}, "b": 1}))

    def test_whitespace_free_and_sorted(self):
        self.assertEqual(canonical.canonical_bytes({"b": [1, 2], "a": "ü"}), '{"a":"ü","b":[1,2]}'.encode("utf-8"))

    def test_value_change_changes_hash(self):
        self.assertNotEqual(canonical.content_hash({"q": 1}), canonical.content_hash({"q": 2}))

    def test_bool_and_int_differ(self):
        self.assertNotEqual(canonical.content_hash({"q": 1}), canonical.content_hash({"q": True}))

    def test_rejects_nan_and_non_string_keys_and_objects(self):
        for bad in ({"a": float("nan")}, {1: "x"}, {"a": object()}, {"a": {"b": float("inf")}}):
            with self.assertRaises(canonical.CanonicalizationError):
                canonical.canonical_bytes(bad)

    def test_hash_is_sha256_hex(self):
        h = canonical.content_hash({})
        self.assertEqual(len(h), 64)
        self.assertEqual(h, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
