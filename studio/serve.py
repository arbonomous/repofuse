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
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
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
}

REPO_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}"
    r"(?:\.git)?/?$")
RUN_ID = re.compile(r"^run-[0-9a-f]{16}$")
NOTES_PATH = re.compile(r"^/notes(/\d{1,9})?$")

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
            # Ideas mode: deterministic suggestions from the REAL analysis
            # (no model call). The user picks one; only then would the paid
            # stages matter.
            try:
                import ideas as ideas_mod
                cards = ideas_mod.suggest(metas)
            except Exception as e:
                emit(run, "error", "error",
                     f"idea suggestion failed honestly: {e}")
                with _lock:
                    run["status"] = "failed"
                return
            emit(run, "ideas", "ideas",
                 "Build ideas derived locally from the actual exports above "
                 "- no model call. Pick one, or describe your own.",
                 {"cards": cards})
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
def _free_loopback_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _probe_owns_backend(base, token):
    """Identity handshake: create/read/delete a uniquely-named note. Only a
    backend we just spawned (empty db, real CRUD) passes all three."""
    probe = json.dumps({"text": f"studio-probe-{token}"}).encode()
    req = urllib.request.Request(f"{base}/notes", data=probe, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2) as r:
        nid = json.loads(r.read())["id"]
    with urllib.request.urlopen(f"{base}/notes/{nid}", timeout=2) as r:
        if json.loads(r.read()).get("text") != f"studio-probe-{token}":
            return False
    req = urllib.request.Request(f"{base}/notes/{nid}", method="DELETE")
    with urllib.request.urlopen(req, timeout=2) as r:
        if r.status != 204:
            return False
    try:
        urllib.request.urlopen(f"{base}/notes/{nid}", timeout=2)
        return False  # deleted note still readable: not our fresh backend
    except urllib.error.HTTPError as e:
        return e.code == 404


def ensure_notes_backend():
    """Spawn OUR copy of the verified app on a random loopback port and
    prove ownership. Never trusts a pre-existing service on any port."""
    global _notes_proc, _notes_port
    with _lock:
        if _notes_proc and _notes_proc.poll() is None and _notes_port:
            return _notes_port
        if not os.path.isdir(FUSED_APP):
            return None
        os.makedirs(RUNS, exist_ok=True)
        for _ in range(2):  # bounded attempts
            port = _free_loopback_port()
            token = secrets.token_hex(8)
            env = dict(os.environ,
                       FUSED_DB_PATH=os.path.join(RUNS, f"notes-{token}.db"))
            proc = subprocess.Popen(
                [sys.executable, "-c",
                 "import assistant_ext\nfrom generated.app import app\n"
                 f"app.run(host='127.0.0.1', port={port})"],
                cwd=FUSED_APP, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            ok = False
            for _ in range(40):
                if proc.poll() is not None:
                    break
                try:
                    if _probe_owns_backend(base, token):
                        ok = True
                        break
                except Exception:
                    time.sleep(0.25)
            if ok:
                _notes_proc, _notes_port = proc, port
                return port
            proc.terminate()
        return None


def proxy_notes(handler):
    port = ensure_notes_backend()
    if not port:
        handler._json(503, {
            "error": "notes backend unavailable",
            "detail": f"could not start and probe the verified example app "
                      f"at {FUSED_APP}"})
        return
    length = int(handler.headers.get("Content-Length") or 0)
    if length > MAX_NOTES_BODY:
        return handler._json(413, {"error": "body too large"})
    body = handler.rfile.read(length) if length else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{urllib.parse.urlsplit(handler.path).path}",
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
                             "recorded_pair": is_recorded_pair(a, b)}
            _active_runs += 1
        threading.Thread(target=run_pipeline,
                         args=(run_id, a, b, intent), daemon=True).start()
        return self._json(200, {"run_id": run_id,
                                "recorded_pair": is_recorded_pair(a, b)})

    def do_POST(self):
        if not self._check_local():
            return self._refuse()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/fuse":
            return self._fuse()
        if NOTES_PATH.match(path):
            return proxy_notes(self)
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
        if NOTES_PATH.match(urllib.parse.urlsplit(self.path).path):
            return proxy_notes(self)
        self._json(405, {"error": "method not allowed here"})

    def do_DELETE(self):
        if not self._check_local():
            return self._refuse()
        if NOTES_PATH.match(urllib.parse.urlsplit(self.path).path):
            return proxy_notes(self)
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
