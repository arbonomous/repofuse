"""The Studio vendor stage builds the fused tree from the SELECTED
repos' real pinned code (plan manifest + acceptance criteria + vendored
bytes + import shim) - free, inert, review-gated. Fixtures only: local
repos, no network, no paid calls, nothing executed."""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location(
    "studio_serve_vendor", os.path.join(ROOT, "studio", "serve.py"))
serve = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = serve
_argv = sys.argv
sys.argv = ["serve.py"]
try:
    spec.loader.exec_module(serve)
finally:
    sys.argv = _argv


def _fixture_repo(base, slug, package):
    d = base / slug
    (d / package).mkdir(parents=True)
    (d / package / "__init__.py").write_text("VALUE = 1\n")
    (d / "LICENSE").write_text("MIT License\n")
    return str(d)


def _metas(tmp_path):
    a = _fixture_repo(tmp_path, "alpha-src", "alphapkg")
    b = _fixture_repo(tmp_path, "beta-src", "betapkg")
    return {
        "alpha": {"url": "https://github.com/x/alpha", "slug": "alpha",
                  "path": a, "commit_sha": "a" * 40,
                  "license_guess": "MIT", "license_file": "LICENSE",
                  "tree": ["alphapkg/__init__.py", "LICENSE"],
                  "readme_excerpt": "alpha",
                  "analysis": {"slug": "alpha", "exports": ["VALUE"],
                               "routes": [], "env_vars": [], "ports": [],
                               "js_files": [],
                               "python_files": [{"file": "alphapkg/__init__.py",
                                                 "exports": ["VALUE"],
                                                 "imports": [],
                                                 "routes": []}],
                               "dependencies": {}}},
        "beta": {"url": "https://github.com/x/beta", "slug": "beta",
                 "path": b, "commit_sha": "b" * 40,
                 "license_guess": "MIT", "license_file": "LICENSE",
                 "tree": ["betapkg/__init__.py", "LICENSE"],
                 "readme_excerpt": "beta",
                 "analysis": {"slug": "beta", "exports": ["VALUE"],
                              "routes": [], "env_vars": [], "ports": [],
                              "js_files": [],
                              "python_files": [{"file": "betapkg/__init__.py",
                                                "exports": ["VALUE"],
                                                "imports": [],
                                                "routes": []}],
                              "dependencies": {}}},
    }


def _run():
    return {"run_id": "run-vendor00", "events": []}


def test_stage_vendors_selected_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    run = _run()
    assert serve._vendor_stage(run, run["run_id"], _metas(tmp_path))
    fdir = tmp_path / "runs" / "run-vendor00-fusion"
    assert (fdir / "fused_app" / "vendor" / "alpha" / "alphapkg"
            / "__init__.py").is_file()
    assert (fdir / "fused_app" / "vendor" / "beta" / "betapkg"
            / "__init__.py").is_file()
    assert (fdir / "fused_app" / "vendor" / "__init__.py").is_file()
    manifest = json.loads((fdir / "vendor_manifest.json").read_text())
    assert len(manifest["repos"]) == 2
    assert manifest["hashes_readback_verified"] is True
    assert (fdir / "fuse_manifest.json").is_file()
    assert (fdir / "acceptance.json").is_file()
    done = [e for e in run["events"]
            if e["kind"] == "stage_done" and e["stage"] == "vendor"]
    assert done and "inert" in done[0]["text"]
    assert run["vendor"]["files"] == len(manifest["hashes"])


def test_stage_declares_dry_run_not_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    run = _run()
    assert serve._vendor_stage(run, run["run_id"], _metas(tmp_path))
    texts = " ".join(e["text"] for e in run["events"])
    assert "PREPARED" in texts and "NOT sent" in texts
    assert "dry run, not a generated app" in texts
    assert "INERT" in texts


def test_nothing_executes_vendored_code(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    run = _run()
    assert serve._vendor_stage(run, run["run_id"], _metas(tmp_path))
    vendor = tmp_path / "runs" / "run-vendor00-fusion" / "fused_app" / "vendor"
    for base, dirs, files in os.walk(vendor):
        assert "__pycache__" not in dirs
        assert not any(f.endswith(".pyc") for f in files)


def test_slug_collision_fails_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    metas = _metas(tmp_path)
    metas["beta"]["slug"] = "alpha"  # collision, different url
    run = _run()
    assert not serve._vendor_stage(run, run["run_id"], metas)
    errs = [e for e in run["events"] if e["kind"] == "error"]
    assert errs and "vendoring failed honestly" in errs[0]["text"]


def _prepare_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    run = _run()
    assert serve._vendor_stage(run, run["run_id"], _metas(tmp_path))
    serve._runs[run["run_id"]] = run
    return run


def test_prepare_bundle_for_picked_idea(tmp_path, monkeypatch):
    run = _prepare_fixture(tmp_path, monkeypatch)
    card = {"title": "Signing playground",
            "what": "Sign and verify payloads in a tiny UI",
            "fit": ["BadData", "Markup"]}
    ok, lines = serve.prepare_bundle_for_idea(run["run_id"], card)
    assert ok, lines
    bundle = json.loads(
        (tmp_path / "runs" / f"{run['run_id']}-fusion" / "prompts"
         / "architecture-manifest.json").read_text())
    payload = json.loads(bundle[1]["content"])
    assert "Signing playground" in payload["user_intent"]
    assert "Sign and verify payloads" in payload["user_intent"]
    assert "BadData" in payload["user_intent"]
    # dry run only: no generated files, no provider artifacts
    fusion = tmp_path / "runs" / f"{run['run_id']}-fusion" / "fused_app"
    assert not (fusion / "generated").exists()
    assert not (tmp_path / "runs" / f"{run['run_id']}-fusion"
                / "raw_responses").exists()
    # the run's event stream carries the honest lines
    texts = " ".join(e["text"] for e in run["events"])
    assert "NOT sent" in texts and "dry run" in texts


def test_prepare_bundle_unknown_run_and_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "RUNS", str(tmp_path / "runs"))
    ok, _ = serve.prepare_bundle_for_idea("run-00000000",
                                          {"title": "x"})
    assert not ok
    run = _run()
    serve._runs[run["run_id"]] = run
    ok, lines = serve.prepare_bundle_for_idea(run["run_id"],
                                              {"title": "x"})
    assert not ok and "no vendored fusion dir" in lines[0]


def test_prepare_bundle_empty_card_refused(tmp_path, monkeypatch):
    run = _prepare_fixture(tmp_path, monkeypatch)
    ok, lines = serve.prepare_bundle_for_idea(
        run["run_id"], {"title": " ", "what": ""})
    assert not ok and "no text to steer" in lines[0]
