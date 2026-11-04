"""End-to-end engine tests on locally-built fixture repos.

No network, no model key: proves the deterministic pipeline and the honest
pending behavior of the model-gated steps.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repofuse import ingest as ingest_mod
from repofuse import analyze as analyze_mod
from repofuse import plan as plan_mod
from repofuse import synthesize as synth_mod
from repofuse import verify as verify_mod
from repofuse import report as report_mod
from repofuse import model_api
from repofuse.cli import main as cli_main

MIT = "MIT License\n\nCopyright (c) 2026 Example\n"

ENGINE_PY = '''
import os
import sqlite3

CANARY = os.environ.get("ENGINE_DB_PATH")

class VectorStore:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)

    def add(self, text, embedding):
        return True

def search(store, embedding, k=5):
    return []

if __name__ == "__main__":
    print("engine")
'''

INTERFACE_PY = '''
from flask import Flask

app = Flask(__name__)

@app.get("/items")
def list_items():
    return []

@app.post("/items")
def add_item():
    return {}
'''


def make_repo(root, name, files):
    path = os.path.join(root, name)
    os.makedirs(path)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=path, check=True)
    return path


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="repofuse-test-")
        cls.engine_repo = make_repo(cls.tmp, "vectorengine", {
            "LICENSE": MIT,
            "README.md": "# vectorengine\nTiny embedded vector store.\n",
            "engine.py": ENGINE_PY,
            "requirements.txt": "numpy==1.26.4\n",
        })
        cls.iface_repo = make_repo(cls.tmp, "miniapi", {
            "LICENSE": MIT,
            "README.md": "# miniapi\nTiny JSON API server.\n",
            "server.py": INTERFACE_PY,
            "requirements.txt": "flask==3.0.0\nnumpy==1.24.0\n",
        })
        cls.out = os.path.join(cls.tmp, "out")
        cls.workdir = os.path.join(cls.out, "repos")
        os.makedirs(cls.workdir)
        cls.metas = [ingest_mod.ingest(cls.engine_repo, cls.workdir,
                                       allow_local=True),
                     ingest_mod.ingest(cls.iface_repo, cls.workdir,
                                       allow_local=True)]
        cls.analyses = [analyze_mod.analyze(m) for m in cls.metas]
        cls.manifest = plan_mod.build_manifest(cls.metas, cls.analyses)

    def test_ingest_metadata(self):
        m = self.metas[0]
        self.assertIsNone(m["clone_error"])
        self.assertTrue(m["commit_sha"])
        self.assertEqual(m["license_guess"], "MIT")
        self.assertIn("Python", m["languages"])
        self.assertIn("requirements.txt", m["manifests"])

    def test_analysis_ast_exports_and_routes(self):
        eng = self.analyses[0]
        self.assertIn("VectorStore", eng["exports"])
        self.assertIn("search", eng["exports"])
        self.assertIn("ENGINE_DB_PATH", eng["env_vars"])
        api = self.analyses[1]
        paths = {r["path"] for r in api["routes"]}
        self.assertEqual(paths, {"/items"})
        self.assertIn("flask", api["dependencies"])

    def test_manifest_roles_and_conflicts(self):
        roles = {r["slug"]: r["role"] for r in self.manifest["repos"]}
        self.assertEqual(roles["miniapi"], "interface")
        self.assertEqual(roles["vectorengine"], "data")  # numpy dep -> data layer
        kinds = {c["type"] for c in self.manifest["conflicts"]}
        self.assertIn("dependency-version", kinds)  # numpy pins differ
        model_steps = [s for s in self.manifest["steps"] if s["kind"] == "model"]
        self.assertTrue(all(s["status"] == "pending" for s in model_steps))

    def test_synthesis_pending_without_key(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("MODEL_API_KEY", "META_API_KEY")}
        res = synth_mod.run_synthesis(self.manifest, self.metas, self.out, env=env)
        self.assertEqual(res["status"], "pending_no_key")
        self.assertEqual(res["files_written"], [])
        prompt_path = os.path.join(self.out, "prompts", "architecture-manifest.json")
        self.assertTrue(os.path.exists(prompt_path))
        bundle = json.load(open(prompt_path))
        self.assertEqual(bundle[0]["role"], "developer")
        self.assertIn("arbitrage_opportunity", bundle[1]["content"])

    def test_model_client_refuses_without_key(self):
        with self.assertRaises(model_api.ModelUnavailable):
            model_api.chat_completion([{"role": "user", "content": "hi"}],
                                      env={})

    def test_verify_skips_honestly(self):
        res = verify_mod.verify_fused_app(os.path.join(self.out, "fused_app"))
        self.assertEqual(res["status"], "skipped")

    def test_report_written(self):
        rep = report_mod.build_report(self.out, self.metas, self.manifest,
                                      {"status": "pending_no_key"},
                                      {"status": "skipped"})
        self.assertTrue(os.path.exists(os.path.join(self.out, "report.json")))
        self.assertEqual(rep["synthesis"]["status"], "pending_no_key")

    def test_cli_end_to_end(self):
        out2 = os.path.join(self.tmp, "out-cli")
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("META_API_KEY", None)
        rc = cli_main(["run", self.engine_repo, self.iface_repo,
                       "--out", out2, "--allow-local"])
        self.assertEqual(rc, 0)
        for name in ("ingest.json", "analysis.json", "fuse_manifest.json",
                     "synthesis.json", "verification.json", "report.json"):
            self.assertTrue(os.path.exists(os.path.join(out2, name)), name)
        synthesis = json.load(open(os.path.join(out2, "synthesis.json")))
        self.assertEqual(synthesis["status"], "pending_no_key")


class VerifyRealRunTest(unittest.TestCase):
    def _attest(self, fusion):
        from repofuse import gluereview
        path = os.path.join(os.path.dirname(fusion.rstrip("/")) or ".",
                            "attest.json")
        if os.path.dirname(fusion) == "":
            path = "attest.json"
        path = os.path.join(tempfile.mkdtemp(prefix="repofuse-att-"),
                            "attest.json")
        gluereview.write_attestation(fusion, path)
        return path

    def test_verify_actually_runs_tests(self):
        tmp = tempfile.mkdtemp(prefix="repofuse-verify-")
        with open(os.path.join(tmp, "test_fused.py"), "w") as f:
            f.write("import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.assertEqual(1 + 1, 2)\n")
        res = verify_mod.verify_fused_app(tmp,
                                          attestation_path=self._attest(tmp))
        self.assertEqual(res["status"], "passed", res)

    def test_gate_blocks_unreviewed_glue(self):
        tmp = tempfile.mkdtemp(prefix="repofuse-verify-")
        with open(os.path.join(tmp, "test_fused.py"), "w") as f:
            f.write("import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.assertEqual(1 + 1, 2)\n")
        res = verify_mod.verify_fused_app(tmp)
        self.assertEqual(res["status"], "pending_glue_review", res)
        self.assertIn("test_fused.py", res["files_pending_review"])

    def test_gate_detects_drift_after_review(self):
        tmp = tempfile.mkdtemp(prefix="repofuse-verify-")
        path = os.path.join(tmp, "test_fused.py")
        with open(path, "w") as f:
            f.write("import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_ok(self):\n"
                    "        self.assertEqual(1 + 1, 2)\n")
        att = self._attest(tmp)
        with open(path, "a") as f:  # change bytes after review
            f.write("# drift\n")
        res = verify_mod.verify_fused_app(tmp, attestation_path=att)
        self.assertEqual(res["status"], "pending_glue_review", res)
        self.assertIn("changed since review", res["detail"])

    def test_verify_detects_failure(self):
        tmp = tempfile.mkdtemp(prefix="repofuse-verify-")
        with open(os.path.join(tmp, "test_fused.py"), "w") as f:
            f.write("import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_bad(self):\n"
                    "        self.assertEqual(1, 2)\n")
        res = verify_mod.verify_fused_app(tmp,
                                          attestation_path=self._attest(tmp))
        self.assertEqual(res["status"], "failed")


if __name__ == "__main__":
    unittest.main()

class HealAndPackageTest(unittest.TestCase):
    def test_heal_not_attempted_on_skip(self):
        import tempfile
        from repofuse import heal as heal_mod, package as package_mod
        tmp = tempfile.mkdtemp(prefix="repofuse-heal-")
        res = heal_mod.auto_heal(tmp, {"status": "skipped"})
        self.assertEqual(res["status"], "not_attempted")

    def test_heal_pending_without_key_on_failure(self):
        import tempfile
        from repofuse import heal as heal_mod
        tmp = tempfile.mkdtemp(prefix="repofuse-heal-")
        env = {k: v for k, v in os.environ.items()
               if k not in ("MODEL_API_KEY", "META_API_KEY")}
        res = heal_mod.auto_heal(tmp, {"status": "failed", "stderr": "boom"}, env=env)
        self.assertEqual(res["status"], "pending_no_key")

    def test_package_emits_unverified_dockerfile(self):
        import tempfile, json
        from repofuse import package as package_mod
        tmp = tempfile.mkdtemp(prefix="repofuse-pkg-")
        os.makedirs(os.path.join(tmp, "fused_app"))
        res = package_mod.package_fused_app(tmp)
        self.assertEqual(res["status"], "packaged")
        self.assertFalse(res["bundle"]["build_verified"])
        docker = open(os.path.join(tmp, "fused_app", "Dockerfile")).read()
        self.assertIn("NOT build-verified", docker)

class HardeningTest(unittest.TestCase):
    def test_write_files_blocks_traversal_and_size(self):
        import tempfile
        from repofuse.synthesize import _write_files
        tmp = tempfile.mkdtemp(prefix="repofuse-wf-")
        fusion = os.path.join(tmp, "fused_app")
        os.makedirs(fusion)
        written = _write_files(fusion, {
            "../escape.py": "print('no')",
            "/abs.py": "print('no')",
            "sub/dir.py": "print('no')",
            "vendor.py": "x = 1",           # fine as a glue name
            "ok.py": "x = 1",
            "test_fused.py": "print('no')",  # test slot not open in glue slot
            "big.py": "y" * (300 * 1024),
        }, "test-model", "now", slot="glue")
        self.assertEqual(sorted(written),
                         ["generated/ok.py", "generated/vendor.py"])
        self.assertFalse(os.path.exists(os.path.join(tmp, "escape.py")))
        self.assertFalse(os.path.exists(os.path.join(fusion, "test_fused.py")))
        # test slot writes exactly test_fused.py, once
        w2 = _write_files(fusion, {"test_fused.py": "T = 1"}, "m", "now",
                          slot="test")
        self.assertEqual(w2, ["test_fused.py"])
        w3 = _write_files(fusion, {"test_fused.py": "T = 2"}, "m", "now",
                          slot="test")
        self.assertEqual(w3, [], "no overwrite of existing generated file")

    def test_ingest_rejects_escaping_symlink(self):
        import subprocess, tempfile
        from repofuse import ingest as ingest_mod
        tmp = tempfile.mkdtemp(prefix="repofuse-sym-")
        src = os.path.join(tmp, "badrepo")
        os.makedirs(src)
        open(os.path.join(src, "LICENSE"), "w").write("MIT License\n")
        open(os.path.join(src, "README.md"), "w").write("# bad\n")
        os.symlink("/etc/passwd", os.path.join(src, "evil.py"))
        subprocess.run(["git", "init", "-q"], cwd=src, check=True)
        subprocess.run(["git", "add", "-A"], cwd=src, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "x"], cwd=src, check=True)
        sha, err = ingest_mod.clone_repo(src, os.path.join(tmp, "dst"))  # clone_repo itself is internal
        self.assertIsNone(sha)
        self.assertIn("symlink", err)

    def test_vendor_hashes_and_license_retained(self):
        from repofuse import vendor as vendor_mod
        out = os.path.join(self.tmp, "vendortest") if hasattr(self, "tmp") else None
        import tempfile
        tmp = tempfile.mkdtemp(prefix="repofuse-vendor-")
        metas = [{"path": EngineTest.engine_repo if False else None}]
        # use the shared fixtures
        metas = EngineTest.metas
        fusion = os.path.join(tmp, "fused_app")
        man = vendor_mod.vendor_repos(metas, fusion)
        self.assertEqual(len(man["repos"]), 2)
        self.assertTrue(os.path.exists(
            os.path.join(fusion, "vendor", "vectorengine", "LICENSE")))
        self.assertIn("vectorengine/engine.py", man["hashes"])
        self.assertEqual(len(man["hashes"]["vectorengine/engine.py"]), 64)

    def test_context_cap_refusal(self):
        import tempfile
        from repofuse import synthesize as synth_mod
        from repofuse import model_api
        tmp = tempfile.mkdtemp(prefix="repofuse-cap-")
        big = {"slug": "big", "path": tmp, "url": "u", "commit_sha": "x",
               "readme_excerpt": "z" * 100, "tree": ["a"]}
        manifest = {"repos": [{"slug": "big", "role": "engine",
                               "exports": [], "routes": [], "dependency_count": 0}],
                    "boundary_candidates": [],
                    "conflicts": [{"type": "x" * 60000}]}
        orig_have = model_api.have_model_key
        orig_count = model_api.count_tokens
        orig_chat = model_api.chat_completion
        model_api.have_model_key = lambda env=None: True
        try:
            # 1) probe refuses when count_tokens unavailable
            model_api.count_tokens = lambda *a, **k: None
            res = synth_mod.run_synthesis(manifest, [big], tmp, env={})
            self.assertEqual(res["status"], "failed")
            self.assertIn("count_tokens unavailable", res["detail"])

            # 2) call_gated: char bound trips before measurement
            from repofuse.budget import Budget, BudgetExceeded
            budget = Budget(os.path.join(tmp, "budget.json"))
            huge = [{"role": "user", "content": "x" * 60000}]
            with self.assertRaises(BudgetExceeded):
                synth_mod.call_gated("architecture-manifest", huge, tmp, budget)
            # 3) call_gated: measured over cap refuses
            model_api.count_tokens = lambda *a, **k: 99999
            with self.assertRaises(BudgetExceeded):
                synth_mod.call_gated("architecture-manifest",
                                     [{"role": "user", "content": "hi"}],
                                     tmp, budget)
            # 4) aggregate cap: reserve until exhausted
            model_api.count_tokens = lambda *a, **k: 11000
            for i in range(5):
                budget.reserve(f"s{i}", 11000, 4096)
            with self.assertRaises(BudgetExceeded):
                budget.reserve("s6", 11000, 4096)
            # 5) probe disagreement aborts
            model_api.count_tokens = lambda *a, **k: 10
            model_api.chat_completion = lambda *a, **k: {
                "content": "ready", "model": "m",
                "usage": {"prompt_tokens": 999, "completion_tokens": 1},
                "latency_ms": 1}
            budget2 = Budget(os.path.join(tmp, "budget2.json"))
            probe = synth_mod.run_probe(tmp, budget2, env={})
            self.assertEqual(probe["status"], "failed")
            self.assertIn("disagrees", probe["detail"])
        finally:
            model_api.have_model_key = orig_have
            model_api.count_tokens = orig_count
            model_api.chat_completion = orig_chat

    def test_same_invocation_attestation_refused(self):
        import argparse
        from repofuse.cli import _refuse_same_invocation_attestation
        args = argparse.Namespace(glue_reviewed=True)
        self.assertTrue(_refuse_same_invocation_attestation(
            args, {"status": "completed", "files_written": ["generated/a.py"]}))
        self.assertFalse(_refuse_same_invocation_attestation(
            args, {"status": "completed", "files_written": ["generated/a.py"],
                   "_reused": True}))
        self.assertFalse(_refuse_same_invocation_attestation(
            args, {"status": "pending_no_key", "files_written": []}))
        self.assertFalse(_refuse_same_invocation_attestation(
            argparse.Namespace(glue_reviewed=False),
            {"status": "completed", "files_written": ["generated/a.py"]}))

    def test_ingest_pin_mismatch_refused(self):
        import tempfile
        from repofuse import ingest as ingest_mod
        tmp = tempfile.mkdtemp(prefix="repofuse-pin-")
        meta = ingest_mod.ingest(EngineTest.engine_repo, tmp,
                                 expected_sha="0" * 40, allow_local=True)
        self.assertIn("pin mismatch", meta["clone_error"])
        meta = ingest_mod.ingest(EngineTest.engine_repo,
                                 os.path.join(tmp, "ok"),
                                 expected_sha=EngineTest.metas[0]["commit_sha"],
                                 allow_local=True)
        self.assertIsNone(meta["clone_error"])


class AcceptanceTest(unittest.TestCase):
    def _fusion(self, test_src, glue_src="VALUE = 41\n"):
        import tempfile, os
        tmp = tempfile.mkdtemp(prefix="repofuse-acc-")
        fusion = os.path.join(tmp, "fused_app")
        vendor = os.path.join(fusion, "vendor", "vectorengine")
        gen = os.path.join(fusion, "generated")
        os.makedirs(vendor)
        os.makedirs(gen)
        open(os.path.join(vendor, "engine.py"), "w").write("def real():\n    return 1\n")
        open(os.path.join(gen, "glue.py"), "w").write(glue_src)
        open(os.path.join(fusion, "test_fused.py"), "w").write(test_src)
        return fusion

    def test_independence_detects_vendored_reference(self):
        from repofuse import acceptance as accept_mod
        fusion = self._fusion(
            "import unittest, sys, os\n"
            "sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vendor', 'vectorengine'))\n"
            "import engine\n"
            "class T(unittest.TestCase):\n"
            "    def test_real(self):\n"
            "        self.assertEqual(engine.real(), 1)\n")
        res = accept_mod.check_test_independence(
            fusion, os.path.join(fusion, "vendor"))
        self.assertTrue(res["independent"], res)

    def test_independence_rejects_glue_only_test(self):
        from repofuse import acceptance as accept_mod
        fusion = self._fusion(
            "import unittest\nfrom generated import glue\n"
            "class T(unittest.TestCase):\n"
            "    def test_glue(self):\n"
            "        self.assertEqual(glue.VALUE, 41)\n")
        res = accept_mod.check_test_independence(
            fusion, os.path.join(fusion, "vendor"))
        self.assertFalse(res["independent"], res)

    def test_vacuity_control_confirms_real_fusion(self):
        from repofuse import verify as verify_mod
        from repofuse.sandbox import bwrap_available
        if not bwrap_available():
            self.skipTest("bwrap required")
        fusion = self._fusion(
            "import unittest\nfrom generated import glue\n"
            "class T(unittest.TestCase):\n"
            "    def test_glue(self):\n"
            "        self.assertEqual(glue.VALUE, 41)\n")
        from repofuse import gluereview
        att = os.path.join(tempfile.mkdtemp(prefix="repofuse-att-"),
                           "attest.json")
        gluereview.write_attestation(fusion, att)
        res = verify_mod.verify_fused_app(fusion, attestation_path=att)
        self.assertEqual(res["status"], "passed", str(res)[:300])
        vac = verify_mod.vacuity_control(
            fusion, ["generated/glue.py", "test_fused.py"],
            attestation_path=att)
        self.assertEqual(vac["status"], "vacuity_confirmed", vac)

    def test_vacuity_control_rejects_vacuous_tests(self):
        from repofuse import verify as verify_mod
        from repofuse.sandbox import bwrap_available
        if not bwrap_available():
            self.skipTest("bwrap required")
        fusion = self._fusion(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_math(self):\n"
            "        self.assertEqual(1 + 1, 2)\n")
        from repofuse import gluereview
        att = os.path.join(tempfile.mkdtemp(prefix="repofuse-att-"),
                           "attest.json")
        gluereview.write_attestation(fusion, att)
        vac = verify_mod.vacuity_control(
            fusion, ["generated/glue.py", "test_fused.py"],
            attestation_path=att)
        self.assertEqual(vac["status"], "vacuous_tests", vac)


class InputValidationTest(unittest.TestCase):
    def test_url_validation(self):
        from repofuse.ingest import validate_repo_url
        self.assertTrue(validate_repo_url(
            "https://github.com/miguelgrinberg/microdot"))
        self.assertTrue(validate_repo_url(
            "https://github.com/coleifer/peewee.git"))
        for bad in ("--upload-pack=evil", "file:///etc/passwd",
                    "git://github.com/a/b", "ssh://git@github.com/a/b",
                    "https://github.com.evil.com/a/b", "",
                    "https://github.com/a/b; rm -rf /"):
            self.assertFalse(validate_repo_url(bad), bad)
        self.assertFalse(validate_repo_url("/tmp/x"))  # no allow_local


class QualificationHarnessIntegrationTest(unittest.TestCase):
    """Full harness proof against the real pinned repos. Network + bwrap
    required; opt in with REPOFUSE_INTEGRATION=1."""

    @unittest.skipUnless(os.environ.get("REPOFUSE_INTEGRATION") == "1",
                         "integration test: set REPOFUSE_INTEGRATION=1")
    def test_fixed_acceptance_judges_reference_glue(self):
        import shutil, tempfile
        from repofuse.cli import main as cli_main
        from repofuse import verify as verify_mod
        out = tempfile.mkdtemp(prefix="repofuse-qual-")
        rc = cli_main(["qualify", "--out", out])
        self.assertEqual(rc, 1)  # no model key: synthesis pending, no glue
        gen = os.path.join(out, "fused_app", "generated")
        os.makedirs(gen, exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(__file__),
                                 "fixtures", "reference_app.py"),
                    os.path.join(gen, "app.py"))
        from repofuse import gluereview
        att = os.path.join(out, "glue_review.attestation.json")
        gluereview.write_attestation(os.path.join(out, "fused_app"), att)
        res = verify_mod.verify_fused_app(os.path.join(out, "fused_app"),
                                          test_module="acceptance_test",
                                          attestation_path=att)
        self.assertEqual(res["status"], "passed", str(res)[:400])
        vac = verify_mod.vacuity_control(os.path.join(out, "fused_app"),
                                         ["generated/app.py"],
                                         test_module="acceptance_test",
                                         attestation_path=att)
        self.assertEqual(vac["status"], "vacuity_confirmed", vac)
