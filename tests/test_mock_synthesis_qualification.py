"""Offline qualification of the GENERAL synthesis path against a chosen
vendor tree - zero live calls. A contract-faithful fake provider drives
the REAL run_synthesis (probe -> architecture -> glue -> test) over a
fusion dir built by the REAL plan/vendor stages from local fixture
repos. Proves the staged mechanics work against chosen vendored code
and that every output stays fixture-labeled and review-gated. Nothing
here is AI output and nothing is claimed as such."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repofuse import gluereview, model_api, plan, synthesize, vendor  # noqa: E402

FIXTURE_MODEL = "offline-fixture-provider"


def _repo(root, slug, module):
    d = os.path.join(root, slug)
    os.makedirs(os.path.join(d, slug + "pkg"))
    with open(os.path.join(d, slug + "pkg", "__init__.py"), "w") as f:
        f.write(module)
    with open(os.path.join(d, "LICENSE"), "w") as f:
        f.write("MIT License\n")
    return d


def _meta(d, slug, sha):
    return {"url": f"https://example.invalid/x/{slug}", "slug": slug,
            "path": d, "commit_sha": sha, "license_guess": "MIT",
            "license_file": "LICENSE",
            "tree": [f"{slug}pkg/__init__.py", "LICENSE"],
            "readme_excerpt": f"fixture {slug}"}


def _analysis(slug, exports):
    return {"slug": slug, "exports": exports, "routes": [],
            "dependencies": {}, "env_vars": [], "ports": [],
            "js_files": [],
            "python_files": [{"file": f"{slug}pkg/__init__.py",
                              "exports": exports, "imports": [],
                              "routes": []}]}


class FakeProvider:
    """Validates the outbound contract; answers in the parsed shape."""

    def __init__(self):
        self.count_calls = 0
        self.chat_calls = 0

    def count_tokens(self, messages, model="m", timeout=30, env=None):
        self.count_calls += 1
        return sum(len(m["content"]) for m in messages) // 4

    def chat_completion(self, messages, model="m", max_tokens=4096,
                        timeout=60, base_url=None, env=None,
                        reasoning_effort=None, response_format=None):
        self.chat_calls += 1
        assert (env or {}).get("MODEL_API_KEY") == "fixture-key-not-real"
        joined = " ".join(m["content"] for m in messages)
        if "Reply with the word" in joined:
            content = "ready"
        elif "architecture bridge manifest" in joined:
            content = json.dumps({
                "source_exports": {"alpha": ["alpha_fn"],
                                   "beta": ["beta_fn"]},
                "arbitrage_opportunity": "fixture fusion",
                "required_shims": ["adapter"],
                "bridge": [{"from_repo": "alpha",
                            "from_export": "alpha_fn",
                            "to_repo": "beta",
                            "to_route_or_input": "beta_fn"}],
                "risks": ["none"]})
        elif "adapter shim code" in joined:
            assert response_format == {"type": "json_object"}
            content = json.dumps({"app_adapter.py":
                                  "# fixture adapter\nBRIDGE = 1\n"})
        elif "integration test file" in joined:
            content = json.dumps({"test_fused.py": "import unittest\n"})
        else:
            raise AssertionError("unrecognized prompt in fake provider")
        return {"content": content, "model": FIXTURE_MODEL,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "latency_ms": 1, "finish_reason": "stop"}


class MockSynthesisQualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rf-mockqual-")
        self.out = os.path.join(self.tmp, "run")
        self.fusion = os.path.join(self.out, "fused_app")
        os.makedirs(self.fusion)
        da = _repo(self.tmp, "alpha", "def alpha_fn():\n    return 1\n")
        db = _repo(self.tmp, "beta", "def beta_fn():\n    return 2\n")
        self.metas = [_meta(da, "alpha", "a" * 40),
                      _meta(db, "beta", "b" * 40)]
        self.analyses = [_analysis("alpha", ["alpha_fn"]),
                         _analysis("beta", ["beta_fn"])]
        self.manifest = plan.build_manifest(self.metas, self.analyses)
        vendor.vendor_repos(self.metas, self.fusion)
        vendor.write_import_shim(self.fusion)
        self.fake = FakeProvider()
        self._orig = (model_api.count_tokens, model_api.chat_completion)
        model_api.count_tokens = self.fake.count_tokens
        model_api.chat_completion = self.fake.chat_completion
        self.env = {"MODEL_API_KEY": "fixture-key-not-real"}

    def tearDown(self):
        model_api.count_tokens, model_api.chat_completion = self._orig

    def test_full_staged_path_over_chosen_vendor_tree(self):
        res = synthesize.run_synthesis(self.manifest, self.metas,
                                       self.out, env=self.env)
        assert res["status"] == "completed", res
        assert self.fake.chat_calls == 4  # probe + arch + glue + test
        assert self.fake.count_calls == 4  # each charged call prefighted
        assert set(res["files_written"]) == {
            os.path.join("generated", "app_adapter.py"), "test_fused.py"}
        # files carry the fixture provider's name, never a real model's
        for rel in res["files_written"]:
            head = open(os.path.join(self.fusion, rel)).read(400)
            assert FIXTURE_MODEL in head, rel
        # raw paid responses retained per step
        for step in ("probe", "architecture-manifest", "glue-synthesis",
                     "test-synthesis"):
            assert os.path.isfile(os.path.join(
                self.out, "raw_responses", step + ".json")), step
        # vendored tree untouched by generation
        manifest = json.loads(open(os.path.join(
            self.fusion, "vendor", "hashes.json")).read())
        assert manifest["repos"] and manifest["hashes"]

    def test_review_gate_covers_mock_output_and_chosen_vendor(self):
        res = synthesize.run_synthesis(self.manifest, self.metas,
                                       self.out, env=self.env)
        assert res["status"] == "completed", res
        att = os.path.join(self.out, "attestation.json")
        doc = gluereview.write_attestation(self.fusion, att)
        # the pinned set includes mock-generated files AND vendor files
        assert any(k.startswith("vendor" + os.sep) for k in doc["files"])
        assert os.path.join("generated", "app_adapter.py") in doc["files"]
        assert "test_fused.py" in doc["files"]
        ok, why, _ = gluereview.check_attestation(self.fusion, att)
        assert ok, why
        # one tampered vendored byte fails the whole gate
        vf = os.path.join(self.fusion, "vendor", "alpha", "alphapkg",
                          "__init__.py")
        with open(vf, "a") as f:
            f.write("\n# tampered\n")
        ok, why, _ = gluereview.check_attestation(self.fusion, att)
        assert not ok and "changed since review" in why

    def test_pending_no_key_path_is_structural(self):
        # with no key in env, the same call writes the bundle and stops
        res = synthesize.run_synthesis(self.manifest, self.metas,
                                       self.out, env={})
        assert res["status"] == "pending_no_key"
        assert res["files_written"] == []
        assert os.path.isfile(os.path.join(
            self.out, "prompts", "architecture-manifest.json"))
        assert self.fake.chat_calls == 0 and self.fake.count_calls == 0


if __name__ == "__main__":
    unittest.main()


class IntentAndEnvelope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rf-intent-")
        self.metas = [
            {"slug": "alpha", "readme_excerpt": "a", "tree": ["a.py"]},
            {"slug": "beta", "readme_excerpt": "b", "tree": ["b.py"]}]
        self.manifest = {
            "repos": [{"slug": "alpha", "role": "library",
                       "exports": ["alpha_fn"], "routes": [],
                       "dependency_count": 0},
                      {"slug": "beta", "role": "library",
                       "exports": ["beta_fn"], "routes": [],
                       "dependency_count": 0}],
            "boundary_candidates": [], "conflicts": [],
            "acceptance_criteria": []}

    def _payload(self, msgs):
        return json.loads(msgs[1]["content"])

    def test_intent_reaches_all_three_prompts(self):
        arch = {"source_exports": {}, "arbitrage_opportunity": "x",
                "required_shims": [], "bridge": [], "risks": []}
        intent = "build a tiny url-signing playground"
        a = synthesize.build_architecture_prompt(
            self.manifest, self.metas, intent=intent)
        g = synthesize.build_glue_prompt(
            self.manifest, arch, intent=intent)
        t = synthesize.build_test_prompt(
            self.manifest, arch, {"app.py": "x=1"}, intent=intent)
        for msgs in (a, g, t):
            assert self._payload(msgs)["user_intent"] == intent

    def test_intent_bounded_and_empty_honest(self):
        long_intent = "x" * 5000
        a = synthesize.build_architecture_prompt(
            self.manifest, self.metas, intent=long_intent)
        assert len(self._payload(a)["user_intent"]) == \
            synthesize.MAX_INTENT_CHARS
        a2 = synthesize.build_architecture_prompt(self.manifest,
                                                  self.metas)
        assert self._payload(a2)["user_intent"] == ""

    def test_run_local_envelope_is_a_mechanical_ceiling(self):
        out = os.path.join(self.tmp, "run")
        os.makedirs(os.path.join(out, "fused_app"))
        env_file = os.path.join(self.tmp, "env.json")
        with open(env_file, "w") as f:
            json.dump({"max_calls": 1, "max_count_calls": 1}, f)
        fake = FakeProvider()
        orig = (model_api.count_tokens, model_api.chat_completion)
        model_api.count_tokens = fake.count_tokens
        model_api.chat_completion = fake.chat_completion
        try:
            res = synthesize.run_synthesis(
                self.manifest, self.metas, out,
                env={"MODEL_API_KEY": "fixture-key-not-real"},
                envelope_path=env_file)
        finally:
            model_api.count_tokens, model_api.chat_completion = orig
        # 1-call envelope: the probe consumes it; architecture must
        # refuse mechanically - not by policy, by the ledger
        assert res["status"] == "failed", res
        assert "BudgetExceeded" in res["detail"]
        assert fake.chat_calls == 1

    def test_missing_envelope_file_fails_closed(self):
        out = os.path.join(self.tmp, "run2")
        os.makedirs(os.path.join(out, "fused_app"))
        from repofuse.budget import BudgetExceeded
        try:
            synthesize.run_synthesis(
                self.manifest, self.metas, out,
                env={"MODEL_API_KEY": "fixture-key-not-real"},
                envelope_path=os.path.join(self.tmp, "nope.json"))
            assert False, "must refuse"
        except BudgetExceeded as e:
            assert "missing" in str(e)
