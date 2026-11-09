"""V31 pipeline corrections: vendor import aliasing, generation contract
naming (app.py + package-qualified imports), spawn_secrets secret
provisioning, and keyed-run state persistence/rehydration. All offline;
no provider calls."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location(
    "studio_serve_v31", os.path.join(ROOT, "studio", "serve.py"))
serve = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = serve
_argv = sys.argv
sys.argv = ["serve.py"]
try:
    spec.loader.exec_module(serve)
finally:
    sys.argv = _argv

from repofuse import serving, synthesize  # noqa: E402
from repofuse.vendor import IMPORT_SHIM  # noqa: E402


# ---------- vendor shim aliasing ----------

def test_shim_binds_real_package_not_namespace(tmp_path):
    """`from vendor import <slug>` must bind the REAL vendored package,
    never the repo-checkout directory imported as a namespace package."""
    vend = tmp_path / "vendor"
    (vend / "fakepkg").mkdir(parents=True)
    (vend / "__init__.py").write_text(IMPORT_SHIM)
    (vend / "fakepkg" / "__init__.py").write_text("MARKER = 'real'\n")
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from vendor import fakepkg\n"
        "assert getattr(fakepkg, 'MARKER', None) == 'real', fakepkg\n"
        "assert 'vendor.fakepkg' in sys.modules\n"
        "print('ok')\n" % str(tmp_path))
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_shim_skips_slugs_without_matching_package(tmp_path):
    """A slug whose top-level package has a different name keeps the
    path-shim behavior only; aliasing must not fail or invent a module."""
    vend = tmp_path / "vendor"
    (vend / "some-repo" / "realname").mkdir(parents=True)
    (vend / "__init__.py").write_text(IMPORT_SHIM)
    (vend / "some-repo" / "realname" / "__init__.py").write_text("X = 1\n")
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import vendor\n"
        "import realname\n"
        "assert realname.X == 1\n"
        "assert 'vendor.some-repo' not in sys.modules\n"
        "print('ok')\n" % str(tmp_path))
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_shim_binds_surface_for_hyphenated_slug(tmp_path):
    """A directory name that is not a Python identifier is imported
    through its read-only surface: from vendor import some_repo."""
    vend = tmp_path / "vendor"
    (vend / "some-repo").mkdir(parents=True)
    (vend / "surfaces").mkdir()
    (vend / "__init__.py").write_text(IMPORT_SHIM)
    (vend / "surfaces" / "__init__.py").write_text("")
    (vend / "surfaces" / "some_repo.py").write_text(
        "def exports():\n    return ['Token']\n")
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from vendor import some_repo\n"
        "assert some_repo.exports() == ['Token']\n"
        "assert 'vendor.some-repo' not in sys.modules\n"
        "print('ok')\n" % str(tmp_path))
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


# ---------- spawn_secrets contract validation ----------

def _contract_tree(tmp_path, contract):
    gen = tmp_path / "generated"
    gen.mkdir()
    (gen / "app.py").write_text(
        "def app(environ, start_response):\n    pass\n")
    (tmp_path / "serving.json").write_text(json.dumps(contract))
    return str(tmp_path)


def _base_contract():
    return {"version": 1, "kind": "python-wsgi", "module": "generated.app",
            "app_object": "app"}


def test_contract_spawn_secrets_generator_accepted(tmp_path):
    c = _base_contract()
    c["spawn_secrets"] = {"REPOFUSE_APP_SECRET": "random-hex-32"}
    ok, out = serving.load_contract(_contract_tree(tmp_path, c))
    assert ok, out
    assert out["spawn_secrets"] == {"REPOFUSE_APP_SECRET": "random-hex-32"}


def test_contract_without_spawn_secrets_still_valid(tmp_path):
    ok, out = serving.load_contract(_contract_tree(tmp_path,
                                                   _base_contract()))
    assert ok, out
    assert out["spawn_secrets"] == {}


def test_contract_literal_secret_refused(tmp_path):
    c = _base_contract()
    c["spawn_secrets"] = {"REPOFUSE_APP_SECRET": "hunter2-literal"}
    ok, reason = serving.load_contract(_contract_tree(tmp_path, c))
    assert not ok
    assert "never allowed" in reason


def test_contract_bad_secret_key_refused(tmp_path):
    c = _base_contract()
    c["spawn_secrets"] = {"lower; rm -rf": "random-hex-32"}
    ok, reason = serving.load_contract(_contract_tree(tmp_path, c))
    assert not ok
    assert "env name" in reason


def test_contract_spawn_secrets_non_object_refused(tmp_path):
    c = _base_contract()
    c["spawn_secrets"] = ["REPOFUSE_APP_SECRET"]
    ok, reason = serving.load_contract(_contract_tree(tmp_path, c))
    assert not ok
    assert "object" in reason


def test_contract_env_still_refused(tmp_path):
    c = _base_contract()
    c["env"] = {"REPOFUSE_APP_SECRET": "random-hex-32"}
    ok, reason = serving.load_contract(_contract_tree(tmp_path, c))
    assert not ok
    assert "NO custom environment" in reason


# ---------- runner snippet ----------

def test_runner_generates_secret_fresh_and_carries_no_literal(tmp_path):
    c = _base_contract()
    c["spawn_secrets"] = {"REPOFUSE_APP_SECRET": "random-hex-32"}
    ok, contract = serving.load_contract(_contract_tree(tmp_path, c))
    assert ok
    snippet = serving.runner_snippet(contract, 3)
    assert "_os.environ['REPOFUSE_APP_SECRET'] = _os.urandom(32).hex()" in \
        snippet
    assert "import os as _os" in snippet
    # the only occurrence of the env name is the generator line itself
    assert snippet.count("REPOFUSE_APP_SECRET") == 1


def test_runner_without_secrets_unchanged_shape(tmp_path):
    ok, contract = serving.load_contract(_contract_tree(tmp_path,
                                                        _base_contract()))
    assert ok
    snippet = serving.runner_snippet(contract, 3)
    assert "_os.urandom" not in snippet
    assert snippet.startswith("import ctypes as _c\n")


# ---------- derive_contract ----------

def test_derive_contract_includes_standard_spawn_secret(tmp_path):
    gen = tmp_path / "generated"
    gen.mkdir()
    (gen / "app.py").write_text(
        "def app(environ, start_response):\n    pass\n")
    contract, reason = serving.derive_contract(str(tmp_path))
    assert reason is None
    assert contract["module"] == "generated.app"
    assert contract["spawn_secrets"] == {
        "REPOFUSE_APP_SECRET": "random-hex-32"}
    on_disk = json.loads((tmp_path / "serving.json").read_text())
    assert on_disk == contract


# ---------- generation prompts ----------

def _manifest():
    return {"conflicts": [], "acceptance_criteria": [],
            "qualification_contract": None}


def test_glue_prompt_states_naming_and_usability_contract():
    msgs = synthesize.build_glue_prompt(_manifest(), {"bridge": "x"})
    payload = msgs[1]["content"]
    assert "Write ONLY integration.py" in payload
    assert "describe()" in payload
    assert "compute(payload" in payload
    assert "assistant-authored fixed HTTP/UI shell" in payload
    assert "BOTH-REPOSITORY" in payload
    assert "No app.py, no server, no routes" in payload
    assert "supported_product_boundary" in payload


def test_test_prompt_states_import_and_flow_contract():
    msgs = synthesize.build_test_prompt(
        _manifest(), {"bridge": "x"},
        {"generated/integration.py": "src", "generated/app.py": "shell"})
    payload = msgs[1]["content"]
    assert "from vendor import <slug>" in payload
    assert "from generated import <name>" in payload
    assert "REPOFUSE_APP_SECRET" in payload
    assert "generated/app.py" in payload
    assert "create-then-use flow" in payload
    assert "/api/describe" in payload
    assert "/api/run" in payload
    assert "integration.compute" in payload


def test_write_files_refuses_model_init(tmp_path):
    fusion = str(tmp_path)
    written = synthesize._write_files(
        fusion, {"__init__.py": "# model attempt\n",
                 "generated/__init__.py": "# prefixed attempt\n",
                 "real.py": "X = 1\n"}, "m", "t", slot="glue")
    assert written == ["generated/real.py"]
    assert not os.path.exists(os.path.join(fusion, "generated",
                                           "__init__.py"))


# ---------- run-state persistence ----------

def test_run_state_persist_and_rehydrate(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    run = {"run_id": "run-0123456789abcdef", "status": "build_verified",
           "events": [], "repo_a": "https://github.com/a/x",
           "repo_b": "https://github.com/b/y", "recorded_pair": False,
           "vendor": {"a": {"commit": "c"}}, "safety": {"status": "pass"}}
    serve.emit(run, "s", "info", "hello")
    state_file = tmp_path / "run-0123456789abcdef-state.json"
    assert state_file.is_file()
    blob = json.loads(state_file.read_text())
    assert blob["status"] == "build_verified"
    assert blob["events"][0]["text"] == "hello"

    serve._runs.pop("run-0123456789abcdef", None)
    serve._rehydrate_runs()
    back = serve._runs["run-0123456789abcdef"]
    assert back["status"] == "build_verified"
    assert back["repo_a"] == "https://github.com/a/x"
    assert back["rehydrated"] is True
    assert back["events"][0]["text"] == "hello"
    serve._runs.pop("run-0123456789abcdef", None)


def test_rehydrate_ignores_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    (tmp_path / "run-0123456789abcdef-state.json").write_text("{not json")
    (tmp_path / "not-a-run-state.json").write_text("{}")
    serve._rehydrate_runs()
    assert "run-0123456789abcdef" not in serve._runs
    assert "not-a-run" not in serve._runs


# ---------- V31r1: reviewer-requested allowlist + authority stress ----------

@pytest.mark.parametrize("name", ["PATH", "PYTHONPATH", "LD_PRELOAD",
                                  "HOME", "TMPDIR", "MODEL_API_KEY",
                                  "BROWSER", "SHELL"])
def test_spawn_secret_allowlist_blocks_execution_control_names(tmp_path,
                                                               name):
    c = _base_contract()
    c["spawn_secrets"] = {name: "random-hex-32"}
    ok, reason = serving.load_contract(_contract_tree(tmp_path, c))
    assert not ok
    assert "allowlist" in reason


def test_rehydrated_state_cannot_manufacture_spend_authority(tmp_path,
                                                             monkeypatch):
    """A tampered state file claiming safety + pins rehydrates into a run
    that STILL fails the spend gate: the gate demands the out-of-band ack
    file bound to the exact verdict hash, which state cannot supply."""
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    monkeypatch.setattr(serve, "ACKS", str(tmp_path / "no-acks"))
    verdict = {"status": "warn",
               "repos": [{"repo": "a/x", "status": "warn",
                          "commit": "c" * 40, "checks": [],
                          "queries_made": 1}],
               "queries_made": 1}
    blob = {"run_id": "run-0123456789abcdef", "status": "build_verified",
            "safety": verdict,
            "events": [{"stage": "ingest",
                        "data": {"slug": "a/x", "commit": "c" * 40}}]}
    (tmp_path / "run-0123456789abcdef-state.json").write_text(
        json.dumps(blob))
    serve._runs.pop("run-0123456789abcdef", None)
    serve._rehydrate_runs()
    run = serve._runs["run-0123456789abcdef"]
    ok, reason = serve.spend_safety_gate(run)
    assert not ok, "rehydrated state alone must never authorize spend"
    serve._runs.pop("run-0123456789abcdef", None)


def test_rehydration_drops_unrecognized_state_keys(tmp_path, monkeypatch):
    """A state file smuggling envelope/budget/ack-shaped keys has them
    dropped: rehydration copies a fixed informational field set only, so
    envelope and ledger authority stay with their own files."""
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    blob = {"run_id": "run-0123456789abcdef", "status": "build_verified",
            "events": [], "envelope": {"max_calls": 999},
            "budget_override": True, "ack": {"verdict_hash": "f" * 64}}
    (tmp_path / "run-0123456789abcdef-state.json").write_text(
        json.dumps(blob))
    serve._runs.pop("run-0123456789abcdef", None)
    serve._rehydrate_runs()
    run = serve._runs["run-0123456789abcdef"]
    for key in ("envelope", "budget_override", "ack"):
        assert key not in run
    serve._runs.pop("run-0123456789abcdef", None)


# ---------- V31r2: reviewer hardening - rehydrated runs need the bound ack ----------

def _rehydrate_with_verdict(tmp_path, monkeypatch, status):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    acks = tmp_path / "acks"
    acks.mkdir()
    monkeypatch.setattr(serve, "ACKS", str(acks))
    verdict = {"status": status,
               "repos": [{"repo": "a/x", "status": status,
                          "commit": "c" * 40, "checks": [],
                          "queries_made": 1}],
               "queries_made": 1}
    blob = {"run_id": "run-0123456789abcdef", "status": "build_verified",
            "safety": verdict,
            "events": [{"stage": "ingest",
                        "data": {"slug": "a/x", "commit": "c" * 40}}]}
    (tmp_path / "run-0123456789abcdef-state.json").write_text(
        json.dumps(blob))
    serve._runs.pop("run-0123456789abcdef", None)
    serve._rehydrate_runs()
    run = serve._runs["run-0123456789abcdef"]
    return run, verdict, acks


def _write_ack(acks, run_id, verdict, commits, verdict_hash=None):
    import hashlib as _hl
    blob = json.dumps(verdict, sort_keys=True).encode()
    rec = {"run_id": run_id, "commits": commits,
           "verdict_hash": verdict_hash or _hl.sha256(blob).hexdigest(),
           "reviewer": "independent-reviewer"}
    (acks / f"{run_id}.json").write_text(json.dumps(rec))


def test_rehydrated_forged_pass_without_ack_refused(tmp_path, monkeypatch):
    run, _, _ = _rehydrate_with_verdict(tmp_path, monkeypatch, "pass")
    ok, reason = serve.spend_safety_gate(run)
    assert not ok
    assert "rehydrated" in reason
    serve._runs.pop("run-0123456789abcdef", None)


def test_rehydrated_pass_with_valid_bound_ack_allowed(tmp_path, monkeypatch):
    run, verdict, acks = _rehydrate_with_verdict(tmp_path, monkeypatch,
                                                 "pass")
    _write_ack(acks, "run-0123456789abcdef", verdict, {"a/x": "c" * 40})
    ok, reason = serve.spend_safety_gate(run)
    assert ok, reason
    serve._runs.pop("run-0123456789abcdef", None)


def test_rehydrated_pass_with_mismatched_ack_refused(tmp_path, monkeypatch):
    run, verdict, acks = _rehydrate_with_verdict(tmp_path, monkeypatch,
                                                 "pass")
    _write_ack(acks, "run-0123456789abcdef", verdict, {"a/x": "d" * 40})
    ok, reason = serve.spend_safety_gate(run)
    assert not ok
    assert "pins" in reason
    serve._runs.pop("run-0123456789abcdef", None)


def test_live_pass_run_still_needs_no_ack(tmp_path, monkeypatch):
    """Live (non-rehydrated) PASS runs are unchanged: no ack required."""
    monkeypatch.setattr(serve, "ACKS", str(tmp_path / "no-acks"))
    run = {"run_id": "run-live000000000001",
           "safety": {"status": "pass",
                      "repos": [{"repo": "a/x", "status": "pass",
                                 "commit": "c" * 40, "checks": [],
                                 "queries_made": 1}],
                      "queries_made": 1},
           "events": [{"stage": "ingest",
                       "data": {"slug": "a/x", "commit": "c" * 40}}]}
    ok, reason = serve.spend_safety_gate(run)
    assert ok, reason


def test_rehydrated_transitional_status_becomes_interrupted(tmp_path,
                                                            monkeypatch):
    """A persisted 'running'/'resuming' means the server died mid-run;
    rehydration must not revive a worker that no longer exists."""
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    for i, st in enumerate(("running", "resuming")):
        rid = f"run-0123456789abcde{i}"
        (tmp_path / f"{rid}-state.json").write_text(json.dumps(
            {"run_id": rid, "status": st, "events": []}))
    (tmp_path / "run-ffffffffffffffff-state.json").write_text(json.dumps(
        {"run_id": "run-ffffffffffffffff",
         "status": "stopped_at_paid_boundary", "events": []}))
    serve._rehydrate_runs()
    assert serve._runs["run-0123456789abcde0"]["status"] == "interrupted"
    assert serve._runs["run-0123456789abcde1"]["status"] == "interrupted"
    assert (serve._runs["run-ffffffffffffffff"]["status"]
            == "stopped_at_paid_boundary")
    for rid in ("run-0123456789abcde0", "run-0123456789abcde1",
                "run-ffffffffffffffff"):
        serve._runs.pop(rid, None)


# ---------------- V31r4: exact request-payload retention + interrupted
# transition guard ----------------

_V31R4_MANIFEST = {"repos": [{"slug": "a", "role": "interface",
                              "exports": ["App"], "routes": [],
                              "dependency_count": 0}],
                   "boundary_candidates": [], "conflicts": []}
_V31R4_METAS = [{"slug": "a", "readme_excerpt": "", "tree": []}]


def _v31r4_fake_provider(captured):
    def fake_count(messages, **k):
        return max(1, sum(len(m["content"]) for m in messages) // 4)

    def fake_chat(messages, **k):
        captured.append((messages, k))
        joined = " ".join(m["content"] for m in messages)
        if "Reply with the word" in joined:
            content = "ready"
        elif "architecture bridge manifest" in joined:
            content = json.dumps({
                "source_exports": {"a": ["App"]},
                "arbitrage_opportunity": "x",
                "required_shims": [], "bridge": [], "risks": []})
        elif "Write ONLY integration.py" in joined:
            content = json.dumps({"integration.py":
                                  "def describe():\n"
                                  "    return {'title': 'Fixture',\n"
                                  "            'description': 'Offline',\n"
                                  "            'example': {}}\n"
                                  "def compute(payload):\n"
                                  "    return payload\n"})
        elif "integration test file" in joined:
            content = json.dumps({"test_fused.py": "import unittest\n"})
        else:
            raise AssertionError("unexpected prompt in fake provider")
        return {"content": content, "model": "muse-spark-1.3",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "latency_ms": 1, "finish_reason": "stop"}

    return fake_count, fake_chat


def test_every_step_request_payload_staged_exactly(tmp_path, monkeypatch):
    """V31r4: ALL four step request payloads (probe, architecture, glue,
    test) are retained under prompts/ BEFORE the count preflight, and the
    staged bytes equal build_payload(messages, exact call params) - the
    single constructor the live send path also uses."""
    from repofuse import model_api, synthesize as synth_mod
    captured = []
    fake_count, fake_chat = _v31r4_fake_provider(captured)
    monkeypatch.setattr(model_api, "count_tokens", fake_count)
    monkeypatch.setattr(model_api, "chat_completion", fake_chat)
    monkeypatch.setenv("MODEL_API_KEY", "offline-contract-test-key")
    res = synth_mod.run_synthesis(dict(_V31R4_MANIFEST),
                                  list(_V31R4_METAS), str(tmp_path),
                                  env=None)
    assert res["status"] == "completed", res
    steps = ["probe", "architecture-manifest", "glue-synthesis",
             "test-synthesis"]
    assert len(captured) == 4
    for (messages, kw), step in zip(captured, steps):
        staged = json.loads(
            (tmp_path / "prompts" / (step + ".json")).read_text())
        params = {k: kw[k] for k in
                  ("max_tokens", "reasoning_effort", "response_format")
                  if k in kw and kw[k] is not None}
        assert staged == model_api.build_payload(messages, **params), step


def test_free_path_stages_exact_arch_payload_without_key(tmp_path,
                                                         monkeypatch):
    """V31r4: the no-key free path still stages the architecture payload,
    now in exact-send format (model/messages/max_tokens/controls)."""
    from repofuse import synthesize as synth_mod
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    res = synth_mod.run_synthesis(dict(_V31R4_MANIFEST),
                                  list(_V31R4_METAS), str(tmp_path),
                                  env=None)
    assert res["status"] == "pending_no_key", res
    staged = json.loads(
        (tmp_path / "prompts" / "architecture-manifest.json").read_text())
    assert staged["model"]
    assert staged["max_tokens"] == synth_mod.RUN_ENVELOPE[
        "max_output_tokens"]
    assert staged["reasoning_effort"] == "minimal"
    assert staged["response_format"]["type"] == "json_schema"
    assert any("architecture bridge manifest" in m["content"]
               for m in staged["messages"])


def test_interrupted_spend_free_guard(tmp_path, monkeypatch):
    """V31r4: an interrupted run may start a general build only when its
    durable record proves zero provider contact (no reservations, no
    count calls, no retained responses); anything else refuses."""
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    fusion = tmp_path / "run-aaaaaaaabbbbcccc-fusion"
    fusion.mkdir()
    rid = "run-aaaaaaaabbbbcccc"
    assert serve._interrupted_run_is_spend_free(rid) is True
    (fusion / "budget.json").write_text(json.dumps(
        {"calls": [{"step": "probe", "actual": None}]}))
    assert serve._interrupted_run_is_spend_free(rid) is False
    (fusion / "budget.json").write_text(json.dumps(
        {"calls": [], "count_calls": [{"step": "probe"}]}))
    assert serve._interrupted_run_is_spend_free(rid) is False
    (fusion / "budget.json").unlink()
    raw = fusion / "raw_responses"
    raw.mkdir()
    (raw / "probe.json").write_text("{}")
    assert serve._interrupted_run_is_spend_free(rid) is False


def test_interrupted_guard_fails_closed_on_corrupt_ledger(tmp_path,
                                                          monkeypatch):
    """V31r5: corrupt or non-ledger budget.json is ambiguity, not absence
    - the guard fails closed. Same for an unreadable ledger/dir."""
    monkeypatch.setattr(serve, "RUNS", str(tmp_path))
    fusion = tmp_path / "run-aaaaaaaabbbbcccc-fusion"
    fusion.mkdir()
    rid = "run-aaaaaaaabbbbcccc"
    # corrupt JSON
    (fusion / "budget.json").write_text("{not json")
    assert serve._interrupted_run_is_spend_free(rid) is False
    # well-formed but not a ledger object
    (fusion / "budget.json").write_text(json.dumps([1, 2, 3]))
    assert serve._interrupted_run_is_spend_free(rid) is False
    # unreadable ledger file (PermissionError is OSError, not FileNotFound)
    (fusion / "budget.json").write_text(json.dumps({"calls": []}))
    os.chmod(fusion / "budget.json", 0)
    try:
        assert serve._interrupted_run_is_spend_free(rid) is False
    finally:
        os.chmod(fusion / "budget.json", 0o600)
    # genuinely absent again -> spend-free
    (fusion / "budget.json").unlink()
    assert serve._interrupted_run_is_spend_free(rid) is True
