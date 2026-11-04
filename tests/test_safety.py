"""Offline tests for the static safety-qualification layer (repofuse.safety).

Covers: malicious fixtures fail, clean repos pass statically, the osv.dev
advisory is offline-by-default (unknown), mocked live reads map
found/unreachable/malformed to fail/unknown/unknown, aggregation is
fail>unknown>warn>pass, and the execution gate refuses blocking/stale
verdicts. No network, no provider calls.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repofuse import safety  # noqa: E402


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rf-safety-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def w(self, rel, text):
        full = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
        return full


class TestStaticScan(RepoFixture):
    def test_clean_repo_passes(self):
        self.w("app.py", "def add(a, b):\n    return a + b\n")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.PASS)
        self.assertEqual(r["findings"], [])

    def test_base64_exec_chain_fails(self):
        self.w("evil.py",
               "import base64\n"
               "import zlib\n"
               "blob = base64.b64decode('AAAA')\n"
               "exec(zlib.decompress(blob))\n")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.FAIL)
        self.assertTrue(any(f["rule"] == "obfuscated-payload"
                            for f in r["findings"]))

    def test_pyc_without_source_fails(self):
        self.w("mod.pyc", "\x00\x01\x02fake-bytecode")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.FAIL)
        self.assertTrue(any(f["rule"] == "pyc-without-source"
                            for f in r["findings"]))

    def test_pyc_with_source_not_flagged(self):
        self.w("mod.py", "x = 1\n")
        self.w("mod.pyc", "\x00\x01")
        r = safety.static_scan(self.dir)
        self.assertNotEqual(r["status"], safety.Verdict.FAIL)

    def test_dynamic_exec_warns(self):
        self.w("dyn.py", "def run(code):\n    exec(code)\n")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.WARN)

    def test_ctypes_warns(self):
        self.w("native.py", "import ctypes\nlibc = ctypes.CDLL('libc.so.6')\n")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.WARN)
        self.assertTrue(any(f["rule"] == "native-loading"
                            for f in r["findings"]))

    def test_setup_py_cmdclass_warns(self):
        self.w("setup.py",
               "from setuptools import setup\n"
               "setup(cmdclass={'install': object})\n")
        r = safety.static_scan(self.dir)
        self.assertTrue(any(f["rule"] == "install-hook"
                            for f in r["findings"]))

    def test_package_json_postinstall_warns(self):
        self.w("package.json",
               '{"name": "x", "scripts": {"postinstall": "node x.js"}}')
        r = safety.static_scan(self.dir)
        self.assertTrue(any(f["rule"] == "install-hook"
                            for f in r["findings"]))

    def test_high_entropy_blob_warns(self):
        blob = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4" * 5
        self.w("blob.py", 'DATA = "%s"\n' % blob)
        r = safety.static_scan(self.dir)
        self.assertTrue(any(f["rule"] == "high-entropy-blob"
                            for f in r["findings"]))

    def test_syntax_error_not_punished(self):
        self.w("broken.py", "def broken(:\n")
        r = safety.static_scan(self.dir)
        self.assertEqual(r["status"], safety.Verdict.PASS)


class TestOsvAdvisory(unittest.TestCase):
    PINNED = {"requests": {"spec": "==2.31.0", "via": "requirements.txt"},
              "lodash": {"spec": "==4.17.21", "via": "package.json"}}
    DEPS = dict(PINNED, loose={"spec": ">=1.0", "via": "requirements.txt"})
    COMMIT = "a" * 40

    @staticmethod
    def _resp(payload):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(payload).encode()
        return Resp()

    def test_offline_mode_is_unknown_and_says_not_run(self):
        r = safety.osv_check(self.DEPS, repo_commit=self.COMMIT,
                             allow_network=False)
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)
        self.assertEqual(r["source"], "offline mode")
        self.assertIn("not run (offline mode)", r["note"])
        self.assertNotIn("unreachable", r["note"])
        self.assertEqual(r["queries_made"], 0)

    def test_missing_commit_reference_is_unknown(self):
        r = safety.osv_check({}, repo_commit=None, allow_network=True,
                             opener=lambda req, timeout=None: self._resp(
                                 {"results": []}))
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)
        self.assertEqual(r["unresolved"][0]["name"], "(repo itself)")

    def test_no_queries_made_says_so(self):
        """Reviewer rule: an empty check must say no queries were made,
        never claim a completed read."""
        r = safety.osv_check({}, repo_commit=None, allow_network=False)
        self.assertEqual(r["queries_made"], 0)
        r2 = safety.osv_check({}, repo_commit=None, allow_network=True)
        self.assertEqual(r2["queries_made"], 0)
        self.assertIn("no queries made", r2["note"])
        self.assertEqual(r2["status"], safety.Verdict.UNKNOWN)

    def test_payload_is_commit_plus_names_versions_only(self):
        seen = {}

        def opener(req, timeout=None):
            seen["url"] = req.full_url
            seen["body"] = json.loads(req.data.decode())
            return self._resp({"results": [{}, {}, {}]})

        r = safety.osv_check(self.PINNED, repo_commit=self.COMMIT,
                             allow_network=True, opener=opener)
        # zero matches is NOT a covered pass: WARN flagged for review
        self.assertEqual(r["status"], safety.Verdict.WARN)
        self.assertIn("does not establish", r["note"])
        self.assertEqual(r["queries_made"], 3)
        self.assertEqual(seen["url"], safety.OSV_QUERYBATCH)
        qs = seen["body"]["queries"]
        self.assertEqual(qs[0], {"commit": self.COMMIT})  # repo-self first
        for q in qs[1:]:
            self.assertEqual(sorted(q.keys()), ["package", "version"])
            self.assertEqual(sorted(q["package"].keys()),
                             ["ecosystem", "name"])
        self.assertIn("transitive", r["scope"])  # scope stated explicitly

    def test_unpinned_dep_makes_status_unknown(self):
        r = safety.osv_check(self.DEPS, repo_commit=self.COMMIT,
                             allow_network=True,
                             opener=lambda req, timeout=None: self._resp(
                                 {"results": [{}, {}, {}]}))
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)
        self.assertIn("unresolved", r["note"])
        self.assertEqual(r["queries_made"], 3)  # queries really happened

    def test_unresolved_ecosystem_is_unknown_never_guessed(self):
        r = safety.osv_check({"x": {"spec": "==1.0", "via": "Gemfile.lock"}},
                             repo_commit=self.COMMIT, allow_network=True,
                             opener=lambda req, timeout=None: self._resp(
                                 {"results": [{}]}))
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)
        self.assertEqual(r["unresolved"][0]["reason"],
                         "unresolved ecosystem")

    def test_version_allowlist_blocks_raw_options(self):
        r = safety.osv_check({"evil": {"spec": "==1.0 --index-url http://x",
                                       "via": "requirements.txt"}},
                             repo_commit=self.COMMIT, allow_network=False)
        self.assertEqual(r["unresolved"][0]["name"], "evil")

    def test_empty_result_never_claims_pass(self):
        """Official contract: a response lists MATCHING records. Zero
        matches proves nothing about indexing or safety -> WARN, with the
        caveat spelled out, never PASS."""
        r = safety.osv_check({}, repo_commit=self.COMMIT, allow_network=True,
                             opener=lambda req, timeout=None: self._resp(
                                 {"results": [{}]}))
        self.assertEqual(r["status"], safety.Verdict.WARN)
        self.assertIn("not establish", r["note"])
        self.assertNotEqual(r["status"], safety.Verdict.PASS)

    def test_vuln_found_fails_and_names_subject(self):
        def opener(req, timeout=None):
            return self._resp({"results": [
                {"vulns": [{"id": "GHSA-xxxx", "modified": "2026-01-01"}]},
                {}, {}]})

        r = safety.osv_check(self.PINNED, repo_commit=self.COMMIT,
                             allow_network=True, opener=opener)
        self.assertEqual(r["status"], safety.Verdict.FAIL)
        self.assertEqual(r["vulnerabilities"][0]["kind"], "repo")
        self.assertEqual(r["vulnerabilities"][0]["subject"], self.COMMIT)

    def test_unreachable_is_unknown_not_crash(self):
        def boom(req, timeout=None):
            raise OSError("connection refused")

        r = safety.osv_check(self.PINNED, repo_commit=self.COMMIT,
                             allow_network=True, opener=boom)
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)
        self.assertIn("advisory read failed", r["note"])
        self.assertNotIn("offline mode", r["note"])

    def test_malformed_response_is_unknown(self):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"not json"

        r = safety.osv_check(self.PINNED, repo_commit=self.COMMIT,
                             allow_network=True,
                             opener=lambda req, timeout=None: Resp())
        self.assertEqual(r["status"], safety.Verdict.UNKNOWN)


class TestAggregation(RepoFixture):
    def test_fail_beats_unknown_beats_warn_beats_pass(self):
        self.assertEqual(safety._worst(
            [safety.Verdict.PASS, safety.Verdict.WARN]), safety.Verdict.WARN)
        self.assertEqual(safety._worst(
            [safety.Verdict.WARN, safety.Verdict.UNKNOWN]),
            safety.Verdict.UNKNOWN)
        self.assertEqual(safety._worst(
            [safety.Verdict.UNKNOWN, safety.Verdict.FAIL]),
            safety.Verdict.FAIL)

    def test_clean_repo_blocks_offline(self):
        """Spotless statics still block when the required advisory could
        not run (offline mode): unknown is blocking, by design."""
        self.w("app.py", "x = 1\n")
        v = safety.qualify_repo("demo", self.dir, deps={},
                                repo_commit="b" * 40, allow_network=False)
        self.assertEqual(v["static"]["status"], safety.Verdict.PASS)
        self.assertEqual(v["status"], safety.Verdict.UNKNOWN)
        self.assertTrue(v["blocking"])
        self.assertTrue(safety.qualify_run([v])["blocking"])

    def test_fail_repo_blocks_run(self):
        self.w("evil.py",
               "import base64\nexec(base64.b64decode('AAAA'))\n")
        v = safety.qualify_repo("evil", self.dir, deps={},
                                repo_commit="b" * 40, allow_network=False)
        self.assertEqual(v["status"], safety.Verdict.FAIL)
        self.assertTrue(safety.qualify_run([v])["blocking"])

    def test_warn_blocks_until_acknowledged(self):
        """Reviewer rule: a warn blocks spending/execution until an
        explicit acknowledgment is recorded."""
        self.w("setup.py",
               "from setuptools import setup\n"
               "setup(cmdclass={'install': object})\n")
        clean = {"status": safety.Verdict.PASS, "source": "test",
                 "queries_made": 1, "vulnerabilities": [], "unresolved": [],
                 "scope": "test", "note": "stub"}
        repo = {"repo": "demo", "status": safety.Verdict.WARN,
                "blocking": False, "static": {"status": "warn"},
                "dependencies": clean}
        blocked = safety.qualify_run([repo])
        self.assertTrue(blocked["blocking"])
        acked = safety.qualify_run([repo], warnings_acknowledged=True,
                                   acknowledged_via="reviewer sign-off")
        self.assertFalse(acked["blocking"])
        self.assertEqual(acked["acknowledgment"]["via"],
                         "reviewer sign-off")

    def test_honesty_states_transitive_scope(self):
        run = safety.qualify_run([])
        self.assertIn("transitive", run["honesty"])
        self.assertIn("cannot prove", run["honesty"])


if __name__ == "__main__":
    unittest.main()
