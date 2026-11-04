"""Genuine isolation for executing untrusted fused-app tests.

bubblewrap kernel namespaces: no network, private PID/mount/IPC/UTS, env
cleared, only /usr /lib /lib64 /bin /sbin read-only plus a scratch COPY of
the fused app at /work. python -S -s: no site machinery at all - host
dist-packages and user site-packages are NOT importable (import closure is
enforced again in verify, as a second layer).

Resource bounds: prlimit (60s CPU, 64 procs, 256 fds, 32MB/file, 1GB RAM)
PLUS a host-side watchdog that kills the run if aggregate scratch disk
(work copy AND the sandbox's /tmp, which is a host-visible bound subdir of
the scratch root, never an invisible tmpfs) exceeds 256MB. tmpfs cannot be
size-limited via bwrap flags; the watchdog is the enforcing layer, with
bounded overshoot from its 0.5s poll interval (SOFT bound, not a quota).

Review gate: run_tests_isolated refuses to execute while unreviewed
model-generated files (generated/*.py, test_fused.py) are present; see
gluereview.py. Attestation pins reviewed bytes; it is a review record, not
a security proof.

Verdict: parsed only from an HMAC-signed line emitted by sandbox_runner.py
(one-time key via a pipe closed before untrusted imports). Bare exit 0 or
printed 'OK' never count.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

from . import gluereview

RLIMITS = ["--cpu=60", "--nproc=64", "--nofile=256",
           "--fsize=33554432", "--as=1073741824"]
MAX_SCRATCH_BYTES = 256 * 1024 * 1024
WATCHDOG_INTERVAL_S = 0.5
_VERDICT = re.compile(r"^REPOFUSE-VERDICT ([0-9a-f]{64}) (\{.*\})$", re.M)

_RUNNER_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "sandbox_runner.py")


def bwrap_available():
    return shutil.which("bwrap") is not None


def _static_check(fusion_dir):
    """Compile-check generated/test code only. Vendored third-party trees are
    excluded: they are inputs with their own upstream dialects, not generated
    output, and are judged by execution, not by our compiler."""
    results = []
    candidates = []
    for name in ("test_fused.py", "acceptance_test.py"):
        full = os.path.join(fusion_dir, name)
        if os.path.isfile(full):
            candidates.append(full)
    gen_dir = os.path.join(fusion_dir, "generated")
    if os.path.isdir(gen_dir):
        candidates += [os.path.join(gen_dir, f)
                       for f in sorted(os.listdir(gen_dir))
                       if f.endswith(".py")]
    for full in candidates:
        if True:
            name = os.path.basename(full)
            rel = os.path.relpath(full, fusion_dir)
            try:
                src = open(full, "r", encoding="utf-8", errors="replace").read()
                compile(src, rel, "exec")  # compiles only; never executes
                results.append({"file": rel, "syntax": "ok"})
            except (SyntaxError, ValueError) as e:
                results.append({"file": rel, "syntax": "error",
                                "detail": str(e)[:500]})
    ok = all(r["syntax"] == "ok" for r in results)
    return {"status": "static_passed" if ok else "static_failed",
            "mode": "static_only",
            "checks": results,
            "note": "compile() only; no code executed; behavioral "
                    "verification requires namespace isolation"}


def build_sandbox_cmd(work, tmp_path, python, argv):
    """bwrap command: all namespaces unshared, env cleared, minimal mounts.
    /tmp is a host-visible bound subdir of the scratch root so the disk
    watchdog covers it; it is never an invisible tmpfs."""
    binds = []
    for d in ("/usr", "/lib", "/lib64", "/bin", "/sbin"):
        if os.path.isdir(d):
            binds += ["--ro-bind", d, d]
    return (["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
             "--clearenv"]
            + binds
            + ["--bind", work, "/work", "--bind", tmp_path, "/tmp",
               "--chdir", "/work",
               "--setenv", "HOME", "/tmp",
               "--setenv", "PATH", "/usr/bin:/bin",
               "--setenv", "PYTHONPATH", "/work",
               "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--setenv", "PYTHONNOUSERSITE", "1",
               "--", "prlimit"] + RLIMITS
            + ["--", python, "-S", "-s"] + argv)


def _dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


class _DiskWatchdog:
    """Kills the sandbox process if aggregate scratch disk exceeds the cap."""

    def __init__(self, path, proc):
        self.path, self.proc = path, proc
        self.tripped = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            if self.proc.poll() is not None:
                return
            try:
                if _dir_size(self.path) > MAX_SCRATCH_BYTES:
                    self.tripped = True
                    self.proc.kill()
                    return
            except OSError:
                pass
            time.sleep(WATCHDOG_INTERVAL_S)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)


def _parse_signed_verdict(stdout, key):
    """Accept exactly one verdict whose HMAC validates; forged lines (any
    number, any position) are ignored. Two valid verdicts = tampering."""
    valid = []
    for m in _VERDICT.finditer(stdout):
        tag, body = m.group(1), m.group(2)
        expect = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(tag, expect):
            valid.append(body)
    if not valid:
        return None, "no validly-signed verdict line"
    if len(set(valid)) > 1:
        return None, "multiple differing signed verdicts"
    try:
        return json.loads(valid[0]), None
    except ValueError:
        return None, "verdict not JSON"


def run_tests_isolated(fusion_dir, timeout=90, exclude_files=(),
                       test_module="test_fused", attestation_path=None):
    """Run the test module inside bwrap namespaces on a scratch copy."""
    test_file = os.path.join(fusion_dir, test_module + ".py")
    if not os.path.exists(test_file):
        return {"status": "skipped",
                "reason": f"no {test_module}.py (synthesis pending or failed)"}
    gate_ok, gate_why, gate_pending = gluereview.check_attestation(
        fusion_dir, attestation_path, exclude=set(exclude_files))
    if not gate_ok:
        return {"status": "pending_glue_review", "detail": gate_why,
                "files_pending_review": gate_pending}
    static = _static_check(fusion_dir)
    if static["status"] == "static_failed":
        return {"status": "failed", "stage": "static", "detail": static}
    if not bwrap_available():
        out = dict(static)
        out["behavioral"] = "not_run_no_isolation"
        return out

    scratch = tempfile.mkdtemp(prefix="repofuse-sbx-")
    work = os.path.join(scratch, "work")
    sbox_tmp = os.path.join(scratch, "sbox-tmp")
    os.mkdir(sbox_tmp)
    shutil.copytree(fusion_dir, work, symlinks=False)
    shutil.copyfile(_RUNNER_SRC, os.path.join(work, "_repofuse_runner.py"))
    for rel in exclude_files:
        target = os.path.join(work, rel)
        if os.path.isfile(target):
            os.unlink(target)
    python = shutil.which("python3") or "/usr/bin/python3"

    key = secrets.token_bytes(32)
    key_r, key_w = os.pipe()
    cmd = build_sandbox_cmd(
        work, sbox_tmp, python, ["_repofuse_runner.py", str(key_r), test_module])
    out_path = os.path.join(scratch, "stdout.txt")
    err_path = os.path.join(scratch, "stderr.txt")
    with open(out_path, "wb") as outf, open(err_path, "wb") as errf:
        proc = subprocess.Popen(cmd, stdout=outf, stderr=errf,
                                pass_fds=(key_r,))
        os.write(key_w, key)
        os.close(key_w)
        os.close(key_r)
        killed_by_watchdog = False
        with _DiskWatchdog(scratch, proc) as wd:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
                shutil.rmtree(scratch, ignore_errors=True)
                return {"status": "timeout", "isolation": "bwrap+prlimit",
                        "detail": f"killed after {timeout}s"}
        killed_by_watchdog = wd.tripped

    def _tail(path, n=4000):
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")

    stdout, stderr = _tail(out_path), _tail(err_path)
    shutil.rmtree(scratch, ignore_errors=True)

    base = {
        "mode": "behavioral",
        "isolation": "bwrap user/net/pid/ipc/uts namespaces, scratch copy, "
                     "prlimits, disk watchdog",
        "static": static["checks"],
        "exit_code": proc.returncode,
        "stdout": stdout, "stderr": stderr,
    }
    if killed_by_watchdog:
        return dict(base, status="failed",
                    detail=f"scratch disk exceeded {MAX_SCRATCH_BYTES} bytes; "
                           "killed by watchdog")
    verdict, err = _parse_signed_verdict(stdout, key)
    if verdict is None:
        return dict(base, status="failed",
                    detail=f"verdict not trustworthy: {err}")
    base["verdict"] = verdict
    if not verdict["ok"]:
        return dict(base, status="failed",
                    detail=f"{verdict['failures']} failure(s), "
                           f"{verdict['errors']} error(s)")
    if verdict["ran"] < 1:
        return dict(base, status="failed",
                    detail="zero tests ran; refusing to count as pass")
    base["status"] = "passed"
    base["note"] = "signed verdict observed inside namespace isolation"
    return base
