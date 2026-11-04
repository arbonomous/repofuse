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


def read_dependencies(path, manifests):
    deps = {}
    for rel in manifests:
        full = os.path.join(path, rel)
        try:
            if rel.endswith("package.json"):
                data = json.load(open(full, encoding="utf-8"))
                for sec in ("dependencies", "devDependencies"):
                    for name, ver in (data.get(sec) or {}).items():
                        deps[name] = {"spec": ver, "via": rel, "dev": sec == "devDependencies"}
            elif rel.endswith("requirements.txt"):
                for line in open(full, encoding="utf-8", errors="replace"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        m = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)", line)
                        if m:
                            deps[m.group(1).lower()] = {"spec": m.group(2).strip() or "*", "via": rel}
            elif rel.endswith("pyproject.toml"):
                text = open(full, encoding="utf-8", errors="replace").read()
                for m in re.finditer(r"['\"]([A-Za-z0-9_.-]+)(\s*[^'\"]*)['\"]", text):
                    deps.setdefault(m.group(1).lower(),
                                    {"spec": (m.group(2) or "").strip() or "*", "via": rel})
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
    return {
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
