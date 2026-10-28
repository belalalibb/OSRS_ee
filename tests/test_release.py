"""S08 release/cache/admission/network tests — pure parts of T14/T15/T18/T19/T32.
No I/O: hashes over in-memory bytes; measurements injected. Live canary is NOT modelled."""
from __future__ import annotations

import unittest
from datetime import timedelta

from osrs_ee import release as rl
from tests.test_store import T0

A = b"artifact-A-bytes"
B = b"artifact-B-bytes"
SHA_A, SHA_B = rl.sha256_hex(A), rl.sha256_hex(B)


def registry():
    r = rl.Registry()
    r.allow("plugin-a.jar", SHA_A, "MIT")
    return r


class RegistryTests(unittest.TestCase):
    def test_admit_only_reviewed_hash(self):
        r = registry()
        self.assertTrue(r.admit("plugin-a.jar", A, path="plugins/plugin-a.jar").allowed)
        d = r.admit("plugin-a.jar", B, path="plugins/plugin-a.jar")
        self.assertEqual((d.allowed, d.reason_code), (False, "IDENTITY_UNVERIFIED"))
        self.assertEqual(r.quarantine[-1][2], "hash mismatch")

    def test_unknown_artifact_quarantined(self):
        r = registry()
        d = r.admit("mystery.jar", B, path="plugins/mystery.jar")
        self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"))
        self.assertEqual(r.quarantine[-1][2], "not on allow-list")

    def test_path_traversal_quarantined(self):
        r = registry()
        for bad in ("../plugin-a.jar", "/abs/plugin-a.jar", "plugins/../../x.jar", "a\\b.jar", ""):
            self.assertFalse(r.admit("plugin-a.jar", A, path=bad).allowed, bad)
        self.assertEqual(len(r.quarantine), 5)

    def test_bad_sha_rejected_at_allow(self):
        with self.assertRaises(ValueError):
            rl.Registry().allow("x", "ABC", "MIT")


class ReleaseTests(unittest.TestCase):
    def manifest(self, version="1.1.0", contract="1.0", schema="1", artifacts=None):
        return rl.ReleaseManifest(version, artifacts or {"plugin-a.jar": SHA_A}, contract, schema)

    def test_manifest_hash_is_canonical_and_immutable(self):
        m1 = self.manifest()
        m2 = rl.ReleaseManifest("1.1.0", {"plugin-a.jar": SHA_A}, "1.0", "1")
        self.assertEqual(m1.hash(), m2.hash())
        self.assertNotEqual(m1.hash(), self.manifest(version="1.1.1").hash())
        with self.assertRaises(Exception):
            m1.version = "x"  # frozen

    def test_forward_pipeline_with_evidence(self):
        rel = rl.Release(self.manifest(), registry())
        for i, state in enumerate(rl.RELEASE_STATES[1:]):
            rel.advance(state, evidence_ref=f"ref:ev:{i}", now=T0)
        self.assertEqual(rel.state, "ACTIVE")
        self.assertEqual(len(rel.evidence), 7)

    def test_skipping_or_missing_evidence_refused(self):
        rel = rl.Release(self.manifest(), registry())
        with self.assertRaises(rl.ReleaseError):
            rel.advance("BUILT", evidence_ref="ref:ev:1", now=T0)
        with self.assertRaises(rl.ReleaseError):
            rel.advance("DOWNLOADED", evidence_ref="no-ref", now=T0)
        self.assertEqual(rel.state, "DETECTED")

    def test_unadmitted_artifact_stops_download(self):
        rel = rl.Release(self.manifest(artifacts={"plugin-a.jar": SHA_B}), registry())
        self.assertEqual(rel.advance("DOWNLOADED", evidence_ref="ref:ev:1", now=T0), "STOPPED")
        self.assertEqual(rel.failure, "artifact not admitted")
        with self.assertRaises(rl.ReleaseError):
            rel.advance("DOWNLOADED", evidence_ref="ref:ev:2", now=T0)

    def test_failure_rolls_back_only_to_compatible_active(self):
        reg = registry()
        active = rl.Release(self.manifest(version="1.0.0"), reg)
        for i, state in enumerate(rl.RELEASE_STATES[1:]):
            active.advance(state, evidence_ref=f"ref:ev:{i}", now=T0)
        compatible = rl.Release(self.manifest(version="1.1.0"), reg)
        self.assertEqual(compatible.fail("canary failed", active=active), "ROLLED_BACK")
        incompatible = rl.Release(self.manifest(version="2.0.0", schema="2"), reg)
        self.assertEqual(incompatible.fail("migration failed", active=active), "STOPPED")
        self.assertEqual(rl.Release(self.manifest(), reg).fail("build failed", active=None), "STOPPED")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.c = rl.BoundedCache(max_entries=2, max_bytes=100, max_age_seconds=60)

    def test_identity_paths_never_cached(self):
        for k in ("hwid.bin", "profile/identity.json", "Jagex_Session", "cookies.db"):
            d = self.c.put("acc1", k, b"x", now=T0)
            self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"), k)
        self.assertEqual(len(self.c), 0)

    def test_count_bound_evicts_lru(self):
        self.c.put("acc1", "a", b"1", now=T0)
        self.c.put("acc1", "b", b"2", now=T0 + timedelta(seconds=1))
        self.c.get("acc1", "a", now=T0 + timedelta(seconds=2))  # a is now most recent
        self.c.put("acc1", "c", b"3", now=T0 + timedelta(seconds=3))
        self.assertIsNone(self.c.get("acc1", "b", now=T0 + timedelta(seconds=3)))
        self.assertEqual(self.c.evicted[-1], ("acc1", "b", "capacity"))

    def test_bytes_bound_and_oversize(self):
        self.assertFalse(self.c.put("acc1", "big", b"x" * 101, now=T0).allowed)
        self.c.put("acc1", "a", b"x" * 60, now=T0)
        self.c.put("acc1", "b", b"x" * 60, now=T0 + timedelta(seconds=1))
        self.assertEqual(len(self.c), 1)
        self.assertLessEqual(self.c.bytes_used, 100)

    def test_age_bound_and_owner_isolation(self):
        self.c.put("acc1", "a", b"1", now=T0)
        self.assertIsNone(self.c.get("acc2", "a", now=T0))                       # other owner cannot read
        self.assertEqual(self.c.get("acc1", "a", now=T0 + timedelta(seconds=59)), b"1")
        self.assertIsNone(self.c.get("acc1", "a", now=T0 + timedelta(seconds=121)))
        self.assertEqual(self.c.evicted[-1], ("acc1", "a", "age"))

    def test_unsafe_key_rejected(self):
        self.assertFalse(self.c.put("acc1", "../escape", b"1", now=T0).allowed)


class AdmissionTests(unittest.TestCase):
    ADM = rl.Admission(rss_limit_bytes=2_000, disk_reserve_bytes=500, fd_limit=100, cpu_limit_percent=90.0, snapshot_max_age_seconds=30)

    def snap(self, **over):
        kw = dict(rss_bytes=1_000, disk_free_bytes=5_000, open_fds=10, cpu_percent=20.0, measured_at=T0)
        kw.update(over)
        return rl.ResourceSnapshot(**kw)

    def test_fresh_snapshot_within_limits_admits(self):
        self.assertTrue(self.ADM.decide(self.snap(), running_sessions=0, now=T0).allowed)

    def test_stale_snapshot_never_admits(self):
        d = self.ADM.decide(self.snap(), running_sessions=0, now=T0 + timedelta(seconds=31))
        self.assertEqual((d.allowed, d.reason_code), (False, "STALE_CONTEXT"))

    def test_each_limit_denies(self):
        for over in (dict(disk_free_bytes=499), dict(rss_bytes=2_000), dict(open_fds=100), dict(cpu_percent=90.0)):
            d = self.ADM.decide(self.snap(**over), running_sessions=0, now=T0)
            self.assertEqual((d.allowed, d.reason_code), (False, "INSUFFICIENT_RESOURCES"), over)

    def test_concurrency_one(self):
        d = self.ADM.decide(self.snap(), running_sessions=1, now=T0)
        self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"))

    def test_pressure_requires_stop(self):
        self.assertFalse(self.ADM.must_stop(self.snap()))
        self.assertTrue(self.ADM.must_stop(self.snap(disk_free_bytes=100)))
        self.assertTrue(self.ADM.must_stop(self.snap(rss_bytes=3_000)))


class NetworkTests(unittest.TestCase):
    P = rl.NetworkPolicy("PROXY", allow_direct_fallback=False, sticky_ttl_seconds=600)

    def check(self, route, **over):
        kw = dict(proxy_healthy=True, sticky_since=T0, unknown_pending=0, now=T0)
        kw.update(over)
        return self.P.check_route(route, **kw)

    def test_healthy_proxy_ok(self):
        self.assertTrue(self.check("PROXY").allowed)

    def test_outage_never_falls_back_to_direct(self):
        self.assertEqual(self.check("PROXY", proxy_healthy=False).reason_code, "PROXY_UNAVAILABLE")
        self.assertEqual(self.check("DIRECT", proxy_healthy=False).reason_code, "POLICY_DENIED")

    def test_sticky_expiry_and_no_renew_during_unknown(self):
        late = T0 + timedelta(seconds=601)
        self.assertEqual(self.check("PROXY", now=late).reason_code, "PROXY_UNAVAILABLE")
        self.assertEqual(self.check("PROXY", now=late, unknown_pending=1).reason_code, "STALE_CONTEXT")

    def test_direct_policy_rejects_proxy_and_unknown_routes(self):
        d = rl.NetworkPolicy("DIRECT")
        self.assertTrue(d.check_route("DIRECT", proxy_healthy=False, sticky_since=None, unknown_pending=0, now=T0).allowed)
        self.assertFalse(d.check_route("PROXY", proxy_healthy=True, sticky_since=None, unknown_pending=0, now=T0).allowed)
        self.assertFalse(self.check("TOR").allowed)
