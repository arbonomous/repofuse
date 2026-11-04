"""Independent acceptance criteria, derived deterministically from the input
repos - NOT from the generated glue. The generated test suite is judged
against these, so a test file that merely re-asserts what the glue says
cannot pass review.

Two deterministic checks:
1. criteria_coverage: the generated test must reference the vendored repos'
   real modules/exports (actual incorporation), not just the glue files.
2. vacuity control (in verify): the same test suite must FAIL when the glue
   is removed. Tests that pass without the fusion are vacuous.
"""
from __future__ import annotations

import ast
import os


def derive_criteria(manifest, analyses):
    """Acceptance criteria from static analysis of the INPUT repos."""
    criteria = []
    roles = {r["slug"]: r["role"] for r in manifest["repos"]}
    for a in analyses:
        slug = a["slug"]
        role = roles.get(slug, "unknown")
        top_exports = a["exports"][:10]
        if role in ("engine", "data") and top_exports:
            criteria.append({
                "id": f"use-{slug}-exports",
                "repo": slug,
                "criterion": f"fused app must actually call at least one real "
                             f"{slug} export (candidates: {', '.join(top_exports)})",
                "check": "test imports a vendored module and calls a real export",
            })
        if role == "interface":
            criteria.append({
                "id": f"expose-{slug}-behavior",
                "repo": slug,
                "criterion": f"fused app must expose working behavior built on "
                             f"{slug} (framework: {', '.join(sorted({i for f in a['python_files'] for i in f['imports'] if i in ('microdot', 'flask', 'fastapi')})) or 'unknown'})",
                "check": "test exercises the running app behavior end-to-end",
            })
    criteria.append({
        "id": "not-vacuous",
        "repo": None,
        "criterion": "test suite must FAIL when glue files are removed",
        "check": "deterministic negative control in verify",
    })
    return criteria


def check_test_independence(fusion_dir, vendor_root):
    """Static check: test_fused.py must incorporate vendored repo code.

    Returns dict with observed imports and a boolean verdict. Heuristic and
    labeled as such; the vacuity control is the stronger signal.
    """
    test_file = os.path.join(fusion_dir, "test_fused.py")
    if not os.path.exists(test_file):
        return {"independent": False, "reason": "no test file"}
    src = open(test_file, encoding="utf-8", errors="replace").read()
    vendored_modules = set()
    for slug in os.listdir(vendor_root):
        slug_dir = os.path.join(vendor_root, slug)
        if not os.path.isdir(slug_dir):
            continue
        for fn in os.listdir(slug_dir):
            if fn.endswith(".py") and not fn.startswith("__"):
                vendored_modules.add(fn[:-3])
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"independent": False, "reason": "test file does not parse"}
    imported = set()
    referenced = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0].split("/")[-1] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for mod in vendored_modules:
        if mod in imported or (mod + ".") in src or (mod + "(") in src:
            referenced.add(mod)
    return {
        "independent": bool(referenced),
        "vendored_modules_available": sorted(vendored_modules),
        "vendored_modules_referenced": sorted(referenced),
        "note": "heuristic: test must reference at least one vendored input "
                "module; vacuity control in verify is the stronger signal",
    }
