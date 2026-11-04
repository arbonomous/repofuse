"""Source-review gate for everything the sandbox will execute.

Execution condition: no automatic sandbox execution of unreviewed code.
Every file the fused-app test run can execute - model-generated files
(generated/*.py, test_fused.py) AND all vendored third-party files under
vendor/ - must be covered by a host-side attestation pinning the exact
reviewed bytes (sha256) before run_tests_isolated will execute. The
attestation lives OUTSIDE the fusion dir (outside every model write
slot). Vendored code is not model-written, but it is third-party code
about to execute: the same exact-byte review applies, so the vendored
tree is pinned here, not trusted from the vendor manifest alone.

Attestation is a review record, not a security proof: reviewers check for
unittest/runner/introspection/hmac/ctypes/gc monkeypatching or equivalent
interference before attesting. Attestations written before the vendor
scope was added do not cover vendor/ and fail closed.
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


def execution_symlinks(fusion_dir):
    """Any symlink inside the execution tree (generated/, test_fused.py,
    vendor/). The sandbox copies this tree with a link-resolving copy, so
    a symlink would smuggle UNATTESTED bytes into execution. Presence of
    one must fail the review gate, never be silently skipped."""
    hits = []
    probe = os.path.join(fusion_dir, "test_fused.py")
    if os.path.islink(probe):
        hits.append("test_fused.py")
    for sub in ("generated", "vendor"):
        root = os.path.join(fusion_dir, sub)
        if not os.path.isdir(root):
            continue
        for base, dirs, names in os.walk(root):
            for d in list(dirs):
                full = os.path.join(base, d)
                if os.path.islink(full):
                    hits.append(os.path.relpath(full, fusion_dir))
                    dirs.remove(d)
            for n in names:
                full = os.path.join(base, n)
                if os.path.islink(full):
                    hits.append(os.path.relpath(full, fusion_dir))
    return sorted(hits)


def vendored_targets(fusion_dir):
    """Every regular file under vendor/ (relative, sorted). Symlinks are
    never followed here; execution_symlinks() makes their mere presence
    fail the gate instead of being skipped quietly."""
    targets = []
    vendor = os.path.join(fusion_dir, "vendor")
    if not os.path.isdir(vendor):
        return targets
    for base, dirs, names in os.walk(vendor):
        dirs[:] = [d for d in dirs
                   if not os.path.islink(os.path.join(base, d))]
        for n in sorted(names):
            full = os.path.join(base, n)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            targets.append(os.path.relpath(full, fusion_dir))
    return sorted(targets)


def review_targets(fusion_dir):
    """Everything the sandbox can execute: model-generated files plus the
    entire vendored tree."""
    return sorted(generated_targets(fusion_dir)
                  + vendored_targets(fusion_dir))


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_attestation(fusion_dir, path):
    """Pin the current bytes of every file the sandbox can execute
    (generated + vendored). Call this ONLY after a human/agent has
    source-reviewed those exact bytes."""
    links = execution_symlinks(fusion_dir)
    if links:
        raise ValueError(
            "symlinks in execution tree would bypass byte review: "
            + ", ".join(links))
    files = {rel: _sha256(os.path.join(fusion_dir, rel))
             for rel in review_targets(fusion_dir)}
    doc = {"files": files,
           "note": "reviewer attests these exact bytes were source-reviewed "
                   "before execution; not a security proof"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return doc


def check_attestation(fusion_dir, attestation_path, exclude=()):
    """(ok, detail, pending_targets). Files in exclude are not executed and
    are therefore not required to be attested. Covers generated AND
    vendored files: pre-vendor-scope attestations fail closed."""
    links = execution_symlinks(fusion_dir)
    if links:
        return False, ("symlinks in execution tree; the sandbox copy "
                       "would resolve UNREVIEWED bytes - refusing: "
                       + ", ".join(links)), links
    targets = [t for t in review_targets(fusion_dir) if t not in exclude]
    if not targets:
        return True, "no executable files to review", []
    if not attestation_path or not os.path.isfile(attestation_path):
        return False, ("executable files present but not source-reviewed "
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
