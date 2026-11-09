"""Phase 1 (deterministic part): capability and dependency extraction.

Python: real stdlib ast parsing for top-level exports.
JavaScript/TypeScript: regex heuristics, explicitly labeled as such.
No cloned code is executed.
"""
from __future__ import annotations

import ast
import json
import os
import re

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
              "test", "tests", "example", "examples", "docs", "doc"}
_PY_ROUTE = re.compile(
    r"@(?:app|router|bp)\.(get|post|put|delete|patch|route)\(\s*['\"]([^'\"]+)")
_JS_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(get|post|put|delete|patch|use)\(\s*['\"]([^'\"]+)")
_JS_EXPORT = re.compile(
    r"(?:export\s+(?:default\s+)?(?:function|class|const|let)\s+([A-Za-z_$][\w$]*)"
    r"|module\.exports\s*=\s*([A-Za-z_$][\w$]*)?)")
_ENV = re.compile(r"os\.environ(?:\.get)?\(?\[?['\"]([A-Z_][A-Z0-9_]+)"
                  r"|process\.env\.([A-Z_][A-Z0-9_]+)")
_PORT = re.compile(r"(?:port\s*[=:]\s*|listen\(\s*|:(\d{4,5})\b)")


MAX_FILE_BYTES = 2 * 1024 * 1024


def _iter_files(path, exts):
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS
                   and not os.path.islink(os.path.join(root, d))]
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full):
                continue
            if os.path.splitext(fn)[1].lower() in exts:
                try:
                    if os.path.getsize(full) > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield full


def analyze_python_file(full, rel):
    out = {"file": rel, "exports": [], "imports": [], "routes": [],
           "entrypoint": False, "parse_error": None}
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        out["parse_error"] = f"{e.__class__.__name__}: {e}"
        tree = None
    if tree is not None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    out["exports"].append(node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                out["imports"].extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                out["imports"].append(node.module.split(".")[0])
        out["entrypoint"] = any(
            isinstance(n, ast.If) for n in tree.body) and "__main__" in src
    for m in _PY_ROUTE.finditer(src):
        out["routes"].append({"method": m.group(1).upper(), "path": m.group(2)})
    return out


def analyze_js_file(full, rel):
    out = {"file": rel, "exports": [], "imports": [], "routes": [],
           "heuristic": True}
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()
    for m in _JS_ROUTE.finditer(src):
        out["routes"].append({"method": m.group(1).upper(), "path": m.group(2)})
    for m in _JS_EXPORT.finditer(src):
        name = m.group(1) or m.group(2)
        if name:
            out["exports"].append(name)
    for m in re.finditer(r"(?:require\(|from\s+)['\"]([^'\"./][^'\"]*)['\"]", src):
        out["imports"].append(m.group(1).split("/")[0])
    return out


# Strict PEP 508-ish project name; anything else (tool flags like
# "--strict-markers", pytest addopts, bare options) is not a dependency.
_DEP_NAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
_DEP_LINE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*([^;#]*)")
# A version spec must start with a comparison operator or a wildcard;
# a bare second word ("bad name") is not a requirement.
_DEP_SPEC = re.compile(r"^(==|>=|<=|~=|!=|>|<|\*|[0-9])")


def _add_dep(deps, raw, via):
    """Record one dependency iff the raw string is actually a package
    requirement. Returns True when recorded."""
    raw = raw.strip().strip("'\"").strip()
    if not raw or raw.startswith(("-", "#")):
        return False
    m = _DEP_LINE.match(raw)
    if not m or not _DEP_NAME.match(m.group(1)):
        return False
    spec = (m.group(3) or "").strip()
    if spec and not _DEP_SPEC.match(spec):
        return False
    name = m.group(1).lower()
    created = name not in deps
    deps.setdefault(name, {"spec": spec or "*", "via": via})
    return name, created


def _pyproject_dependencies(text):
    """Dependency requirement strings, including optional extras."""
    return [spec for spec, _dev in _pyproject_roles(text)]


def _pyproject_roles(text):
    """Section-scoped extraction: only the [project] dependencies array
    and [project.optional-dependencies] values count. Tool sections
    ([tool.pytest.ini_options] addopts etc.) are NOT dependencies -
    a 2026-11-04 review found the previous whole-file regex misparsed
    pytest flags as packages (85 of 99 entries inflated)."""
    section = None
    collecting = False
    optional = False
    role = False
    buf = ""
    out = []

    def flush():
        nonlocal buf, collecting
        if "]" in buf:
            array = buf[:buf.index("]")]
            for m in re.finditer(r"['\"]([^'\"]+)['\"]", array):
                out.append((m.group(1), role))
        buf = ""
        collecting = False

    for line in text.splitlines():
        stripped = line.strip()
        sec = re.match(r"^\[\s*([A-Za-z0-9_.-]+)\s*\]", stripped)
        if sec:
            flush()
            section = sec.group(1)
            optional = section.startswith("project.optional-dependencies")
            continue
        if collecting:
            if optional and re.match(r"^[A-Za-z_.-]+\s*=", stripped):
                flush()  # next optional-dependency key
            elif not optional and re.match(r"^[A-Za-z_.-]+\s*=", stripped):
                flush()  # a new [project] key ends the array
                continue
            else:
                buf += " " + stripped
                if "]" in stripped:
                    flush()
            continue
        if section == "project" and re.match(r"^dependencies\s*=", stripped):
            buf = stripped.split("=", 1)[1]
            role = False
            collecting = True
            if "]" in buf:
                flush()
        elif optional and re.match(r"^[A-Za-z_.-]+\s*=", stripped):
            buf = stripped.split("=", 1)[1]
            role = True
            collecting = True
            if "]" in buf:
                flush()
    flush()
    return out


def _mark_dev(deps, recorded, dev):
    if not recorded:
        return
    name, created = recorded
    if created and dev:
        deps[name]["dev"] = True
    elif not created and not dev:
        deps[name].pop("dev", None)


def _development_manifest(rel):
    """Requirements that install a library's tests or docs, not its runtime."""
    parts = rel.replace("\\", "/").split("/")
    return parts[0] in {
        "tests", "test", "testing", "docs", "doc", "ci",
        "benchmark", "benchmarks", "examples",
    }


def read_dependencies(path, manifests):
    deps = {}
    for rel in manifests:
        full = os.path.join(path, rel)
        try:
            if rel.endswith("package.json"):
                data = json.load(open(full, encoding="utf-8"))
                for sec in ("dependencies", "devDependencies"):
                    for name, ver in (data.get(sec) or {}).items():
                        if _DEP_NAME.match(name):
                            deps[name] = {"spec": ver, "via": rel,
                                          "dev": sec == "devDependencies"}
            elif rel.endswith("requirements.txt"):
                dev = _development_manifest(rel)
                for line in open(full, encoding="utf-8", errors="replace"):
                    _mark_dev(deps, _add_dep(deps, line, rel), dev)
            elif rel.endswith("pyproject.toml"):
                text = open(full, encoding="utf-8", errors="replace").read()
                for dep, dev in _pyproject_roles(text):
                    _mark_dev(deps, _add_dep(deps, dep, rel), dev)
        except (OSError, ValueError):
            continue
    return deps


def detect_env_and_ports(path):
    env, ports = set(), set()
    for full in _iter_files(path, {".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".env"}):
        try:
            src = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in _ENV.finditer(src):
            env.add(m.group(1) or m.group(2))
        for m in re.finditer(r"(?:listen\(|port\s*[=:]\s*)\s*(\d{4,5})", src):
            ports.add(int(m.group(1)))
    return sorted(env), sorted(p for p in ports if 1024 <= p <= 65535)


def analyze(meta):
    """Full static analysis of one ingested repo. Returns analysis dict."""
    path = meta["path"]
    py_files, js_files = [], []
    for full in _iter_files(path, {".py"}):
        py_files.append(analyze_python_file(full, os.path.relpath(full, path)))
    for full in _iter_files(path, {".js", ".ts", ".jsx", ".tsx"}):
        js_files.append(analyze_js_file(full, os.path.relpath(full, path)))
    exports = sorted({e for f in py_files + js_files for e in f["exports"]})
    routes = [r for f in py_files + js_files for r in f["routes"]]
    deps = read_dependencies(path, meta.get("manifests", []))
    env, ports = detect_env_and_ports(path)
    from .api_evidence import package_api
    return {
        "api_evidence": package_api(path, meta["slug"]),
        "slug": meta["slug"],
        "exports": exports,
        "routes": routes,
        "dependencies": deps,
        "env_vars": env,
        "ports": ports,
        "python_files": py_files,
        "js_files": js_files,
        "notes": ["JS/TS extraction is regex-based heuristic; "
                  "Python extraction uses stdlib ast."],
    }
