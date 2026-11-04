"""Import a saved, independently-reviewed sample build into this checkout.

Reads ONLY the fixed payload paths under builds/<run_id>/, reconstructs
the reviewed app tree (vendored dependencies come from the reviewed
in-repo examples/ tree, never from the payload), re-hashes EVERY file and
compares the full map to the payload's clean manifest. Any mismatch,
unexpected file, unsafe path entry, invalid build record, or existing
target: refuse and leave nothing behind. Never overwrites. No network,
no key, no generation, no paid path - stdlib only.
"""
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ROOT)
RUN_ID = re.compile(r"^run-[0-9a-f]{16}$")
# The payload files this importer will read - nothing else is touched.
PAYLOAD_FILES = ("app/generated/app.py", "app/test_fused.py",
                 "build-state.json", "manifest.json")


class Refused(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_rel(rel):
    """Fail closed on unsafe manifest path entries."""
    if not isinstance(rel, str) or not rel or rel != rel.strip():
        raise Refused(f"unsafe manifest path {rel!r}")
    if rel.startswith("/") or "\\" in rel or "\x00" in rel:
        raise Refused(f"unsafe manifest path {rel!r}")
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise Refused(f"unsafe manifest path {rel!r}")
    if rel != "test_fused.py" and not rel.startswith(("generated/",
                                                      "vendor/")):
        raise Refused(f"manifest path outside the reviewed tree {rel!r}")


def _hash_tree(app_dir):
    files = {}
    for base, dirs, names in os.walk(app_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(names):
            if n.endswith(".pyc"):
                continue
            p = os.path.join(base, n)
            if os.path.islink(p) or not os.path.isfile(p):
                raise Refused(f"non-regular file in tree: {p}")
            rel = os.path.relpath(p, app_dir).replace(os.sep, "/")
            files[rel] = _sha256(p)
    return files


def import_build(run_id, repo_root=REPO_ROOT, out=None):
    if not RUN_ID.match(run_id or ""):
        raise Refused("bad run id")
    payload = os.path.join(repo_root, "builds", run_id)
    if not os.path.isdir(payload):
        raise Refused(f"no saved reviewed build at builds/{run_id}")
    for rel in PAYLOAD_FILES:
        p = os.path.join(payload, rel)
        if os.path.islink(p) or not os.path.isfile(p):
            raise Refused(f"payload missing or unsafe: {rel}")
    try:
        manifest = json.load(open(os.path.join(payload, "manifest.json")))
    except (OSError, ValueError) as e:
        raise Refused(f"manifest unreadable: {e}")
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
        raise Refused("manifest run_id mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise Refused("manifest has no file map")
    for rel, sha in files.items():
        _check_rel(rel)
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise Refused(f"bad hash for {rel!r}")
    # The two payload-shipped files must be pinned by the manifest.
    for rel in ("generated/app.py", "test_fused.py"):
        if rel not in files:
            raise Refused(f"manifest does not pin {rel}")
        actual = _sha256(os.path.join(payload, "app", rel))
        if actual != files[rel]:
            raise Refused(f"payload file {rel} does not match the "
                          "reviewed manifest")
    try:
        state = json.load(open(os.path.join(payload, "build-state.json")))
    except (OSError, ValueError) as e:
        raise Refused(f"build record unreadable: {e}")
    meta = isinstance(state, dict) and state.get("meta")
    if (not isinstance(state, dict) or state.get("run_id") != run_id
            or state.get("status") != "build_ready"
            or not isinstance(meta, dict)
            or not all(isinstance(meta.get(k), str) for k in
                       ("prefix", "field", "app_name", "entity"))):
        raise Refused("build record invalid or not a reviewed ready build")
    runs = os.path.join(repo_root, "studio", "runs")
    approvals = os.environ.get("REPOFUSE_BUILD_APPROVALS") \
        or os.path.join(repo_root, "studio", "build-approvals")
    build_root = os.path.join(runs, f"{run_id}-build")
    approval_path = os.path.join(approvals, f"{run_id}.json")
    if os.path.exists(build_root) or os.path.exists(approval_path):
        raise Refused("this build is already imported - never overwrite")
    vendor_src = os.path.join(repo_root, "examples", "notes-app-fusion",
                              "fused_app", "vendor")
    if not os.path.isdir(vendor_src):
        raise Refused("reviewed in-repo vendor tree missing")
    os.makedirs(build_root)
    try:
        app_dir = os.path.join(build_root, "app")
        shutil.copytree(
            vendor_src, os.path.join(app_dir, "vendor"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        os.makedirs(os.path.join(app_dir, "generated"))
        shutil.copyfile(os.path.join(payload, "app", "generated", "app.py"),
                        os.path.join(app_dir, "generated", "app.py"))
        shutil.copyfile(os.path.join(payload, "app", "test_fused.py"),
                        os.path.join(app_dir, "test_fused.py"))
        actual = _hash_tree(app_dir)
        if actual != files:
            raise Refused(
                "reconstructed tree does not match the reviewed manifest "
                f"({len(actual)} vs {len(files)} files)")
        _atomic_json(os.path.join(build_root, "build-state.json"), state)
        os.makedirs(approvals, exist_ok=True)
        if os.path.exists(approval_path):
            raise Refused("approval manifest already exists - never "
                          "overwrite")
        _atomic_json(approval_path,
                     {"run_id": run_id,
                      "reviewed_at": manifest.get("reviewed_at"),
                      "reviewer": manifest.get("reviewer"),
                      "files": files})
    except BaseException:
        shutil.rmtree(build_root, ignore_errors=True)
        if os.path.exists(approval_path):
            os.unlink(approval_path)
        raise
    return build_root


def _atomic_json(path, data):
    """Atomic write: temp file in the same dir + os.replace, so a crash
    can never leave a half-written build record or approval manifest."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def main(argv):
    run_id = argv[1] if len(argv) > 1 else ""
    try:
        build_root = import_build(run_id)
    except Refused as e:
        print(f"IMPORT REFUSED honestly: {e}")
        return 1
    print(f"Imported the saved reviewed build into {build_root}")
    print("Every file re-hashed and matched the reviewed manifest.")
    print("Next: sh studio/run.sh then open http://127.0.0.1:8317/ and "
          'click "Open the saved reviewed AI-built notes app".')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
