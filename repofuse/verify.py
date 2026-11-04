"""Phase 4: verification of the fused app. See sandbox.py for isolation.

RepoFuse never runs untrusted code with only an environment scrub. A
behavioral pass requires: static compile ok, import closure ok (only stdlib
+ vendored + generated modules), the sandbox run returning 0, AND unittest
reporting at least 1 test run with an OK verdict - a bare exit code 0 (or a
zero-test suite, or sys.exit(0)) never counts as a pass.
"""
from __future__ import annotations

import ast
import os
import sys

from .sandbox import run_tests_isolated, bwrap_available

def _import_closure_ok(fusion_dir):
    """Generated+test code may import only stdlib, vendored, or generated."""
    allowed = set(sys.stdlib_module_names)
    vendor = os.path.join(fusion_dir, "vendor")
    if os.path.isdir(vendor):
        for slug in os.listdir(vendor):
            slug_dir = os.path.join(vendor, slug)
            if not os.path.isdir(slug_dir):
                continue
            for base in (slug_dir, os.path.join(slug_dir, "src"),
                         os.path.join(slug_dir, "lib")):
                if not os.path.isdir(base):
                    continue
                for fn in os.listdir(base):
                    full = os.path.join(base, fn)
                    if fn.endswith(".py") and not fn.startswith("__"):
                        allowed.add(fn[:-3])
                    elif os.path.isdir(full) and os.path.exists(
                            os.path.join(full, "__init__.py")):
                        allowed.add(fn)
    targets = []
    gen_dir = os.path.join(fusion_dir, "generated")
    allowed.update(("generated", "vendor"))
    if os.path.isdir(gen_dir):
        targets += [os.path.join(gen_dir, f) for f in os.listdir(gen_dir)
                    if f.endswith(".py")]
        allowed.update(os.path.basename(f)[:-3] for f in targets)
    test_file = os.path.join(fusion_dir, "test_fused.py")
    if os.path.exists(test_file):
        targets.append(test_file)
    unknown = {}
    for full in targets:
        try:
            tree = ast.parse(open(full, encoding="utf-8",
                                  errors="replace").read())
        except SyntaxError as e:
            unknown[os.path.basename(full)] = [f"<unparseable: {e}>"]
            continue
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        bad = sorted(m for m in mods
                     if m not in allowed and m != "test_fused")
        if bad:
            unknown[os.path.basename(full)] = bad
    return unknown


def verify_fused_app(fusion_dir, timeout=90, test_module="test_fused",
                     attestation_path=None):
    unknown = _import_closure_ok(fusion_dir)
    if unknown:
        return {"status": "failed", "stage": "import-closure",
                "detail": f"unvendored/unknown imports: {unknown}"}
    res = run_tests_isolated(fusion_dir, timeout=timeout,
                             test_module=test_module,
                             attestation_path=attestation_path)
    # status is driven by the HMAC-signed verdict from the trusted runner
    # inside the sandbox; see sandbox.py.
    return res


def vacuity_control(fusion_dir, glue_files, timeout=90,
                    test_module="test_fused", attestation_path=None):
    """Negative control: the same tests must FAIL with the glue removed."""
    if not bwrap_available():
        return {"status": "not_run_no_isolation"}
    generated = [f for f in glue_files
                 if os.path.basename(f) != (test_module + ".py")
                 and f.endswith(".py")]
    if not generated:
        return {"status": "not_applicable", "reason": "no glue files recorded"}
    res = run_tests_isolated(fusion_dir, timeout=timeout,
                             exclude_files=generated,
                             test_module=test_module,
                             attestation_path=attestation_path)
    if res["status"] in ("failed", "timeout"):
        return {"status": "vacuity_confirmed",
                "detail": "tests fail without glue: they exercise the fusion",
                "control_run": res["status"]}
    if res["status"] == "passed":
        return {"status": "vacuous_tests",
                "detail": "tests PASS without the glue: they prove nothing "
                          "about the fusion - rejecting result"}
    return {"status": "inconclusive", "control_run": res}
