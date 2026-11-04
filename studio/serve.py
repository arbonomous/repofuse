#!/usr/bin/env python3
"""RepoFuse Studio local server. Stdlib only, localhost only.

REAL capabilities:
1. POST /api/fuse - runs the actually-available, free pipeline stages on the
   pasted repos (real clone, real pin, real license check, real static
   analysis via the repofuse package - cloned code is READ, never executed),
   then STOPS at the paid boundary (no model call, no key).
2. /notes* - proxies to the real verified notes app it spawns itself from
   examples/notes-app-fusion/fused_app (assistant_ext imported), on a random
   loopback port, proven ours by a create/read/delete probe handshake.

Hardening (reviewer findings):
- Host header must be this server (DNS-rebinding protection); mutating
  requests with a cross-origin Origin header are refused.
- Static serving is an exact allowlist; no listing, no traversal, nothing
  else on disk is reachable.
- Repo URLs must be exact https://github.com/<owner>/<repo> (and ingest
  re-validates). file:, ssh, other hosts, option injection all refused.
- Routes are method-specific; /api/* has no PUT/DELETE alias.
- Bounded bodies, bounded concurrent runs, bounded retained runs, clones
  deleted when a run ends.
- Run ids are random; /api/run/<id> validates the format.
- Pipeline modules import lazily: if the repofuse package is missing the
  server still serves the UI/replay and /api/fuse fails with an honest error.
"""
import atexit
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ROOT)
FUSED_APP = os.path.join(REPO_ROOT, "examples", "notes-app-fusion", "fused_app")
RUNS = os.path.join(ROOT, "runs")
# Review manifests for generated builds. A build can NEVER write here:
# the dir lives outside every run dir and the pipeline only reads it.
APPROVALS = (os.environ.get("REPOFUSE_BUILD_APPROVALS")
             or os.path.join(ROOT, "build-approvals"))

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8317
LOCAL_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}", "[::1]:" + str(PORT)}
LOCAL_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

MAX_FUSE_BODY = 16 * 1024
MAX_NOTES_BODY = 64 * 1024
MAX_ACTIVE_RUNS = 2
MAX_RETAINED_RUNS = 10

STATIC = {
    "/": ("text/html; charset=utf-8", "index.html"),
    "/index.html": ("text/html; charset=utf-8", "index.html"),
    "/styles.css": ("text/css; charset=utf-8", "styles.css"),
    "/app.js": ("text/javascript; charset=utf-8", "app.js"),
    "/replay-data.js": ("text/javascript; charset=utf-8", "replay-data.js"),
    "/assets/repofuse-icon-clean.png": ("image/png",
                                        "assets/repofuse-icon-clean.png"),
    "/assets/repofuse-icon-dark.png": ("image/png",
                                       "assets/repofuse-icon-dark.png"),
    "/assets/repofuse-logo-lockup.png": ("image/png",
                                         "assets/repofuse-logo-lockup.png"),
}

REPO_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}"
    r"(?:\.git)?/?$")
RUN_ID = re.compile(r"^run-[0-9a-f]{16}$")
NOTES_PATH = re.compile(r"^/notes(/\d{1,9})?$")
BUILD_PATH = re.compile(r"^/build/(run-[0-9a-f]{16})(/[A-Za-z0-9_/.-]{0,120})?$")

RECORDED = {
    frozenset(("https://github.com/miguelgrinberg/microdot",
               "https://github.com/coleifer/peewee")),
}
RECORDED_PINS = {"microdot": "7742db9ff9f49635de3387145fafe56bf2377a97",
                 "peewee": "e9b55c96b0c1e5c13c0053205868f188af617945"}

_runs = {}
_lock = threading.Lock()
_active_runs = 0
_notes_proc = None
_notes_port = None


def _norm(url):
    return re.sub(r"/+$", "", (url or "").strip().lower()).removesuffix(".git")


def is_recorded_pair(a, b):
    return frozenset((_norm(a), _norm(b))) in RECORDED


def emit(run, stage, kind, text, data=None):
    ev = {"ts": time.time(), "stage": stage, "kind": kind, "text": text}
    if data:
        ev["data"] = data
    with _lock:
        run["events"].append(ev)


def _load_pipeline():
    """Lazy import: the UI and replay work even without the package."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from repofuse import analyze as analyze_mod    # noqa: PLC0415
    from repofuse import ingest as ingest_mod      # noqa: PLC0415
    return ingest_mod, analyze_mod


def run_pipeline(run_id, repo_a, repo_b, intent):
    global _active_runs
    with _lock:
        run = _runs[run_id]
    workdir = os.path.join(RUNS, run_id)
    try:
        try:
            ingest_mod, analyze_mod = _load_pipeline()
        except Exception as e:
            emit(run, "ingest", "error",
                 "repofuse package not importable from this checkout "
                 f"({e}); serve from a full repo clone: studio/run.sh")
            with _lock:
                run["status"] = "failed"
            return
        os.makedirs(workdir, exist_ok=True)
        metas = {}
        for url in (repo_a, repo_b):
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "-",
                          _norm(url).split("/")[-1] or "repo")
            emit(run, "ingest", "log", f"Cloning {url} ...")
            # Recorded repos are pinned to the exact qualification commits;
            # any other repo is pinned to whatever its default branch is NOW
            # and the run says so. No unpinned snapshots either way.
            pin = RECORDED_PINS.get(slug) if is_recorded_pair(repo_a, repo_b) \
                else None
            meta = ingest_mod.ingest(url, workdir, expected_sha=pin)
            if meta.get("clone_error"):
                emit(run, "ingest", "error",
                     f"{slug}: refused - {meta['clone_error']}")
                with _lock:
                    run["status"] = "failed"
                return
            metas[slug] = meta
            emit(run, "ingest", "log",
                 f"{slug}: pinned at {meta['commit_sha'][:12]}"
                 + (" (qualification pin)" if pin
                    else " (current HEAD, pinned now)"))
            emit(run, "ingest", "log",
                 f"{slug}: license {meta.get('license_guess') or 'NONE FOUND'}"
                 f" - {meta.get('license_note', '')}",
                 {"slug": slug, "commit": meta["commit_sha"],
                  "license": meta.get("license_guess"),
                  "tree": meta.get("tree", [])[:12]})
        emit(run, "ingest", "stage_done", "Both repos cloned, pinned, scanned.")

        for slug, meta in metas.items():
            emit(run, "analyze", "log", f"Extracting exports from {slug} ...")
            a = analyze_mod.analyze(meta)  # static reads only; no code exec
            metas[slug]["analysis"] = a
            emit(run, "analyze", "log",
                 f"{slug}: {len(a['exports'])} exports, "
                 f"{len(a['python_files'])} Python files",
                 {"slug": slug, "exports": a["exports"][:24]})
        emit(run, "analyze", "stage_done", "Exports mapped.")

        if not intent:
            # Ideas mode. PAID path (model-generated cards) only when an
            # envelope + key are really configured; every guard failure
            # falls back to the FREE deterministic analysis, labeled as
            # such. The two sources are never blended or mislabeled.
            try:
                import ideas as ideas_mod
                import ideas_ai
            except Exception as e:
                emit(run, "error", "error",
                     f"idea suggestion failed honestly: {e}")
                with _lock:
                    run["status"] = "failed"
                return
            cards, prov = None, None
            paid_attempt = None
            try:
                cards, prov = ideas_ai.suggest_with_model(metas, run_id)
            except ideas_ai.NotConfigured:
                pass  # paid path off: normal free mode, no note needed
            except ideas_ai.Refused as e:
                paid_attempt = {"spent": bool(e.spent), "reason": str(e)}
                emit(run, "ideas", "log",
                     "PAID idea-suggest refused "
                     + ("AFTER its one charged call fired (raw retained, "
                        "never retried)" if e.spent
                        else "before any spend")
                     + f": {e}. Showing the free local analysis instead.")
            except Exception as e:
                paid_attempt = {"spent": None, "reason": str(e)}
                emit(run, "ideas", "log",
                     f"paid idea path errored honestly: {e}. "
                     "Showing the free local analysis instead.")
            if cards is None:
                cards = ideas_mod.suggest(metas)
            if prov:
                emit(run, "ideas", "log",
                     f"Ideas generated by {prov['model']} - 1 paid call: "
                     f"{prov['usage']['input']} in / "
                     f"{prov['usage']['output']} out (provider count-check "
                     f"{prov['measured_input_tokens']}).")
            if prov:
                ideas_text = ("Build ideas generated by the model from "
                              "the actual analysis - 1 paid model call. "
                              "Pick one, or describe your own.")
            elif paid_attempt and paid_attempt["spent"] is True:
                ideas_text = ("1 paid model call was made and its output "
                              "was REJECTED (raw + rejection record "
                              "retained; never retried). These ideas are "
                              "derived locally from the actual exports "
                              "above. Pick one, or describe your own.")
            elif paid_attempt and paid_attempt["spent"] is None:
                ideas_text = ("The paid idea path errored; whether its "
                              "call was charged is UNKNOWN - check the "
                              "retained record before any retry. These "
                              "ideas are derived locally from the actual "
                              "exports above. Pick one, or describe "
                              "your own.")
            else:
                ideas_text = ("Build ideas derived locally from the "
                              "actual exports above - no model call. "
                              "Pick one, or describe your own.")
            emit(run, "ideas", "ideas", ideas_text,
                 {"cards": cards,
                  "source": prov["source"] if prov else "local-analysis",
                  "provenance": prov,
                  "paid_attempt": paid_attempt})
            with _lock:
                run["status"] = "ideas_ready"
            return

        # --- the paid boundary: everything below needs a model call ---
        emit(run, "architecture", "blocked",
             "Architecture synthesis needs a model call. Paid generation is "
             "disabled in this demo (no active grant, no API key). "
             "Everything above really ran: your repos were cloned, pinned, "
             "license-checked and analyzed just now. The recorded-run replay "
             "shows how the full pipeline went for the pinned "
             "microdot + peewee pair.")
        with _lock:
            run["status"] = "stopped_at_paid_boundary"
    except Exception as e:  # honest failure, never a pretend pass
        emit(run, "error", "error", f"pipeline error: {e}")
        with _lock:
            run["status"] = "failed"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # clones are transient
        with _lock:
            _active_runs -= 1
            while len(_runs) > MAX_RETAINED_RUNS:
                _runs.pop(next(iter(_runs)))


# ---------------- real notes backend (owned, probed) ----------------
def _fixed_acceptance(base, prefix, field):
    """FIXED functional acceptance - assistant-written, model-independent,
    checked in for review like everything else. Exercises the declared
    CRUD contract over real HTTP against the spawned reviewed app and
    fails on the first deviation. The model's own tests are a supporting
    signal, never proof; THIS is the verification bar."""
    tok = secrets.token_hex(6)
    v1, v2 = f"fx-{tok}-one", f"fx-{tok}-two"

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{base}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return 0, f"connection failed: {e}"

    st, created = call("POST", prefix, {field: v1})
    if st != 201 or not isinstance(created, dict) or "id" not in created:
        return False, f"create returned {st} {created!r} (want 201 + id)"
    iid = created["id"]
    st, lst = call("GET", prefix)
    if st != 200 or not isinstance(lst, list) or not any(
            isinstance(x, dict) and x.get("id") == iid
            and x.get(field) == v1 for x in lst):
        return False, "list did not return an array containing the " \
                      "created entity"
    st, got = call("GET", f"{prefix}/{iid}")
    if st != 200 or not isinstance(got, dict) or got.get(field) != v1:
        return False, f"read returned {st} (want 200 with the entity)"
    st, _ = call("PUT", f"{prefix}/{iid}", {field: v2})
    if st != 200:
        return False, f"update returned {st} (want 200)"
    st, got = call("GET", f"{prefix}/{iid}")
    if st != 200 or not isinstance(got, dict) or got.get(field) != v2:
        return False, "update was not persisted"
    st, _ = call("DELETE", f"{prefix}/{iid}")
    if st != 204:
        return False, f"delete returned {st} (want 204)"
    st, _ = call("GET", f"{prefix}/{iid}")
    if st != 404:
        return False, f"deleted entity still readable: {st}"
    return True, "create/list/read/update/delete + 404-after-delete, " \
                 "all exact"


def _verify_and_register(run, run_id, build_root, app_dir, meta):
    """The ONLY way generated bytes ever execute: re-hash the whole tree
    IMMEDIATELY before running anything, then verify in two layers - the
    model's own tests (supporting signal, reported honestly) and the
    FIXED model-independent contract acceptance (the actual bar).
    Register only on fixed-acceptance pass. Shared by the initial build
    and the bounded resume path. Never generates anything; fails closed
    with the run left awaiting review."""
    approved, files, approval = _build_review_gate(run_id, app_dir)
    if not approved:
        emit(run, "verify", "error",
             "Review manifest missing or bytes changed since review - "
             "refused to execute; the run stays awaiting review.")
        with _lock:
            run["status"] = "awaiting_review"
        _update_build_state_status(build_root, "awaiting_review")
        return
    emit(run, "verify", "log",
         "Source review matched these exact bytes (reviewer "
         f"{approval.get('reviewer', '?')}, "
         f"{approval.get('reviewed_at', '?')}). Two verification layers "
         "now run under the scrubbed child env (free stage): the model's "
         "own tests - a supporting signal, never proof - and the FIXED "
         "model-independent contract acceptance, which is the bar.")
    env = _child_env({
        "FUSED_DB_PATH": os.path.join(build_root, "verify.db"),
        "PYTHONPATH": app_dir})
    model_result = "not run"
    try:
        proc = subprocess.run([sys.executable, "test_fused.py"],
                              cwd=app_dir, env=env,
                              capture_output=True, text=True,
                              timeout=60)
        out = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
        if proc.returncode == 0:
            model_result = "passed"
            emit(run, "verify", "log",
                 "The model's own acceptance tests PASSED (supporting "
                 "signal only).")
        else:
            model_result = f"failed (exit {proc.returncode})"
            emit(run, "verify", "error",
                 f"The model's own acceptance tests FAILED (exit "
                 f"{proc.returncode}) - reported honestly, nothing "
                 f"repaired silently. Output tail: {out}")
    except subprocess.TimeoutExpired:
        model_result = "timed out"
        emit(run, "verify", "error",
             "The model's own acceptance tests timed out at 60s - "
             "reported honestly.")
    proc2, port = _spawn_owned(app_dir, BUILD_RUNNER, meta["prefix"],
                               meta["field"],
                               os.path.join(build_root, "accept"))
    if not port:
        emit(run, "verify", "error",
             "Could not spawn and probe the reviewed app for the fixed "
             "acceptance - build FAILED honestly.")
        with _lock:
            run["status"] = "build_failed"
        _update_build_state_status(build_root, "build_failed")
        return
    try:
        ok, detail = _fixed_acceptance(f"http://127.0.0.1:{port}",
                                       meta["prefix"], meta["field"])
    finally:
        proc2.terminate()
    if not ok:
        emit(run, "verify", "error",
             f"FIXED contract acceptance FAILED: {detail} - reported "
             "honestly, nothing repaired silently.")
        with _lock:
            run["status"] = "build_failed"
        _update_build_state_status(build_root, "build_failed")
        return
    emit(run, "verify", "stage_done",
         f"FIXED contract acceptance PASSED ({detail}). Model-written "
         f"tests: {model_result}.")
    with _lock:
        _builds[run_id] = {
            "dir": app_dir, "prefix": meta["prefix"],
            "field": meta["field"], "files": files,
            "proc": None, "port": None}
        run["status"] = "build_ready"
    _update_build_state_status(build_root, "build_ready")
    emit(run, "build", "ready",
         f"'{meta['app_name']}' built and verified - the app below is "
         "THIS build, spawned and probe-verified just now.",
         {"prefix": meta["prefix"], "field": meta["field"],
          "app_name": meta["app_name"], "entity": meta["entity"],
          "model_tests": model_result})


def run_build(run_id, card):
    """Selected-idea build pipeline. Paid synthesis honestly gated per
    step. Generated code NEVER executes automatically - not even its
    own acceptance tests: the review gate pins the exact bytes by
    sha256 and only an independent reviewer manifest unlocks the
    verify stage, which always reports exactly what happened."""
    global _active_runs
    with _lock:
        run = _runs[run_id]
        run["status"] = "running"
        _active_runs += 1
    build_root = os.path.join(RUNS, f"{run_id}-build")
    workdir = os.path.join(build_root, "work")
    app_dir = os.path.join(build_root, "app")
    try:
        try:
            ingest_mod, analyze_mod = _load_pipeline()
            import build_ai
        except Exception as e:
            emit(run, "architecture", "error",
                 f"build path unavailable honestly: {e}")
            with _lock:
                run["status"] = "failed"
            return
        pins = {}
        for ev in run["events"]:
            d = ev.get("data") or {}
            if d.get("slug") and d.get("commit"):
                pins[d["slug"]] = d["commit"]
        metas = {}
        os.makedirs(workdir, exist_ok=True)
        for url in (run["repo_a"], run["repo_b"]):
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "-",
                          _norm(url).split("/")[-1] or "repo")
            meta = ingest_mod.ingest(url, workdir,
                                     expected_sha=pins.get(slug))
            if meta.get("clone_error"):
                emit(run, "architecture", "error",
                     f"{slug}: re-pin failed honestly - "
                     f"{meta['clone_error']}")
                with _lock:
                    run["status"] = "failed"
                return
            meta["analysis"] = analyze_mod.analyze(meta)
            metas[slug] = meta
        emit(run, "architecture", "log",
             f"Building '{card.get('title')}' - both repos re-pinned at "
             "the exact commits from the ideas run and re-analyzed "
             "(free stages, real).")
        try:
            def on_step(step, prov):
                stage = step.replace("build-", "")
                emit(run, stage, "log",
                     f"{stage}: 1 paid call - "
                     f"{prov['usage']['input']} in / "
                     f"{prov['usage']['output']} out (provider "
                     f"count-check {prov['measured_input_tokens']}).")
            plan, code, tests, provs = build_ai.run_build_steps(
                metas, card, run_id, on_step=on_step)
        except build_ai.NotConfigured:
            emit(run, "architecture", "blocked",
                 "Build generation is not armed: no envelope.build.json "
                 "and no key. The idea-to-build path is wired end to "
                 "end; the first real build needs its own bounded grant "
                 "(3 model calls: architecture, glue, tests). The repos "
                 "were re-pinned and re-analyzed just now - nothing was "
                 "pretended.",
                 {"paid_attempt": None})
            with _lock:
                run["status"] = "stopped_at_paid_boundary"
            return
        except build_ai.Refused as e:
            emit(run, "architecture", "blocked",
                 "PAID build refused "
                 + ("AFTER a charged call fired (raw + rejection record "
                    "retained, never retried)" if e.spent
                    else "before any spend")
                 + f": {e}",
                 {"paid_attempt": {"spent": bool(e.spent),
                                   "reason": str(e), "step": e.step}})
            with _lock:
                run["status"] = "stopped_at_paid_boundary"
            return
        except Exception as e:
            emit(run, "architecture", "blocked",
                 f"paid build path errored honestly: {e}. Whether its "
                 "call was charged is UNKNOWN - check the retained "
                 "record before any retry.",
                 {"paid_attempt": {"spent": None, "reason": str(e)}})
            with _lock:
                run["status"] = "stopped_at_paid_boundary"
            return

        os.makedirs(os.path.join(app_dir, "generated"), exist_ok=True)
        with open(os.path.join(app_dir, "generated", "app.py"), "w") as f:
            f.write(code)
        with open(os.path.join(app_dir, "test_fused.py"), "w") as f:
            f.write(tests)
        vend = os.path.join(FUSED_APP, "vendor")
        if os.path.isdir(vend):
            shutil.copytree(vend, os.path.join(app_dir, "vendor"),
                            dirs_exist_ok=True)
        emit(run, "glue", "stage_done",
             "generated/app.py written, statically linted (AST "
             "accident filter - NOT a security boundary). Vendored "
             "pinned deps copied from the reviewed example.")
        emit(run, "tests", "stage_done",
             "test_fused.py written, statically linted.")
        meta = {"prefix": plan["crud_prefix"],
                "field": plan["fields"][0]["name"],
                "app_name": plan["app_name"], "entity": plan["entity"]}
        approved, files, approval = _build_review_gate(run_id, app_dir)
        if not approved:
            _write_build_state(build_root, {
                "run_id": run_id, "status": "awaiting_review",
                "meta": meta, "created_at": time.time()})
            review_req = {
                "run_id": run_id, "files": files,
                "vendor_matches_repo": _vendor_matches_repo(app_dir),
                "approval_path": os.path.join(APPROVALS,
                                              f"{run_id}.json"),
                "note": "reviewer: read the exact source under this run's "
                        "app dir; approve ONLY these hashes. The pipeline "
                        "cannot write the approval path."}
            with open(os.path.join(build_root, "review-request.json"),
                      "w") as f:
                json.dump(review_req, f, indent=2, sort_keys=True)
            emit(run, "verify", "review",
                 "Generated and PINNED - nothing executed. RepoFuse never "
                 "runs unreviewed generated code: the static lint catches "
                 "accidents but is not a security boundary (introspection "
                 "and the vendored dependencies can reach OS facilities, "
                 "and child processes share this OS user). An independent "
                 "reviewer must approve these exact bytes; after that the "
                 "acceptance tests and the app run under the scrubbed "
                 "child environment.",
                 {"files": files, "run_id": run_id,
                  "vendor_matches_repo": _vendor_matches_repo(app_dir),
                  "review_request": os.path.join(
                      os.path.relpath(build_root, ROOT),
                      "review-request.json"),
                  "approval_path": os.path.join(
                      os.path.relpath(APPROVALS, ROOT),
                      f"{run_id}.json")})
            with _lock:
                run["status"] = "awaiting_review"
            return
        _verify_and_register(run, run_id, build_root, app_dir, meta)
    except Exception as e:  # honest failure, never a pretend pass
        emit(run, "error", "error", f"build pipeline error: {e}")
        with _lock:
            run["status"] = "failed"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        with _lock:
            _active_runs -= 1


GENERATED_RELS = ["generated/app.py", "test_fused.py"]


def _hash_tree(app_dir):
    """sha256 of EVERY file a run would execute under app_dir - generated
    app, acceptance tests AND the vendored pinned dependencies - keyed by
    relative path. __pycache__ is excluded: the interpreter creates it
    after the pin. None when a required generated file is missing."""
    out = {}
    for base, dirs, names in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in sorted(names):
            p = os.path.join(base, n)
            rel = os.path.relpath(p, app_dir)
            with open(p, "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()
    if not all(rel in out for rel in GENERATED_RELS):
        return None
    return out


def _vendor_matches_repo(app_dir):
    """True when every vendored file in the build is byte-identical to the
    reviewed example's vendor tree. Reviewer aid only - enforcement is the
    hash match, never this flag."""
    src = os.path.join(FUSED_APP, "vendor")
    dst = os.path.join(app_dir, "vendor")
    if not (os.path.isdir(src) and os.path.isdir(dst)):
        return None
    def tree(root):
        t = {}
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for n in sorted(names):
                p = os.path.join(base, n)
                with open(p, "rb") as f:
                    t[os.path.relpath(p, root)] = hashlib.sha256(
                        f.read()).hexdigest()
        return t
    return tree(src) == tree(dst)


def _load_approval(run_id):
    """The independent review manifest for this run, or None. Format:
    {"run_id", "files": {relpath: sha256}, "reviewer", "reviewed_at",
    "note"}. Written ONLY by a human/reviewer after reading the exact
    generated source - never by any pipeline code."""
    p = os.path.join(APPROVALS, f"{run_id}.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            ap = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(ap, dict) or not isinstance(ap.get("files"), dict):
        return None
    if ap.get("run_id") != run_id:
        return None  # inner id must match - a manifest for another run is void
    return ap


def _build_review_gate(run_id, app_dir):
    """THE boundary for generated code: (approved, files, approval).
    approved is True only when an independent review manifest pins the
    EXACT sha256 of every generated file on disk right now. The AST lint
    upstream is an accident filter, not a security boundary - this hash
    match against reviewer-read bytes is what execution hangs on."""
    files = _hash_tree(app_dir)
    if files is None:
        return False, None, None
    ap = _load_approval(run_id)
    if ap and ap.get("files") == files:
        return True, files, ap
    return False, files, ap


RESUMABLE_DISK = {"awaiting_review", "build_failed", "build_ready"}
RESUMABLE_MEM = {"awaiting_review", "build_failed"}


def _write_build_state(build_root, state):
    """Persist the resumable truth of a build run (never the marker: the
    approval manifest lives only in APPROVALS and is never written here)."""
    tmp = os.path.join(build_root, "build-state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, os.path.join(build_root, "build-state.json"))


def _update_build_state_status(build_root, status):
    try:
        with open(os.path.join(build_root, "build-state.json")) as f:
            st = json.load(f)
        st["status"] = status
        _write_build_state(build_root, st)
    except (OSError, ValueError):
        pass  # persistence is restart-truth only; the live run is primary


def _load_build_state(run_id):
    """Restart-truth loader for the bounded resume path. Fail closed on
    anything unexpected: bad id, missing/unreadable file, inner run_id
    mismatch, non-resumable status, malformed meta."""
    if not RUN_ID.match(run_id):
        return None
    p = os.path.join(RUNS, f"{run_id}-build", "build-state.json")
    try:
        with open(p) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(st, dict) or st.get("run_id") != run_id:
        return None
    if st.get("status") not in RESUMABLE_DISK:
        return None
    meta = st.get("meta")
    if not (isinstance(meta, dict)
            and isinstance(meta.get("prefix"), str)
            and isinstance(meta.get("field"), str)
            and isinstance(meta.get("app_name"), str)
            and isinstance(meta.get("entity"), str)):
        return None
    return st


def _child_env(extra=None):
    """Environment for ANY child running app code (verify subprocess,
    spawned apps). ALLOWLIST only: the server's own environment - which
    may carry MODEL_API_KEY during an armed qualification - is never
    inherited. No key material, no vault paths, a throwaway HOME."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": tempfile.mkdtemp(prefix="repofuse-child-"),
        "LANG": "C.UTF-8",
    }
    env.update(extra or {})
    return env


def _free_loopback_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _probe_owns(base, token, path, field):
    """Identity handshake: create/read/delete a uniquely-named entity. Only
    a backend we just spawned (empty db, real CRUD) passes all three."""
    probe = json.dumps({field: f"studio-probe-{token}"}).encode()
    req = urllib.request.Request(f"{base}{path}", data=probe, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2) as r:
        nid = json.loads(r.read())["id"]
    with urllib.request.urlopen(f"{base}{path}/{nid}", timeout=2) as r:
        if json.loads(r.read()).get(field) != f"studio-probe-{token}":
            return False
    req = urllib.request.Request(f"{base}{path}/{nid}", method="DELETE")
    with urllib.request.urlopen(req, timeout=2) as r:
        if r.status != 204:
            return False
    try:
        urllib.request.urlopen(f"{base}{path}/{nid}", timeout=2)
        return False  # deleted entity still readable: not our fresh backend
    except urllib.error.HTTPError as e:
        return e.code == 404


def _probe_owns_backend(base, token):
    return _probe_owns(base, token, "/notes", "text")


def _spawn_owned(app_dir, runner_snippet, probe_path, probe_field, db_base):
    """Spawn OUR copy of an app on a random loopback port and prove
    ownership. Never trusts a pre-existing service on any port."""
    os.makedirs(os.path.dirname(db_base + ".db") or ".", exist_ok=True)
    for _ in range(2):  # bounded attempts
        port = _free_loopback_port()
        token = secrets.token_hex(8)
        env = _child_env({"FUSED_DB_PATH": f"{db_base}-{token}.db"})
        proc = subprocess.Popen(
            [sys.executable, "-c", runner_snippet % port],
            cwd=app_dir, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        ok = False
        for _ in range(40):
            if proc.poll() is not None:
                break
            try:
                if _probe_owns(base, token, probe_path, probe_field):
                    ok = True
                    break
            except Exception:
                time.sleep(0.25)
        if ok:
            return proc, port
        proc.terminate()
    return None, None


NOTES_RUNNER = ("import assistant_ext\nfrom generated.app import app\n"
                "app.run(host='127.0.0.1', port=%d)")
BUILD_RUNNER = ("import os\n"
                "import vendor  # RepoFuse shim: puts vendored pinned repos on sys.path\n"
                "import generated.app as g\n"
                "g.db.init(os.environ['FUSED_DB_PATH'])\n"
                "g.db.create_tables(g.MODELS)\n"
                "g.app.run(host='127.0.0.1', port=%d)")
_builds = {}


def _resume_thread(run_id, prev_status):
    """Bounded resume worker: revalidates the persisted record, then the
    shared verify-and-register path. Generation is structurally absent:
    no pipeline import, no envelope, no key, no model traffic."""
    global _active_runs
    try:
        with _lock:
            run = _runs[run_id]
        build_root = os.path.join(RUNS, f"{run_id}-build")
        app_dir = os.path.join(build_root, "app")
        st = _load_build_state(run_id)
        if st is None or not os.path.isdir(app_dir):
            emit(run, "verify", "error",
                 "Resume refused: persisted build record or retained "
                 "artifacts missing or invalid - nothing executed.")
            with _lock:
                run["status"] = prev_status
            return
        _verify_and_register(run, run_id, build_root, app_dir, st["meta"])
    except Exception as e:  # honest failure, never a pretend pass
        with _lock:
            run = _runs.get(run_id)
            if run is not None:
                run["status"] = prev_status
        if run is not None:
            emit(run, "error", "error", f"resume pipeline error: {e}")
    finally:
        with _lock:
            _active_runs -= 1


def resume_build(run_id):
    """The bounded continuation the review gate needs. Returns a code for
    the HTTP layer. Accepts only an already-generated run awaiting review
    (or one whose verify failed), in memory or - after a server restart -
    reconstructed from the persisted build record. NEVER generates."""
    global _active_runs
    restored = False
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            st = _load_build_state(run_id)
            if st is None:
                return "unknown", None
            run = {"status": st["status"], "events": [],
                   "repo_a": None, "repo_b": None, "recorded_pair": False}
            _runs[run_id] = run
            restored = True
        status = run["status"]
        if status not in RESUMABLE_MEM and not (
                status == "build_ready" and run.get("repo_a") is None):
            # build_ready in memory is already registered - nothing to do;
            # build_ready from disk re-registers via a fresh verify.
            return "state", status
        if _active_runs >= MAX_ACTIVE_RUNS:
            return "busy", status
        run["status"] = "resuming"
        _active_runs += 1
    threading.Thread(target=_resume_thread, args=(run_id, status),
                     daemon=True).start()
    if restored:
        emit(run, "verify", "log",
             "Run state restored from the persisted build record "
             "after a server restart - bounded continuation only, no "
             "generation of any kind.")
    return "ok", status


def ensure_notes_backend():
    """Spawn OUR copy of the verified example app via the shared spawner."""
    global _notes_proc, _notes_port
    with _lock:
        if _notes_proc and _notes_proc.poll() is None and _notes_port:
            return _notes_port
        if not os.path.isdir(FUSED_APP):
            return None
        os.makedirs(RUNS, exist_ok=True)
    proc, port = _spawn_owned(FUSED_APP, NOTES_RUNNER, "/notes", "text",
                              os.path.join(RUNS, "notes"))
    with _lock:
        if port:
            _notes_proc, _notes_port = proc, port
    return port


def ensure_build_backend(run_id):
    """Spawn the probe-verified runner for a REVIEWED, VERIFIED build only.
    The on-disk bytes are re-hashed against the registered review manifest
    first - tampered, unreviewed or absent builds never execute."""
    with _lock:
        b = _builds.get(run_id)
        if not b:
            return None
        if b.get("proc") and b["proc"].poll() is None and b.get("port"):
            return b["port"]
        expected = dict(b.get("files") or {})
        app_dir, prefix, field = b["dir"], b["prefix"], b["field"]
    if not expected or _hash_tree(app_dir) != expected:
        return None  # bytes changed since review - refuse to execute
    proc, port = _spawn_owned(app_dir, BUILD_RUNNER, prefix,
                              field,
                              os.path.join(RUNS, f"{run_id}-build", "live"))
    with _lock:
        if port:
            b["proc"], b["port"] = proc, port
    return port


def proxy_notes(handler):
    port = ensure_notes_backend()
    if not port:
        handler._json(503, {
            "error": "notes backend unavailable",
            "detail": f"could not start and probe the verified example app "
                      f"at {FUSED_APP}"})
        return
    _proxy_to(handler, port,
              urllib.parse.urlsplit(handler.path).path)


def proxy_build(handler, run_id, rest):
    port = ensure_build_backend(run_id)
    if not port:
        handler._json(503, {
            "error": "build backend unavailable",
            "detail": "no reviewed and verified build is registered for "
                      "this run, its bytes changed since review, or it "
                      "failed to start and probe"})
        return
    _proxy_to(handler, port, rest)


def _proxy_to(handler, port, path):
    length = int(handler.headers.get("Content-Length") or 0)
    if length > MAX_NOTES_BODY:
        return handler._json(413, {"error": "body too large"})
    body = handler.rfile.read(length) if length else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body, method=handler.command,
        headers={"Content-Type": handler.headers.get("Content-Type",
                                                     "application/json")})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload, status = resp.read(), resp.status
            ctype = resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        payload, status = e.read(), e.code
        ctype = "application/json"
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _shutdown():
    if _notes_proc and _notes_proc.poll() is None:
        _notes_proc.terminate()


atexit.register(_shutdown)


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, status, obj):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _refuse(self, status=403, msg="refused"):
        self._json(status, {"error": msg})

    def _check_local(self):
        """DNS-rebinding / cross-origin local-POST protection."""
        if self.headers.get("Host", "") not in LOCAL_HOSTS:
            return False
        if self.command in ("POST", "PUT", "DELETE"):
            origin = self.headers.get("Origin")
            if origin and origin not in LOCAL_ORIGINS:
                return False
        return True

    def _fuse(self):
        global _active_runs
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_FUSE_BODY:
            return self._json(413, {"error": "body too large"})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad JSON"})
        a, b = _norm(req.get("repo_a")), _norm(req.get("repo_b"))
        intent = (req.get("intent") or "").strip()[:2000]
        if not (REPO_URL.match(a) and REPO_URL.match(b)):
            return self._json(400, {
                "error": "repo URLs must be exactly "
                         "https://github.com/<owner>/<repo>"})
        if a == b:
            return self._json(400, {"error": "two different repos required"})
        with _lock:
            if _active_runs >= MAX_ACTIVE_RUNS:
                return self._json(429, {"error": "too many active runs"})
            run_id = f"run-{secrets.token_hex(8)}"
            _runs[run_id] = {"status": "running", "events": [],
                             "repo_a": a, "repo_b": b,
                             "recorded_pair": is_recorded_pair(a, b)}
            _active_runs += 1
        threading.Thread(target=run_pipeline,
                         args=(run_id, a, b, intent), daemon=True).start()
        return self._json(200, {"run_id": run_id,
                                "recorded_pair": is_recorded_pair(a, b)})

    def _build(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_FUSE_BODY:
            return self._json(413, {"error": "body too large"})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad JSON"})
        run_id = req.get("run_id") or ""
        card = req.get("card")
        if not RUN_ID.match(run_id):
            return self._json(400, {"error": "unknown run"})
        if not (isinstance(card, dict)
                and isinstance(card.get("title"), str)):
            return self._json(400,
                              {"error": "a selected idea card is required"})
        with _lock:
            run = _runs.get(run_id)
            if not run:
                return self._json(404, {"error": "unknown run"})
            if run["status"] != "ideas_ready":
                return self._json(
                    409, {"error": f"run is {run['status']}, "
                                   "not ideas_ready"})
            if _active_runs >= MAX_ACTIVE_RUNS:
                return self._json(429, {"error": "too many active runs"})
        threading.Thread(target=run_build, args=(run_id, card),
                         daemon=True).start()
        return self._json(200, {"run_id": run_id, "status": "running"})

    def _build_resume(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_FUSE_BODY:
            return self._json(413, {"error": "body too large"})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad JSON"})
        run_id = req.get("run_id") or ""
        if not RUN_ID.match(run_id):
            return self._json(400, {"error": "unknown run"})
        code, status = resume_build(run_id)
        if code == "ok":
            return self._json(200, {"run_id": run_id,
                                    "status": "resuming"})
        if code == "unknown":
            return self._json(404, {"error": "unknown run"})
        if code == "busy":
            return self._json(429, {"error": "too many active runs"})
        return self._json(409, {"error": f"run is {status}, not resumable "
                                        "(awaiting_review or build_failed)"})

    def do_POST(self):
        if not self._check_local():
            return self._refuse()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/fuse":
            return self._fuse()
        if path == "/api/build":
            return self._build()
        if path == "/api/build/resume":
            return self._build_resume()
        if NOTES_PATH.match(path):
            return proxy_notes(self)
        bm = BUILD_PATH.match(path)
        if bm:
            return proxy_build(self, bm.group(1), bm.group(2) or "/")
        self._json(404, {"error": "unknown endpoint"})

    def do_GET(self):
        if not self._check_local():
            return self._refuse()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/notes-health":
            port = ensure_notes_backend()
            return self._json(200, {
                "available": bool(port),
                "backend": "real verified app (microdot + peewee + SQLite), "
                           "spawned and probe-verified by this server"})
        if path.startswith("/api/run/"):
            rid = path.rsplit("/", 1)[-1]
            if not RUN_ID.match(rid):
                return self._json(404, {"error": "unknown run"})
            with _lock:
                run = _runs.get(rid)
                snap = None if not run else {
                    "status": run["status"], "events": list(run["events"]),
                    "recorded_pair": run["recorded_pair"]}
            return self._json(200 if snap else 404,
                              snap or {"error": "unknown run"})
        if NOTES_PATH.match(path):
            return proxy_notes(self)
        bm = BUILD_PATH.match(path)
        if bm:
            return proxy_build(self, bm.group(1), bm.group(2) or "/")
        if path.startswith("/api/"):
            return self._json(404, {"error": "unknown endpoint"})
        entry = STATIC.get(path)
        if not entry:
            return self._refuse(404, "not found")
        ctype, fname = entry
        try:
            with open(os.path.join(ROOT, fname), "rb") as f:
                payload = f.read()
        except OSError:
            return self._refuse(404, "not found")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_PUT(self):
        if not self._check_local():
            return self._refuse()
        p = urllib.parse.urlsplit(self.path).path
        if NOTES_PATH.match(p):
            return proxy_notes(self)
        bm = BUILD_PATH.match(p)
        if bm:
            return proxy_build(self, bm.group(1), bm.group(2) or "/")
        self._json(405, {"error": "method not allowed here"})

    def do_DELETE(self):
        if not self._check_local():
            return self._refuse()
        p = urllib.parse.urlsplit(self.path).path
        if NOTES_PATH.match(p):
            return proxy_notes(self)
        bm = BUILD_PATH.match(p)
        if bm:
            return proxy_build(self, bm.group(1), bm.group(2) or "/")
        self._json(405, {"error": "method not allowed here"})


def main():
    print(f"RepoFuse Studio on http://127.0.0.1:{PORT} "
          f"(fused app: {FUSED_APP})")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
