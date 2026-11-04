"""Bounded offline validation of the provider request/response contract
and the end-to-end paid-path orchestration, with ZERO live calls.

A contract-faithful fake replaces model_api.count_tokens /
chat_completion: it VALIDATES the request shape RepoFuse sends (messages
list of role/content dicts, model string, integer max_tokens <= 4096, key
present) and answers with the exact response shape the real client parses
(content/model/usage/latency_ms/finish_reason, integer usage tokens).

It then drives the REAL staged driver (arch -> glue -> test) over REAL
ingest/analyze/plan/vendor code against two tiny local fixture repos,
proving: checkpoint ordering (count before charged), durable ledger
transitions, raw paid-response retention, staged-state recovery, and the
truncation failure mode (finish_reason="length" -> TruncatedOutput, raw
retained, usage committed, and a rerun fires ZERO provider requests).
"""
import json
import os
import sys
import tempfile
import unittest

from repofuse import ingest as ingest_mod
from repofuse import model_api
from repofuse import synthesize as synth_mod
from repofuse.qualification import target as qual_target

DRIVER_PATH = "/home/sandbox/run_qual_staged.py"


def make_fixture_repo(root, slug, module_body):
    import subprocess
    repo = os.path.join(root, slug)
    os.makedirs(repo)
    with open(os.path.join(repo, "LICENSE"), "w") as f:
        f.write("MIT License\n\nPermission is hereby granted, free of "
                "charge, to any person obtaining a copy\n")
    with open(os.path.join(repo, "README.md"), "w") as f:
        f.write(f"# {slug}\nA tiny offline fixture repo.\n")
    with open(os.path.join(repo, slug + ".py"), "w") as f:
        f.write(module_body)
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], cwd=repo, check=True)
    subprocess.run(git + ["add", "-A"], cwd=repo, check=True)
    subprocess.run(git + ["commit", "-qm", "fixture"], cwd=repo, check=True)
    return repo


class ContractFake:
    """Validates RepoFuse's outbound request contract; answers in the
    provider's response shape. Counts every invocation."""

    def __init__(self, arch_finish="stop"):
        self.count_calls = 0
        self.chat_calls = 0
        self.arch_finish = arch_finish

    def count_tokens(self, messages, model="muse-spark-1.3", timeout=30,
                     env=None):
        self.count_calls += 1
        self._check_messages(messages)
        assert isinstance(model, str) and model
        return sum(len(m["content"]) for m in messages) // 4

    def chat_completion(self, messages, model="muse-spark-1.3",
                        max_tokens=4096, timeout=60, base_url=None,
                        env=None):
        self.chat_calls += 1
        self._check_messages(messages)
        assert isinstance(max_tokens, int) and 1 <= max_tokens <= 4096
        assert (env or os.environ).get("MODEL_API_KEY") or \
               (env or os.environ).get("META_API_KEY"), "no key presented"
        joined = " ".join(m["content"] for m in messages)
        if "architecture bridge manifest" in joined:
            content = json.dumps({
                "source_exports": {"fixweb": ["App", "route"],
                                   "fixdb": ["Model", "connect"]},
                "arbitrage_opportunity": "web + db fusion",
                "required_shims": ["adapter"],
                "bridge": [{"from_repo": "fixweb", "from_export": "App",
                            "to_repo": "fixdb",
                            "to_route_or_input": "Model"}],
                "risks": ["none"],
            })
            finish = self.arch_finish
            if finish == "length":  # simulate the 2026-11-04 truncation
                content = content[:120]  # unterminated JSON
        elif "adapter shim code" in joined:
            content = json.dumps({"app_adapter.py":
                                  "# generated adapter\nVALUE = 1\n"})
            finish = "stop"
        else:  # test prompt
            content = json.dumps({"test_fused.py":
                                  "import unittest\n"})
            finish = "stop"
        prompt_chars = sum(len(m["content"]) for m in messages)
        return {"content": content, "model": model,
                "usage": {"prompt_tokens": prompt_chars // 4,
                          "completion_tokens": len(content) // 4},
                "latency_ms": 1, "finish_reason": finish}

    @staticmethod
    def _check_messages(messages):
        assert isinstance(messages, list) and messages
        for m in messages:
            assert set(m) == {"role", "content"}
            assert isinstance(m["role"], str) and isinstance(m["content"], str)


class E2EMockProvider(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(DRIVER_PATH):
            self.skipTest("staged driver not present in this environment")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_qual_staged",
                                                      DRIVER_PATH)
        self.drv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.drv)
        self.tmp = tempfile.mkdtemp(prefix="rf064-e2e-")
        # redirect the driver's durable paths
        self.drv.OUT = self.tmp
        self.drv.STATE = os.path.join(self.tmp, "staged_state.json")
        self.drv.ATTEST = os.path.join(self.tmp, "glue_review.attestation.json")
        # fixture repos through REAL ingest (local-path boundary only)
        root = os.path.join(self.tmp, "src")
        os.makedirs(root)
        web = make_fixture_repo(root, "fixweb", "class App:\n    pass\n")
        db = make_fixture_repo(root, "fixdb", "class Model:\n    pass\n")
        self._orig_target = qual_target.TARGET
        qual_target.TARGET = {
            "name": "offline-fixture", "contract": {"module": "x"},
            "inputs": {"fixweb": {"url": web, "commit": None,
                                  "license": "MIT"},
                       "fixdb": {"url": db, "commit": None,
                                 "license": "MIT"}}}
        self._orig_ingest = ingest_mod.ingest
        ingest_mod.ingest = lambda url, workdir, expected_sha=None, **k: \
            self._orig_ingest(url, workdir, allow_local=True)
        # staged state: probe satisfied (mirrors the real repaired state)
        with open(self.drv.STATE, "w") as f:
            json.dump({"status": "in_progress", "files_written": [],
                       "steps": {"probe": {"status": "ok"}}}, f)
        # fake provider + key
        self.fake = ContractFake()
        self._orig_count = model_api.count_tokens
        self._orig_chat = model_api.chat_completion
        model_api.count_tokens = self.fake.count_tokens
        model_api.chat_completion = self.fake.chat_completion
        os.environ["MODEL_API_KEY"] = "offline-contract-test-key"

    def tearDown(self):
        qual_target.TARGET = self._orig_target
        ingest_mod.ingest = self._orig_ingest
        model_api.count_tokens = self._orig_count
        model_api.chat_completion = self._orig_chat
        os.environ.pop("MODEL_API_KEY", None)

    def _stage(self, name):
        argv = sys.argv
        sys.argv = ["run_qual_staged.py", name]
        try:
            self.drv.main()
        finally:
            sys.argv = argv

    def test_full_paid_path_orchestration(self):
        self._stage("arch")
        self._stage("glue")
        self._stage("test")
        # durable ledger: 3 charged + 3 count, one per step, all committed
        b = json.load(open(os.path.join(self.tmp, "budget.json")))
        steps = [c["step"] for c in b["calls"]]
        self.assertEqual(steps, ["architecture-manifest", "glue-synthesis",
                                 "test-synthesis"])
        self.assertTrue(all(c["actual"] for c in b["calls"]))
        self.assertEqual([c["step"] for c in b["count_calls"]], steps)
        # staged-state recovery: every step done, files recorded
        st = json.load(open(self.drv.STATE))
        self.assertEqual([k for k, v in st["steps"].items() if v == "done"],
                         steps)
        # raw paid responses retained BEFORE parsing for every step
        for step in steps:
            raw = json.load(open(os.path.join(
                self.tmp, "raw_responses", step + ".json")))
            self.assertEqual(raw["finish_reason"], "stop")
            self.assertTrue(raw["content"])
        # artifacts: architecture, generated glue, generated test
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp, "architecture.json")))
        self.assertTrue(any(f.startswith("generated/")
                            for f in st["files_written"]))
        self.assertEqual(self.fake.count_calls, 3)
        self.assertEqual(self.fake.chat_calls, 3)

    def test_truncation_retains_raw_and_blocks_rerun(self):
        self.fake.arch_finish = "length"
        with self.assertRaises(SystemExit):  # driver records terminal, exits 2
            self._stage("arch")
        st_term = json.load(open(self.drv.STATE))
        self.assertEqual(st_term["steps"]["architecture-manifest"]["status"],
                         "failed_terminal")
        self.assertTrue(self.drv.next_action(st_term).startswith("TERMINAL"))
        # usage committed (the call was real), raw retained
        b = json.load(open(os.path.join(self.tmp, "budget.json")))
        self.assertEqual(len(b["calls"]), 1)
        self.assertIsNotNone(b["calls"][0]["actual"])
        raw = json.load(open(os.path.join(
            self.tmp, "raw_responses", "architecture-manifest.json")))
        self.assertEqual(raw["finish_reason"], "length")
        self.assertFalse(os.path.isfile(
            os.path.join(self.tmp, "architecture.json")))
        # a rerun fires ZERO provider requests of either kind; the driver
        # catches the budget refusal and re-records terminal state
        with self.assertRaises(SystemExit):
            self._stage("arch")
        st3 = json.load(open(self.drv.STATE))
        self.assertTrue(self.drv.next_action(st3).startswith("TERMINAL"))
        self.assertEqual(self.fake.count_calls, 1)
        self.assertEqual(self.fake.chat_calls, 1)


class ArchPromptBudget(unittest.TestCase):
    def test_arch_prompt_carries_output_budget(self):
        manifest = {"repos": [{"slug": "a", "role": "interface",
                               "exports": ["App"], "routes": ["/x"],
                               "dependency_count": 0},
                              {"slug": "b", "role": "storage",
                               "exports": ["Model"], "routes": [],
                               "dependency_count": 0}],
                    "boundary_candidates": [], "conflicts": []}
        metas = [{"slug": "a", "readme_excerpt": "x" * 5000,
                  "tree": [f"f{i}" for i in range(200)]},
                 {"slug": "b", "readme_excerpt": "y", "tree": []}]
        msgs = synth_mod.build_architecture_prompt(manifest, metas)
        body = msgs[1]["content"]
        self.assertIn(str(synth_mod.ARCH_OUTPUT_CHAR_BUDGET), body)
        self.assertIn(f"<= {synth_mod.ARCH_MAX_EXPORTS_PER_REPO}".replace(
            "<= ", "<="), body)
        # inputs trimmed: 5000-char readme cut to 800, 200-entry tree to 40
        self.assertNotIn("x" * 900, body)
        self.assertNotIn("f100", body)

    def test_arch_size_validator(self):
        from repofuse.budget import BudgetExceeded
        ok = {"source_exports": {"a": ["x"]}, "bridge": [],
              "required_shims": [], "risks": []}
        self.assertTrue(synth_mod.validate_architecture_size(ok))
        bloated = {"source_exports": {"a": [str(i) for i in range(50)]},
                   "bridge": [], "required_shims": [], "risks": []}
        with self.assertRaises(BudgetExceeded):
            synth_mod.validate_architecture_size(bloated)


if __name__ == "__main__":
    unittest.main()


class TerminalFailureHandling(unittest.TestCase):
    """0.6.5: truncation/size failures record a TERMINAL state, never a
    stale next_action that routes back into a burned step."""

    def _driver(self):
        import importlib.util
        if not os.path.isfile(DRIVER_PATH):
            self.skipTest("staged driver not present in this environment")
        spec = importlib.util.spec_from_file_location("run_qual_staged",
                                                      DRIVER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_run_synthesis_truncation_is_terminal(self):
        from repofuse.budget import Budget  # noqa: F401
        tmp = tempfile.mkdtemp(prefix="rf065-term-")
        manifest = {"repos": [{"slug": "a", "role": "interface",
                               "exports": ["App"], "routes": [],
                               "dependency_count": 0}],
                    "boundary_candidates": [], "conflicts": []}
        metas = [{"slug": "a", "readme_excerpt": "", "tree": []}]
        fake = ContractFake(arch_finish="length")
        orig_count, orig_chat = model_api.count_tokens, model_api.chat_completion
        model_api.count_tokens = fake.count_tokens
        model_api.chat_completion = fake.chat_completion
        os.environ["MODEL_API_KEY"] = "offline-contract-test-key"
        try:
            res = synth_mod.run_synthesis(manifest, metas, tmp, env=None)
        finally:
            model_api.count_tokens, model_api.chat_completion = orig_count, orig_chat
            os.environ.pop("MODEL_API_KEY", None)
        self.assertEqual(res["status"], "failed_truncated")
        self.assertIn("max_tokens cap", res["detail"])
        # raw retained, usage committed
        raw = json.load(open(os.path.join(
            tmp, "raw_responses", "architecture-manifest.json")))
        self.assertEqual(raw["finish_reason"], "length")
        b = json.load(open(os.path.join(tmp, "budget.json")))
        arch = [c for c in b["calls"] if c["step"] == "architecture-manifest"]
        self.assertIsNotNone(arch[0]["actual"])
        # glue never fired
        self.assertFalse(any(c["step"] == "glue-synthesis"
                             for c in b["calls"]))

    def test_run_synthesis_oversized_architecture_rejected(self):
        tmp = tempfile.mkdtemp(prefix="rf065-bloat-")
        manifest = {"repos": [{"slug": "a", "role": "interface",
                               "exports": ["App"], "routes": [],
                               "dependency_count": 0}],
                    "boundary_candidates": [], "conflicts": []}
        metas = [{"slug": "a", "readme_excerpt": "", "tree": []}]
        fake = ContractFake()
        bloated = json.dumps({
            "source_exports": {"a": [str(i) for i in range(50)]},
            "arbitrage_opportunity": "x", "required_shims": [],
            "bridge": [], "risks": []})
        orig_chat = model_api.chat_completion
        orig_count = model_api.count_tokens

        def chat(messages, **k):
            r = fake.chat_completion(messages, **k)
            if "architecture bridge manifest" in \
                    " ".join(m["content"] for m in messages):
                r["content"] = bloated
            return r

        model_api.count_tokens = fake.count_tokens
        model_api.chat_completion = chat
        os.environ["MODEL_API_KEY"] = "offline-contract-test-key"
        try:
            res = synth_mod.run_synthesis(manifest, metas, tmp, env=None)
        finally:
            model_api.count_tokens = orig_count
            model_api.chat_completion = orig_chat
            os.environ.pop("MODEL_API_KEY", None)
        self.assertEqual(res["status"], "failed")
        self.assertIn("source_exports", res["detail"])
        b = json.load(open(os.path.join(tmp, "budget.json")))
        self.assertFalse(any(c["step"] == "glue-synthesis"
                             for c in b["calls"]))

    def test_driver_records_terminal_and_stops_routing(self):
        drv = self._driver()
        tmp = tempfile.mkdtemp(prefix="rf065-drv-")
        st = {"status": "in_progress", "files_written": [],
              "steps": {"probe": {"status": "ok"}}}
        drv.STATE = os.path.join(tmp, "staged_state.json")
        drv.save_state(st)
        with self.assertRaises(SystemExit):
            drv.fail_terminal(st, "architecture-manifest",
                              synth_mod.TruncatedOutput("hit cap"))
        st2 = json.load(open(drv.STATE))
        self.assertEqual(st2["status"], "failed_terminal")
        self.assertEqual(
            st2["steps"]["architecture-manifest"]["status"],
            "failed_terminal")
        self.assertTrue(drv.next_action(st2).startswith("TERMINAL"))

    def test_driver_next_action_terminal(self):
        drv = self._driver()
        st = {"status": "failed_terminal", "files_written": [],
              "steps": {"probe": {"status": "ok"},
                        "architecture-manifest":
                            {"status": "failed_terminal",
                             "detail": "TruncatedOutput: hit cap"}}}
        nxt = drv.next_action(st)
        self.assertTrue(nxt.startswith("TERMINAL"), nxt)
        self.assertIn("no retries", nxt)
