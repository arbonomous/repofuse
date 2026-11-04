#!/usr/bin/env python3
"""Offline tests for the REVIEW GATE in serve.py - the actual boundary that
keeps unreviewed generated code from executing. No server, no network, no
model: pure manifest/hash logic plus the spawn-time re-hash refusal."""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve

APP_PY = ("from microdot import Microdot\n"
          "from peewee import SqliteDatabase\n"
          "app = Microdot()\n"
          "db = SqliteDatabase(None)\n"
          "MODELS = []\n")
TEST_PY = "print('acceptance placeholder')\n"

FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" - {detail}" if detail
                                                   and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _mk_app():
    d = tempfile.mkdtemp(prefix="rf-review-")
    os.makedirs(os.path.join(d, "generated"))
    with open(os.path.join(d, "generated", "app.py"), "w") as f:
        f.write(APP_PY)
    with open(os.path.join(d, "test_fused.py"), "w") as f:
        f.write(TEST_PY)
    return d


def _write_approval(approvals, run_id, files):
    os.makedirs(approvals, exist_ok=True)
    with open(os.path.join(approvals, f"{run_id}.json"), "w") as f:
        json.dump({"run_id": run_id, "files": files,
                   "reviewer": "agent-reviewer", "reviewed_at": "now"},
                  f)


def main():
    approvals = tempfile.mkdtemp(prefix="rf-approvals-")
    old_approvals, old_builds, old_spawn = (serve.APPROVALS,
                                            dict(serve._builds),
                                            serve._spawn_owned)
    serve.APPROVALS = approvals
    try:
        app_dir = _mk_app()
        files = serve._hash_tree(app_dir)
        check("hash manifest covers both generated files",
              files is not None and set(files) == set(serve.GENERATED_RELS)
              and files["generated/app.py"] ==
              hashlib.sha256(APP_PY.encode()).hexdigest())

        ok, f2, ap = serve._build_review_gate("run-x", app_dir)
        check("no manifest -> NOT approved (nothing would execute)",
              ok is False and f2 == files and ap is None)

        _write_approval(approvals, "run-x", files)
        ok, _, ap = serve._build_review_gate("run-x", app_dir)
        check("exact manifest -> approved", ok is True
              and ap.get("reviewer") == "agent-reviewer")

        wrong = dict(files)
        wrong["generated/app.py"] = "0" * 64
        _write_approval(approvals, "run-y", wrong)
        ok, _, _ = serve._build_review_gate("run-y", app_dir)
        check("mismatched sha -> NOT approved", ok is False)

        extra = dict(files); extra["generated/evil.py"] = "1" * 64
        _write_approval(approvals, "run-z", extra)
        ok, _, _ = serve._build_review_gate("run-z", app_dir)
        check("manifest with extra file key -> NOT approved", ok is False)

        os.remove(os.path.join(app_dir, "test_fused.py"))
        ok, f3, _ = serve._build_review_gate("run-x", app_dir)
        check("missing generated file -> NOT approved, manifest None",
              ok is False and f3 is None)

        # a NEW file appearing in the tree after approval invalidates it
        app_dir_n = _mk_app()
        _write_approval(approvals, "run-n", serve._hash_tree(app_dir_n))
        with open(os.path.join(app_dir_n, "generated", "helper.py"),
                  "w") as f:
            f.write("x = 1\n")
        ok, _, _ = serve._build_review_gate("run-n", app_dir_n)
        check("new file in tree after approval -> NOT approved",
              ok is False)

        # vendored dependencies are pinned too: tampering one invalidates
        app_dir_v = _mk_app()
        os.makedirs(os.path.join(app_dir_v, "vendor", "pkg"))
        with open(os.path.join(app_dir_v, "vendor", "pkg", "m.py"),
                  "w") as f:
            f.write("ok = 1\n")
        _write_approval(approvals, "run-v", serve._hash_tree(app_dir_v))
        ok, _, _ = serve._build_review_gate("run-v", app_dir_v)
        check("vendor tree covered by manifest -> approved", ok is True)
        with open(os.path.join(app_dir_v, "vendor", "pkg", "m.py"),
                  "a") as f:
            f.write("ok = 2\n")
        ok, _, _ = serve._build_review_gate("run-v", app_dir_v)
        check("tampered vendored dep -> NOT approved", ok is False)

        # inner run_id mismatch: a manifest naming another run is void
        app_dir_m = _mk_app()
        mm = serve._hash_tree(app_dir_m)
        os.makedirs(approvals, exist_ok=True)
        with open(os.path.join(approvals, "run-m.json"), "w") as f:
            json.dump({"run_id": "run-OTHER", "files": mm}, f)
        ok, _, _ = serve._build_review_gate("run-m", app_dir_m)
        check("manifest with wrong inner run_id -> NOT approved",
              ok is False)

        # persisted build-state loader: fail closed on every inconsistency
        root = tempfile.mkdtemp(prefix="rf-runs-")
        old_runs = serve.RUNS
        serve.RUNS = root
        try:
            br = os.path.join(root, "run-a1b2c3d4e5f60718-build")
            os.makedirs(br)
            good = {"run_id": "run-a1b2c3d4e5f60718",
                    "status": "awaiting_review",
                    "meta": {"prefix": "/items", "field": "text",
                             "app_name": "X", "entity": "item"}}
            serve._write_build_state(br, dict(good))
            check("valid persisted state loads",
                  (serve._load_build_state("run-a1b2c3d4e5f60718") or {})
                  .get("status") == "awaiting_review")
            bad = dict(good); bad["run_id"] = "run-9999999999999999"
            serve._write_build_state(br, bad)
            check("inner run_id mismatch -> state refused",
                  serve._load_build_state("run-a1b2c3d4e5f60718") is None)
            bad = dict(good); bad["status"] = "running"
            serve._write_build_state(br, bad)
            check("non-resumable status -> state refused",
                  serve._load_build_state("run-a1b2c3d4e5f60718") is None)
            bad = dict(good); bad["meta"] = {"prefix": "/items"}
            serve._write_build_state(br, bad)
            check("malformed meta -> state refused",
                  serve._load_build_state("run-a1b2c3d4e5f60718") is None)
            check("missing file -> state refused",
                  serve._load_build_state("run-b1b2c3d4e5f60718") is None)
            serve._write_build_state(br, dict(good))
            serve._update_build_state_status(br, "build_ready")
            check("status update persists",
                  serve._load_build_state("run-a1b2c3d4e5f60718")["status"]
                  == "build_ready")
        finally:
            serve.RUNS = old_runs

        # spawn-time re-hash: registered build whose bytes changed since
        # review must never reach the spawner
        app_dir2 = _mk_app()
        manifest = serve._hash_tree(app_dir2)
        calls = []
        serve._spawn_owned = lambda *a, **k: calls.append(a) or (None, None)
        serve._builds["run-tamper"] = {
            "dir": app_dir2, "prefix": "/items", "field": "text",
            "files": manifest, "proc": None, "port": None}
        with open(os.path.join(app_dir2, "generated", "app.py"),
                  "a") as f:
            f.write("# tampered after review\n")
        port = serve.ensure_build_backend("run-tamper")
        check("tampered build refused at spawn, spawner never called",
              port is None and calls == [])
        check("unknown run refused", serve.ensure_build_backend("run-nope")
              is None and calls == [])
    finally:
        serve.APPROVALS = old_approvals
        serve._builds.clear(); serve._builds.update(old_builds)
        serve._spawn_owned = old_spawn
        # FIXED functional acceptance: real reviewed notes example passes
        proc, port = serve._spawn_owned(
            serve.FUSED_APP, serve.NOTES_RUNNER, "/notes", "text",
            os.path.join(tempfile.mkdtemp(prefix="rf-fx-"), "db"))
        ok, detail = (serve._fixed_acceptance(
            f"http://127.0.0.1:{port}", "/notes", "text")
            if port else (False, "spawn failed"))
        if proc:
            proc.terminate()
        check("fixed acceptance passes against the real notes example",
              ok, detail)

        # an app whose update route is missing fails honestly at update
        d = tempfile.mkdtemp(prefix="rf-fxfail-")
        os.makedirs(os.path.join(d, "generated"))
        import shutil as _sh
        _sh.copytree(os.path.join(serve.FUSED_APP, "vendor"),
                     os.path.join(d, "vendor"))
        # a real peewee CRUD minus PUT: the spawn probe passes,
        # the fixed acceptance must fail at the update step
        with open(os.path.join(d, "generated", "app.py"), "w") as f:
            f.write("""from microdot import Microdot
from peewee import Model, SqliteDatabase, CharField

db = SqliteDatabase(None)

class Item(Model):
    text = CharField()
    class Meta:
        database = db
        table_name = "item"

MODELS = [Item]
app = Microdot()

@app.get("/items")
def l(request):
    return [{"id": i.id, "text": i.text} for i in Item.select()]

@app.post("/items")
def c(request):
    it = Item.create(text=(request.json or {}).get("text", ""))
    return {"id": it.id, "text": it.text}, 201

@app.get("/items/<int:iid>")
def r(request, iid):
    try:
        it = Item.get_by_id(iid)
        return {"id": it.id, "text": it.text}
    except Exception:
        return {"error": "not found"}, 404

@app.delete("/items/<int:iid>")
def dl(request, iid):
    try:
        it = Item.get_by_id(iid)
    except Exception:
        return {"error": "not found"}, 404
    it.delete_instance()
    return None, 204
""")
        proc, port = serve._spawn_owned(
            d, serve.BUILD_RUNNER, "/items", "text",
            os.path.join(tempfile.mkdtemp(prefix="rf-fxf-"), "db"))
        if port:
            ok, detail = serve._fixed_acceptance(
                f"http://127.0.0.1:{port}", "/items", "text")
            proc.terminate()
            check("app missing update fails fixed acceptance honestly",
                  not ok and "update" in detail, detail)
        else:
            check("app missing update fails fixed acceptance honestly",
                  False, "spawn/probe refused (fail-closed, but untested "
                  "acceptance path)")

    print(f"\n{len(FAILURES)} failures")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
