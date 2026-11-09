"""Static safety qualification for input repos BEFORE any spend or run.

Answers the user's requirement honestly: before RepoFuse builds with a chosen
repo, say what passed, what failed, and what could not be checked - and
block when a required check is missing. This is STATIC analysis plus
OPTIONAL live advisory reads. It is not isolation (bubblewrap owns that),
not a guarantee: a clean verdict never means "proven harmless".

Verdicts per repo: pass / warn / fail / unknown. Aggregation is
fail > unknown > warn > pass. BLOCKING = fail, unknown, or an
unacknowledged warn. An offline advisory, a missing commit, a malformed
spec, or a failed advisory read is unknown and blocks. A dependency this
build does not install is reported and does not block. A warn blocks
spending or execution until a reviewer explicitly acknowledges it.

Coverage is exactly what the verdict says: the repo itself (via its commit
advisory mapping) plus PINNED DIRECT dependencies. Transitive dependencies
are NOT resolved here - that scope is stated on every verdict, never
implied away.

Live advisory reads (osv.dev) are OFF by default ("offline mode - not
run"). When enabled they POST only: the repo commit SHA and each pinned
direct dependency's name + exact version + ecosystem to the official
endpoint. Unpinned specs and tool options never reach the payload (an
allowlist admits only exact pins). Unreachable/timeout/malformed =
unknown = blocks, and is reported as a failed read - never confused with
offline mode.

Empty-result semantics (official API contract, post-v1-query docs, read
2026-11-04): the API "lists vulnerabilities" MATCHING the query subject.
A successful response with zero matches is exactly that - no records
matched. It does NOT establish that the commit or package is indexed by
OSV, and it is never reported as proof of being vulnerability-free.
Per policy it maps to WARN (flagged for reviewer acknowledgment), while
anything unresolved maps to UNKNOWN, and any match to FAIL.
"""
import ast
import json
import math
import os
import re
import time
import urllib.request

OSV_QUERYBATCH = "https://api.osv.dev/v1/querybatch"  # official, grounded 2026-11-04
OSV_TIMEOUT_S = 15
OSV_MAX_QUERIES = 1000

_SOURCE_EXT = {".py", ".pyi", ".js", ".ts", ".jsx", ".tsx", ".sh"}
_MAX_FILES = 4000
_MAX_FILE_BYTES = 2 * 1024 * 1024
_ENTROPY_MIN_LEN = 200


class Verdict:
    PASS, WARN, FAIL, UNKNOWN = "pass", "warn", "fail", "unknown"


_RANK = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.UNKNOWN: 2, Verdict.FAIL: 3}


def _worst(statuses):
    return max(statuses, key=lambda s: _RANK[s], default=Verdict.PASS)


def _entropy(s):
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _iter_files(path):
    count = 0
    for base, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__",
                                                "node_modules")]
        for n in sorted(names):
            if count >= _MAX_FILES:
                return
            full = os.path.join(base, n)
            if os.path.islink(full):
                yield full, n, "symlink"
                continue
            try:
                if os.path.getsize(full) > _MAX_FILE_BYTES:
                    yield full, n, "oversize"
                    continue
            except OSError:
                yield full, n, "unreadable"
                continue
            count += 1
            yield full, n, "file"


# ---------------- static checks ----------------

def _check_pyc_without_source(path):
    findings = []
    for base, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        sources = {os.path.splitext(n)[0] for n in names if n.endswith(".py")}
        for n in names:
            if n.endswith((".pyc", ".pyo")) and \
                    os.path.splitext(n)[0].rsplit(".", 1)[0] not in sources:
                findings.append({
                    "rule": "pyc-without-source", "severity": Verdict.FAIL,
                    "file": os.path.relpath(os.path.join(base, n), path),
                    "detail": "compiled bytecode with no matching source - "
                              "unreviewable content"})
    return findings


def _check_install_hooks(path):
    findings = []
    for rel, pats in (("setup.py", ("cmdclass", "install.run",
                                    "CustomInstall")),
                      ("package.json", ("preinstall", "postinstall",
                                        "prepare")),
                      ("Makefile", ("curl", "wget")),
                      ("setup.cfg", ("cmdclass",))):
        full = os.path.join(path, rel)
        if not os.path.isfile(full) or os.path.islink(full):
            continue
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            findings.append({"rule": "install-hook", "severity": Verdict.UNKNOWN,
                             "file": rel, "detail": "manifest unreadable"})
            continue
        for pat in pats:
            if pat in text:
                findings.append({
                    "rule": "install-hook", "severity": Verdict.WARN,
                    "file": rel,
                    "detail": f"install-time code path ({pat}); RepoFuse "
                              "never installs repos, but flag for review"})
    return findings


def _b64_exec_chain(tree):
    """True when the same module decodes a base64/zlib/marshal blob AND
    evals/exec-s - the classic obfuscated-payload shape."""
    has_decode, has_exec = False, False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = ""
        if isinstance(f, ast.Attribute):
            name = f.attr
        elif isinstance(f, ast.Name):
            name = f.id
        if name in ("b64decode", "a85decode", "b32decode", "decompress",
                    "loads") and isinstance(f, ast.Attribute):
            obj = f.value
            mod = obj.id if isinstance(obj, ast.Name) else ""
            if mod in ("base64", "zlib", "marshal", "bz2", "lzma"):
                has_decode = True
        if name in ("eval", "exec") and node.args and \
                not isinstance(node.args[0], ast.Constant):
            has_exec = True
    return has_decode and has_exec


def _check_python_file(full, rel):
    findings = []
    try:
        src = open(full, encoding="utf-8", errors="replace").read()
    except OSError:
        return [{"rule": "unreadable", "severity": Verdict.UNKNOWN,
                 "file": rel, "detail": "source file unreadable"}]
    if len(src) > _MAX_FILE_BYTES:
        return [{"rule": "oversize", "severity": Verdict.UNKNOWN,
                 "file": rel, "detail": "source file too large to scan"}]
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return findings  # not necessarily malicious; analysis stays honest
    if _b64_exec_chain(tree):
        findings.append({"rule": "obfuscated-payload",
                         "severity": Verdict.FAIL, "file": rel,
                         "detail": "encoded-blob decode combined with "
                                   "dynamic eval/exec"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else \
                (f.id if isinstance(f, ast.Name) else "")
            if name in ("eval", "exec") and node.args and \
                    not isinstance(node.args[0], ast.Constant):
                findings.append({"rule": "dynamic-exec",
                                 "severity": Verdict.WARN, "file": rel,
                                 "detail": "dynamic eval/exec of "
                                           "non-constant code"})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names]
                    if isinstance(node, ast.Import) else [node.module or ""])
            for mod in mods:
                root = (mod or "").split(".")[0]
                if root in ("ctypes", "cffi", "_ctypes"):
                    findings.append({"rule": "native-loading",
                                     "severity": Verdict.WARN, "file": rel,
                                     "detail": f"native code loading "
                                               f"({mod}) bypasses Python "
                                               "source review"})
    for m in re.finditer(r"['\"]([A-Za-z0-9+/=]{%d,})['\"]" % _ENTROPY_MIN_LEN,
                         src):
        if _entropy(m.group(1)) > 4.5:
            findings.append({"rule": "high-entropy-blob",
                             "severity": Verdict.WARN, "file": rel,
                             "detail": "long high-entropy string - possible "
                                       "obfuscated payload"})
            break
    return findings


def static_scan(path):
    """All static checks for one cloned repo. Never executes anything."""
    findings = _check_pyc_without_source(path) + _check_install_hooks(path)
    scanned = 0
    for full, name, kind in _iter_files(path):
        if kind == "symlink":
            findings.append({"rule": "symlink-entry",
                             "severity": Verdict.WARN,
                             "file": os.path.relpath(full, path),
                             "detail": "symlink in repo tree; vendoring "
                                       "copies target content, review the "
                                       "target"})
            continue
        if kind in ("oversize", "unreadable"):
            source = (os.path.splitext(name)[1] in _SOURCE_EXT
                      or name == "setup.py")
            findings.append({
                "rule": kind,
                "severity": Verdict.UNKNOWN if source else Verdict.WARN,
                "file": os.path.relpath(full, path),
                "detail": ("source file not fully scanned"
                           if source else
                           "non-source file not fully scanned and not executed"),
            })
            continue
        if os.path.splitext(name)[1] in _SOURCE_EXT or name == "setup.py":
            scanned += 1
            if name.endswith((".py", ".pyi")) or name == "setup.py":
                findings.extend(_check_python_file(
                    full, os.path.relpath(full, path)))
    return {"status": _worst([f["severity"] for f in findings]),
            "files_scanned": scanned, "findings": findings}


# ---------------- dependency advisory (optional live read) ----------------

def _pinned_version(spec):
    """Admit ONLY an exact pin ([A-Za-z0-9._+-]); ranges, wildcards, and
    anything carrying flags or options are not sent to OSV."""
    m = re.match(r"^==\s*([A-Za-z0-9._+-]+)$", (spec or "").strip())
    return m.group(1) if m else None


def _malformed_spec(spec):
    """Option injection and URLs are not ordinary uninstalled requirements."""
    text = spec or ""
    return ("--" in text or ";" in text or "://" in text
            or "\n" in text or "\x00" in text)


def _ecosystem(via):
    """Map a manifest to an OSV ecosystem. Unknown manifest -> None,
    which makes the advisory UNKNOWN rather than guessing."""
    if via.endswith("package.json"):
        return "npm"
    if via.endswith(("requirements.txt", "pyproject.toml", "setup.py",
                     "setup.cfg", "Pipfile")):
        return "PyPI"
    return None


def osv_check(deps, repo_commit=None, allow_network=False, opener=None):
    """Known-vulnerability advisory via the official OSV querybatch
    endpoint.

    Covers the repo itself (commit-based advisory query, when a commit is
    known) plus pinned DIRECT dependencies (name + exact version +
    ecosystem). Transitive dependencies are NOT resolved - every verdict
    states that scope. OFF by default (offline mode); unreachable,
    timeout, or malformed response = UNKNOWN, reported as a failed read.
    A missing commit, a malformed spec, or a failed read is UNKNOWN and
    blocks. A dependency this build does not install is reported in
    not_installed and does not change the verdict. Never raises, never
    fabricates a check: queries_made reports the real count.
    """
    out = {"status": Verdict.UNKNOWN, "source": "offline mode",
           "queries_made": 0, "vulnerabilities": [], "unresolved": [],
           "not_installed": [], "development_unresolved": [],
           "scope": "repo commit advisory + pinned direct dependencies "
                    "only; transitive dependencies are not resolved. "
                    "Development extras are reported and are not a runtime block",
           "note": "advisory not run (offline mode); required check "
                   "unknown -> blocks execution"}
    queries, keyed = [], []
    if repo_commit:
        queries.append({"commit": repo_commit})
        keyed.append({"kind": "repo", "ref": repo_commit})
    else:
        out["unresolved"].append({"name": "(repo itself)",
                                  "reason": "no commit reference for "
                                            "advisory mapping"})
    for name, info in sorted((deps or {}).items()):
        via = info.get("via", "")
        spec = info.get("spec") or "*"
        ver = _pinned_version(spec)
        eco = _ecosystem(via)
        item = {"name": name, "spec": spec, "via": via,
                "reason": "unresolved version" if not ver else
                "unresolved ecosystem"}
        if info.get("dev"):
            if not ver or not eco:
                out["development_unresolved"].append(item)
            continue
        if _malformed_spec(spec):
            out["unresolved"].append(item)
            continue
        if not ver or not eco:
            item["reason"] = "not installed by this build"
            out["not_installed"].append(item)
            continue
        queries.append({"package": {"name": name, "ecosystem": eco},
                        "version": ver})
        keyed.append({"kind": "dependency", "ref": name})
    if not allow_network:
        return out
    if not queries:
        out.update({"status": Verdict.UNKNOWN, "source": OSV_QUERYBATCH,
                    "note": "no queries made: no commit reference and no "
                            "pinned direct dependencies - nothing was "
                            "actually checked"})
        return out
    if len(queries) > OSV_MAX_QUERIES:
        out["note"] = (f"{len(queries)} required queries exceed one "
                       "bounded advisory read; not run")
        return out
    try:
        body = json.dumps({"queries": queries}).encode()
        req = urllib.request.Request(
            OSV_QUERYBATCH, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        open_fn = opener or urllib.request.urlopen
        with open_fn(req, timeout=OSV_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
        results = data["results"]
        assert isinstance(results, list) and len(results) == len(queries)
        vulns = []
        for key, res in zip(keyed, results):
            for v in (res or {}).get("vulns") or []:
                vulns.append({"id": v.get("id"), "kind": key["kind"],
                              "subject": key["ref"],
                              "modified": v.get("modified")})
        n_repo = sum(1 for k in keyed if k["kind"] == "repo")
        n_dep = len(keyed) - n_repo
        made = (f"{len(queries)} OSV query(ies) made: {n_repo} repo-commit "
                f"+ {n_dep} pinned direct dependency")
        if vulns:
            status = Verdict.FAIL
            note = (f"{len(vulns)} known vulnerability record(s) matched "
                    f"({made})")
        elif out["unresolved"]:
            status = Verdict.UNKNOWN
            note = (f"{made}; 0 matching records returned, but "
                    f"{len(out['unresolved'])} item(s) are unresolved - "
                    "their vulnerability status is unknown")
        else:
            # A request was made and zero records matched. That is NOT a
            # covered pass: an empty result does not establish the subject
            # is indexed by OSV or free of vulnerabilities. Flag for
            # reviewer acknowledgment instead of claiming safety.
            status = Verdict.WARN
            note = (f"{made}; 0 matching vulnerability records returned. "
                    "An empty result does not establish the subject is "
                    "indexed by OSV or vulnerability-free - flagged for "
                    "reviewer acknowledgment, not claimed as safe")
        extras = out.get("development_unresolved") or []
        if extras:
            note += (f" {len(extras)} development extra(s) are outside "
                     "this runtime check and do not change the verdict.")
        skipped = out.get("not_installed") or []
        if skipped:
            note += (f" {len(skipped)} declared dependency(ies) are not "
                     "installed by this build and were not queried.")
        out.update({"status": status, "source": OSV_QUERYBATCH,
                    "queries_made": len(queries),
                    "vulnerabilities": vulns, "note": note})
    except Exception as e:  # unreachable, timeout, malformed: all unknown
        out.update({"status": Verdict.UNKNOWN, "source": OSV_QUERYBATCH,
                    "note": f"advisory read failed: {type(e).__name__}: "
                            f"{e} - required check unknown -> blocks"})
    return out


# ---------------- aggregation + gating ----------------

def qualify_repo(slug, path, deps=None, repo_commit=None,
                 allow_network=False, opener=None):
    """Full qualification verdict for one repo. BLOCKING = fail|unknown,
    or warn until a reviewer acknowledges it (see qualify_run)."""
    static = static_scan(path)
    advisory = osv_check(deps or {}, repo_commit=repo_commit,
                         allow_network=allow_network, opener=opener)
    status = _worst([static["status"], advisory["status"]])
    return {"repo": slug, "status": status,
            "blocking": status in (Verdict.FAIL, Verdict.UNKNOWN),
            "static": static, "dependencies": advisory}


def qualify_run(repo_verdicts, warnings_acknowledged=False,
                acknowledged_via=None):
    """Run-level verdict + honest summary. Blocks if ANY repo is fail or
    unknown, or if any warn has not been explicitly acknowledged (warns
    block spending and execution until a reviewer signs off)."""
    status = _worst([v["status"] for v in repo_verdicts])
    warn_pending = (any(v["status"] == Verdict.WARN for v in repo_verdicts)
                    and not warnings_acknowledged)
    blocking = (any(v["blocking"] for v in repo_verdicts) or warn_pending)
    out = {"status": status, "blocking": blocking,
           "warnings_acknowledged": bool(warnings_acknowledged),
           "repos": repo_verdicts,
           "honesty": ("Static scans and advisory lookups reduce risk; "
                       "they cannot prove a repo harmless. Static findings "
                       "are matching suspicious signals, never proof of "
                       "absence. Advisory coverage is the repo commit "
                       "plus pinned direct dependencies; transitive "
                       "dependencies are not resolved, and an empty "
                       "advisory result does not establish indexed "
                       "coverage. Acknowledging a warn clears only this "
                       "gate - execution still requires isolation plus "
                       "independent review of the exact vendored and "
                       "generated bytes.")}
    if warnings_acknowledged:
        out["acknowledgment"] = {"via": acknowledged_via or "unspecified",
                                 "at": time.strftime(
                                     "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return out
