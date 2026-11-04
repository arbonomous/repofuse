"""Phase 1 (deterministic) + step DAG: the Fuse-Manifest.

Produces a structured manifest: repo roles, boundary candidates, dependency
conflicts, and the ordered step DAG. Steps that need a model are marked
kind="model" and stay pending until a real model call runs them.
"""
from __future__ import annotations

import re

_WEB_LIBS = {"flask", "fastapi", "django", "express", "react", "vue", "next",
             "starlette", "aiohttp", "http"}
_DATA_LIBS = {"sqlite3", "sqlalchemy", "faiss", "qdrant-client", "chromadb",
              "redis", "pymongo", "duckdb", "numpy"}


def classify_role(analysis):
    deps = {d.lower() for d in analysis["dependencies"]}
    langs = analysis.get("languages_hint") or {}
    imports = {i.lower() for f in analysis.get("python_files", [])
               for i in f.get("imports", [])}
    has_routes = len(analysis["routes"]) >= 2
    if not has_routes and (deps & _DATA_LIBS or imports & _DATA_LIBS):
        return "data", "has data/storage library deps/imports"
    if has_routes or deps & _WEB_LIBS or imports & _WEB_LIBS:
        return "interface", "has HTTP routes or web framework deps/imports"
    if analysis["exports"] and not analysis["entrypoints_hint"]:
        return "engine", "library-style exports, no web surface detected"
    return "unknown", "insufficient signal"


def detect_conflicts(analyses):
    conflicts = []
    # dependency version conflicts on exact pins
    seen = {}
    for a in analyses:
        for name, info in a["dependencies"].items():
            spec = info["spec"]
            pin = re.match(r"==\s*([\d.]+)$", spec) or re.match(r"^([\d.]+)$", spec)
            if not pin:
                continue
            key = name.lower()
            if key in seen and seen[key][0] != pin.group(1):
                conflicts.append({
                    "type": "dependency-version",
                    "dependency": key,
                    "versions": {seen[key][1]: seen[key][0], a["slug"]: pin.group(1)},
                    "resolution": "model",
                })
            else:
                seen[key] = (pin.group(1), a["slug"])
    # top-level module name collisions
    owners = {}
    for a in analyses:
        for f in a["python_files"]:
            mod = f["file"].split("/")[-1]
            if mod in ("__init__.py", "setup.py"):
                continue
            owners.setdefault(mod, set()).add(a["slug"])
    for mod, slugs in sorted(owners.items()):
        if len(slugs) > 1:
            conflicts.append({
                "type": "module-name-collision", "module": mod,
                "repos": sorted(slugs), "resolution": "model",
            })
    # port collisions
    port_owners = {}
    for a in analyses:
        for p in a["ports"]:
            port_owners.setdefault(p, set()).add(a["slug"])
    for p, slugs in sorted(port_owners.items()):
        if len(slugs) > 1:
            conflicts.append({
                "type": "port-collision", "port": p,
                "repos": sorted(slugs), "resolution": "deterministic",
            })
    return conflicts


def boundary_candidates(analyses, roles):
    cands = []
    engines = [a for a in analyses if roles[a["slug"]][0] in ("engine", "data")]
    ifaces = [a for a in analyses if roles[a["slug"]][0] == "interface"]
    for e in engines:
        for i in ifaces:
            cands.append({
                "from": e["slug"], "to": i["slug"],
                "kind": "expose-engine-over-interface",
                "engine_exports": e["exports"][:20],
                "interface_routes": i["routes"][:20],
                "note": "candidate bridge: call engine exports from interface routes; "
                        "semantic match requires the architecture model step",
            })
    if not cands and len(analyses) >= 2:
        cands.append({
            "from": analyses[0]["slug"], "to": analyses[1]["slug"],
            "kind": "unclassified",
            "note": "roles unclear; boundary mapping left to the architecture model step",
        })
    return cands


def build_manifest(metas, analyses):
    for a in analyses:
        m = next(m for m in metas if m["slug"] == a["slug"])
        a["languages_hint"] = m.get("languages", {})
        a["entrypoints_hint"] = [f for f in a["python_files"] if f.get("entrypoint")]
    roles = {a["slug"]: classify_role(a) for a in analyses}
    conflicts = detect_conflicts(analyses)
    boundaries = boundary_candidates(analyses, roles)
    steps = [
        {"id": "ingest", "kind": "deterministic", "status": "done",
         "desc": "clone repos, metadata, license/language detection"},
        {"id": "analyze", "kind": "deterministic", "status": "done",
         "desc": "static export/route/dependency extraction"},
        {"id": "architecture-manifest", "kind": "model", "status": "pending",
         "model": "muse-spark-1.3",
         "desc": "structured JSON bridge map: exports, inputs, arbitrage "
                 "opportunity, required shims"},
        {"id": "resolve-conflicts", "kind": "model", "status": "pending",
         "model": "muse-spark-1.3",
         "desc": "unify dependency specs and namespace collisions; "
                 f"{len(conflicts)} conflict(s) detected deterministically"},
        {"id": "glue-synthesis", "kind": "model", "status": "pending",
         "model": "muse-spark-1.3",
         "desc": "generate adapter shim code (Muse Code CLI is an optional "
                 "harness; the API model is muse-spark-1.3)"},
        {"id": "test-synthesis", "kind": "model", "status": "pending",
         "model": "muse-spark-1.3",
         "desc": "generate integration test file for the fused app"},
        {"id": "asset-generation", "kind": "model", "status": "pending",
         "model": "muse-image",
         "desc": "logo/favicon/design tokens for fused app (optional)"},
        {"id": "verify", "kind": "deterministic", "status": "pending",
         "desc": "run fused-app tests in isolated subprocess"},
        {"id": "auto-heal", "kind": "model", "status": "pending",
         "model": "muse-spark-1.3",
         "desc": "exactly one bounded correction round if verify fails"},
        {"id": "package", "kind": "deterministic", "status": "pending",
         "desc": "emit fused repo bundle + Dockerfile"},
    ]
    return {
        "schema": "repofuse/fuse-manifest@0.1",
        "repos": [{
            "slug": a["slug"], "role": roles[a["slug"]][0],
            "role_reason": roles[a["slug"]][1],
            "exports": a["exports"], "routes": a["routes"],
            "dependency_count": len(a["dependencies"]),
        } for a in analyses],
        "boundary_candidates": boundaries,
        "conflicts": conflicts,
        "steps": steps,
        "honesty": ("Steps marked model/pending require a real Meta Model API "
                    "call. RepoFuse never fabricates their output."),
    }
