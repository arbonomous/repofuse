"""Source-review gate for model-generated glue.

Execution condition (reviewer-mandated): no automatic sandbox execution of
unreviewed model glue. Any model-generated file (generated/*.py and
test_fused.py) must be covered by a host-side attestation pinning the exact
reviewed bytes (sha256) before run_tests_isolated will execute. The
attestation lives OUTSIDE the fusion dir (outside every model write slot).
Attestation is a review record, not a security proof: reviewers check for
unittest/runner/introspection/hmac/ctypes/gc monkeypatching or equivalent
interference before attesting.
"""
from __future__ import annotations

import hashlib
import json
import os


def generated_targets(fusion_dir):
    targets = []
    gen = os.path.join(fusion_dir, "generated")
    if os.path.isdir(gen):
        targets += [os.path.join("generated", f)
                    for f in sorted(os.listdir(gen)) if f.endswith(".py")]
    if os.path.isfile(os.path.join(fusion_dir, "test_fused.py")):
        targets.append("test_fused.py")
    return sorted(targets)


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_attestation(fusion_dir, path):
    """Pin the current bytes of every model-generated file. Call this ONLY
    after a human/agent has source-reviewed those exact bytes."""
    files = {rel: _sha256(os.path.join(fusion_dir, rel))
             for rel in generated_targets(fusion_dir)}
    doc = {"files": files,
           "note": "reviewer attests these exact bytes were source-reviewed "
                   "before execution; not a security proof"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return doc


def check_attestation(fusion_dir, attestation_path, exclude=()):
    """(ok, detail, pending_targets). Files in exclude are not executed and
    are therefore not required to be attested."""
    targets = [t for t in generated_targets(fusion_dir) if t not in exclude]
    if not targets:
        return True, "no model-generated files to execute", []
    if not attestation_path or not os.path.isfile(attestation_path):
        return False, ("model-generated files present but not source-reviewed "
                       "(no attestation); refusing automatic execution"), targets
    try:
        with open(attestation_path, encoding="utf-8") as f:
            doc = json.load(f)
    except (ValueError, OSError) as e:
        return False, f"attestation unreadable: {e}", targets
    files = doc.get("files", {})
    for rel in targets:
        want = files.get(rel)
        if not want:
            return False, f"{rel} not covered by attestation", targets
        if _sha256(os.path.join(fusion_dir, rel)) != want:
            return False, f"{rel} changed since review; re-review required", targets
    return True, "attestation matches reviewed bytes", targets
