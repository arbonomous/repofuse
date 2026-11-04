"""Phase 0: clone repositories and extract verifiable metadata.

Only static inspection happens here. RepoFuse never executes cloned code
during ingest/analyze/plan.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

_EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".java": "Java", ".c": "C",
    ".h": "C/C++ header", ".cpp": "C++", ".cs": "C#",
    ".html": "HTML", ".css": "CSS", ".sh": "Shell",
}
_MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml",
              "go.mod", "Cargo.toml", "Gemfile", "pom.xml")
_LICENSE_PATTERNS = [
    ("MIT", re.compile(r"\bMIT License\b|Permission is hereby granted, free of charge", re.I)),
    ("Apache-2.0", re.compile(r"Apache License[,\s]+Version 2\.0", re.I)),
    ("BSD-3-Clause", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    ("GPL-3.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("GPL-2.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 2", re.I)),
    ("MPL-2.0", re.compile(r"Mozilla Public License Version 2\.0", re.I)),
    ("ISC", re.compile(r"\bISC License\b", re.I)),
    ("Unlicense", re.compile(r"This is free and unencumbered software", re.I)),
]
_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


MAX_REPO_BYTES = 200 * 1024 * 1024  # refuse repos over 200MB
_GITHUB_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?$")


def validate_repo_url(url, allow_local=False):
    """Strict input validation; option injection and file:// are refused."""
    if not url or url.startswith("-") or "\x00" in url:
        return False
    if _GITHUB_URL.match(url):
        return True
    if allow_local and os.path.isabs(url) and os.path.isdir(url):
        return True
    return False

_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",  # no user gitconfig (credential helpers etc)
    "GIT_TEMPLATE_DIR": "/dev/null",   # no template hooks
    "GIT_TERMINAL_PROMPT": "0",        # never prompt/hang on auth
    "HOME": "/tmp",
}


# Helper for the portable bounded path: a tiny single-threaded process that
# applies the SAME limits via the POSIX stdlib resource module, then execs
# git. Works on Linux and macOS; bounds apply DURING the clone, not after.
_RLIMIT_HELPER = (
    "import json,os,resource,sys\n"
    "spec=json.loads(sys.argv[1])\n"
    "for name,val in spec['limits'].items():\n"
    "    resource.setrlimit(getattr(resource,name),(val,val))\n"
    "os.execvpe('git',['git']+spec['args'],spec['env'])\n"
)

_PRLIMIT_TO_RLIMIT = {"--fsize": "RLIMIT_FSIZE", "--cpu": "RLIMIT_CPU",
                      "--as": "RLIMIT_AS"}


def _git(args, cwd=None, rlimits=None):
    env = dict(_GIT_ENV)
    if not rlimits:
        return subprocess.run(["git"] + args, cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=300)
    if shutil.which("prlimit", path=env["PATH"]):
        cmd = ["prlimit"] + rlimits + ["--", "git"] + args
        return subprocess.run(cmd, cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=300)
    # No prlimit (e.g. macOS): use the portable POSIX resource module via a
    # helper process (single-threaded, so no preexec_fn fork-in-threads
    # hazard). Never silently drop the bounds - if this platform has no
    # resource module either, refuse the clone (fail closed). Limits are
    # per-file size / CPU / address space, not an aggregate disk cap; note
    # RLIMIT_AS is advisory-only on macOS (kernel ignores it), FSIZE and
    # CPU are enforced there (SIGXFSZ / SIGXCPU).
    try:
        import resource  # noqa: F401  (POSIX stdlib; present on macOS too)
    except ImportError:
        return subprocess.CompletedProcess(
            args=["git"] + args, returncode=126,
            stdout="", stderr="refused: no prlimit and no POSIX resource "
                              "module; cannot bound the clone on this "
                              "platform")
    limits = {}
    for r in rlimits:
        k, _, v = r.partition("=")
        limits[_PRLIMIT_TO_RLIMIT[k]] = int(v)
    spec = json.dumps({"args": args, "env": env, "limits": limits})
    return subprocess.run([sys.executable, "-c", _RLIMIT_HELPER, spec],
                          cwd=cwd, capture_output=True, text=True,
                          timeout=300)


def _dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for fn in files:
            fp = os.path.join(root, fn)
            if os.path.islink(fp):
                continue
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def _reject_unsafe_links(path):
    """Refuse symlinks that escape the repo root."""
    root_real = os.path.realpath(path)
    bad = []
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            fp = os.path.join(root, name)
            if os.path.islink(fp):
                target = os.path.realpath(fp)
                if not target.startswith(root_real + os.sep):
                    bad.append(os.path.relpath(fp, path))
    return bad


def clone_repo(url, dest):
    """Shallow clone. Returns (commit_sha, error_or_None)."""
    if os.path.exists(dest) and os.listdir(dest):
        return None, f"destination {dest} already exists and is not empty"
    os.makedirs(dest, exist_ok=True)
    # --no-recurse-submodules: submodule content is never fetched/executed
    # filter=blob:none keeps clones small; hooks disabled via _GIT_ENV
    # protocols: https + local file only (no ssh/git); credential helpers off
    # rlimits during clone: per-file size / CPU / address-space caps apply
    # DURING download, not after (per-file, not an aggregate disk cap)
    res = _git(["-c", "core.hooksPath=/dev/null",
                "-c", "credential.helper=",
                "-c", "protocol.ssh.allow=never",
                "-c", "protocol.git.allow=never",
                "-c", "protocol.ext.allow=never",
                "clone", "--depth", "1", "--no-recurse-submodules",
                "--filter=blob:none", "--", url, dest],
               rlimits=["--fsize=%d" % MAX_REPO_BYTES, "--cpu=300",
                        "--as=2147483648"])
    if res.returncode != 0:
        return None, res.stderr.strip()[:400]
    bad_links = _reject_unsafe_links(dest)
    if bad_links:
        return None, (f"refused: symlinks escaping repo root: "
                      f"{bad_links[:5]}")
    if _dir_size(dest) > MAX_REPO_BYTES:
        return None, f"refused: repo exceeds {MAX_REPO_BYTES} bytes"
    sha = _git(["rev-parse", "HEAD"], cwd=dest).stdout.strip()
    return sha, None


def detect_license(path):
    """Return (spdx_guess, source_file). Static text match only; labeled a guess."""
    for name in os.listdir(path):
        low = name.lower()
        if low.startswith(("license", "licence", "copying")):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read(8000)
                except OSError:
                    continue
                for spdx, pat in _LICENSE_PATTERNS:
                    if pat.search(text):
                        return spdx, name
                return "UNKNOWN", name
    return None, None


def detect_languages(path):
    counts = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            lang = _EXT_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def find_manifests(path):
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for m in _MANIFESTS:
            if m in files:
                found.append(os.path.relpath(os.path.join(root, m), path))
    return sorted(found)


def tree_summary(path, max_entries=200):
    entries = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            entries.append(os.path.relpath(os.path.join(root, fn), path))
            if len(entries) >= max_entries:
                return sorted(entries) + ["... (truncated)"]
    return sorted(entries)


def read_readme(path, max_chars=6000):
    for name in os.listdir(path):
        if name.lower().startswith("readme"):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    return name, f.read(max_chars)
    return None, ""


def ingest(url, workdir, expected_sha=None, allow_local=False):
    """Clone one repo and collect metadata. Returns metadata dict.

    expected_sha: when set (qualification mode), the checked-out commit MUST
    match or the ingest refuses - qualification runs on pinned snapshots, not
    on whatever a mutable branch points at now."""
    if not validate_repo_url(url, allow_local=allow_local):
        return {"url": url, "slug": None, "path": None, "commit_sha": None,
                "clone_error": "refused: URL failed strict validation "
                               "(https://github.com/<owner>/<repo> only)"}
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", url.rstrip("/").split("/")[-1])
    slug = slug[:-4] if slug.endswith(".git") else slug
    dest = os.path.join(workdir, slug)
    meta = {"url": url, "slug": slug, "path": dest}
    if os.path.isdir(dest) and os.listdir(dest):
        # Idempotent re-run on the same fixed out dir (the review loop
        # re-runs the pipeline after attesting glue). Reuse the existing
        # clone ONLY if it is the exact pinned commit; anything else is
        # refused, never silently reused.
        if not os.path.isdir(os.path.join(dest, ".git")):
            meta["commit_sha"] = None
            meta["clone_error"] = ("destination exists and is not a git "
                                   "clone; refusing to reuse")
            return meta
        sha = subprocess.run(
            ["git", "-C", dest, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        meta["commit_sha"] = sha
        if expected_sha:
            if sha != expected_sha:
                meta["clone_error"] = (
                    f"existing clone at {sha or 'unknown'} does not match "
                    f"the pinned commit {expected_sha}; refusing to reuse")
                return meta
        else:
            origin = subprocess.run(
                ["git", "-C", dest, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=30).stdout.strip()
            if origin.rstrip("/").removesuffix(".git") != \
                    url.rstrip("/").removesuffix(".git"):
                meta["clone_error"] = (f"existing clone origin {origin!r} "
                                       f"!= requested {url!r}; refusing")
                return meta
        meta["clone_error"] = None
        meta["reused_clone"] = True
    else:
        sha, err = clone_repo(url, dest)
        meta["commit_sha"] = sha
        meta["clone_error"] = err
        if err:
            return meta
    if expected_sha and sha != expected_sha:
        meta["clone_error"] = (f"pin mismatch: expected {expected_sha}, "
                               f"got {sha}; refusing unpinned snapshot")
        return meta
    spdx, lic_file = detect_license(dest)
    meta["license_guess"] = spdx
    meta["license_file"] = lic_file
    meta["license_note"] = ("heuristic text match; verify before reuse"
                            if spdx else "no LICENSE file found")
    meta["languages"] = detect_languages(dest)
    meta["manifests"] = find_manifests(dest)
    meta["tree"] = tree_summary(dest)
    readme_name, readme = read_readme(dest)
    meta["readme_file"] = readme_name
    meta["readme_excerpt"] = readme
    return meta


def save_json(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
