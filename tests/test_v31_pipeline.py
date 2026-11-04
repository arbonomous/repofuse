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
    assert "app.py defines a top-level WSGI" in payload
    assert "app(environ, start_response)" in payload
    assert "from generated import <name>" in payload
    assert "from vendor import <slug>" in payload
    assert "creates or mutates a resource" in payload
    assert "REPOFUSE_APP_SECRET" in payload
    assert "never hardcode a secret" in payload


def test_test_prompt_states_import_and_flow_contract():
    msgs = synthesize.build_test_prompt(_manifest(), {"bridge": "x"},
                                        {"generated/app.py": "src"})
    payload = msgs[1]["content"]
    assert "from vendor import <slug>" in payload
    assert "from generated import <name>" in payload
    assert "REPOFUSE_APP_SECRET" in payload
    assert "generated/app.py" in payload
    assert "create-then-use flow" in payload


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
