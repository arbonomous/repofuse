"""Fail-closed spend gate: every paid entrypoint must pass the safety
gate BEFORE any count/provider call. All fixtures, no network, no paid
calls. Reviewer finding (V24): warn/fail/unknown could previously spend
through direct build and un-acknowledged paid ideas."""
import hashlib
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "studio_serve_under_test", os.path.join(ROOT, "studio", "serve.py"))
serve = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = serve
_argv = sys.argv
sys.argv = ["serve.py"]  # module reads sys.argv[1] as PORT at import
try:
    spec.loader.exec_module(serve)
finally:
    sys.argv = _argv

PINS = {"alice/alpha": "a" * 40, "bob/beta": "b" * 40}


def _run(status="warn", with_safety=True, commit_override=None):
    repos = []
    for slug, commit in PINS.items():
        repos.append({
            "repo": slug, "status": status,
            "commit": commit_override or commit,
            "checks": [], "queries_made": 2,
        })
    run = {
        "run_id": "run-12345678",
        "events": [
            {"stage": "ingest", "data": {"slug": s, "commit": c}}
            for s, c in PINS.items()
        ],
    }
    if with_safety:
        run["safety"] = {"status": status, "repos": repos,
                         "queries_made": 4}
    return run


def _ack(tmp_path, run, monkeypatch, commits=None, verdict_hash=None):
    acks = tmp_path / "acks"
    acks.mkdir()
    monkeypatch.setattr(serve, "ACKS", str(acks))
    verdict = run["safety"]
    blob = json.dumps(verdict, sort_keys=True).encode()
    rec = {
        "run_id": run["run_id"],
        "commits": commits if commits is not None else PINS,
        "verdict_hash": (verdict_hash
                         or hashlib.sha256(blob).hexdigest()),
        "reviewer": "independent-reviewer",
    }
    (acks / f"{run['run_id']}.json").write_text(json.dumps(rec))
    return acks


def test_missing_verdict_refuses():
    ok, why = serve.spend_safety_gate(_run(with_safety=False))
    assert not ok and "no safety qualification" in why


def test_fail_refuses():
    ok, _ = serve.spend_safety_gate(_run("fail"))
    assert not ok


def test_unknown_refuses():
    ok, _ = serve.spend_safety_gate(_run("unknown"))
    assert not ok


def test_warn_without_ack_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "ACKS", str(tmp_path / "acks"))
    ok, why = serve.spend_safety_gate(_run("warn"))
    assert not ok and "independent reviewer acknowledgment" in why


def test_warn_with_valid_ack_passes(tmp_path, monkeypatch):
    run = _run("warn")
    _ack(tmp_path, run, monkeypatch)
    ok, _ = serve.spend_safety_gate(run)
    assert ok


def test_ack_wrong_verdict_hash_refuses(tmp_path, monkeypatch):
    run = _run("warn")
    _ack(tmp_path, run, monkeypatch, verdict_hash="0" * 64)
    ok, why = serve.spend_safety_gate(run)
    assert not ok and "current verdict bytes" in why


def test_ack_wrong_commits_refuses(tmp_path, monkeypatch):
    run = _run("warn")
    bad = dict(PINS, **{"alice/alpha": "c" * 40})
    _ack(tmp_path, run, monkeypatch, commits=bad)
    ok, why = serve.spend_safety_gate(run)
    assert not ok and "pins do not match" in why


def test_ack_wrong_run_id_refuses(tmp_path, monkeypatch):
    run = _run("warn")
    acks = _ack(tmp_path, run, monkeypatch)
    rec = json.loads((acks / "run-12345678.json").read_text())
    rec["run_id"] = "run-87654321"
    (acks / "run-12345678.json").write_text(json.dumps(rec))
    ok, why = serve.spend_safety_gate(run)
    assert not ok and "run_id mismatch" in why


def test_ack_in_browser_reachable_run_dir_ignored(tmp_path, monkeypatch):
    """An ack dropped where run artifacts live is never honored; only the
    out-of-band ACKS dir counts (the browser cannot self-approve)."""
    monkeypatch.setattr(serve, "ACKS", str(tmp_path / "acks"))
    run = _run("warn")
    run_dir = tmp_path / "runs" / "run-12345678"
    run_dir.mkdir(parents=True)
    verdict = run["safety"]
    blob = json.dumps(verdict, sort_keys=True).encode()
    (run_dir / "run-12345678.json").write_text(json.dumps({
        "run_id": run["run_id"], "commits": PINS,
        "verdict_hash": hashlib.sha256(blob).hexdigest()}))
    ok, _ = serve.spend_safety_gate(run)
    assert not ok


def test_verdict_not_bound_to_pins_refuses(tmp_path, monkeypatch):
    run = _run("warn", commit_override="d" * 40)
    ok, why = serve.spend_safety_gate(run)
    assert not ok and "not bound to this run's pinned commits" in why


def test_pass_status_allows_without_ack():
    ok, why = serve.spend_safety_gate(_run("pass"))
    assert ok and "pass" in why
