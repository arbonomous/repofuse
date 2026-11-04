"""Assemble the evidence report: observed facts only."""
from __future__ import annotations

import json
import os
import time


def build_report(out_dir, metas, manifest, synthesis, verification):
    tel = []
    tel_path = os.path.join(out_dir, "telemetry.jsonl")
    if os.path.exists(tel_path):
        from . import telemetry
        tel = telemetry.read_log(tel_path)
    safety = None
    safety_path = os.path.join(out_dir, "safety.json")
    if os.path.exists(safety_path):
        try:
            with open(safety_path, encoding="utf-8") as f:
                safety = json.load(f)
        except (OSError, ValueError):
            safety = {"status": "unknown", "note": "safety.json unreadable"}
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "repofuse 0.1.0",
        "safety_qualification": safety,
        "repos": [{
            "url": m["url"], "commit_sha": m["commit_sha"],
            "license_guess": m["license_guess"],
            "license_note": m["license_note"],
            "languages": m["languages"],
        } for m in metas],
        "manifest": manifest,
        "synthesis": synthesis,
        "verification": verification,
        "telemetry": tel,
        "incorporation": {
            "vendored_into_app": os.path.exists(
                os.path.join(out_dir, "vendor_manifest.json")),
            "vendor_manifest": "vendor_manifest.json (per-file sha256 + commit SHAs)",
            "shown_to_model": "summaries only: exports, routes, dependency "
                              "names, README excerpt, tree sample - never full source",
            "license_obligations": "vendored code keeps its own LICENSE files; "
                                   "detected licenses are heuristic guesses - "
                                   "verify before publishing a fusion",
        },
        "claims_policy": [
            "Every pass/fail above is an observed subprocess result.",
            "License IDs are heuristic text matches; verify before reuse.",
            "Model steps left pending are pending; no fabricated output.",
            "This report makes no production-readiness or novelty claims.",
        ],
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report
