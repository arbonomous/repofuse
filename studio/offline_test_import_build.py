"""Offline gates for studio/import_build.py: the saved-reviewed-build
importer must reconstruct the exact reviewed tree and refuse everything
else - tampered payload, unsafe manifest paths, missing pins, invalid
build records, pre-existing targets. No network, no key, no calls.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import import_build

RUN = "run-1f58ac57911bb892"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = []


def check(name, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  ok  {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"FAIL  {name}: {e}")


def make_root(with_vendor=True):
    """A fake checkout holding the real payload (and real vendor)."""
    root = tempfile.mkdtemp(prefix="repofuse-import-test-")
    shutil.copytree(os.path.join(REPO, "builds", RUN),
                    os.path.join(root, "builds", RUN))
    if with_vendor:
        shutil.copytree(
            os.path.join(REPO, "examples", "notes-app-fusion",
                         "fused_app", "vendor"),
            os.path.join(root, "examples", "notes-app-fusion",
                         "fused_app", "vendor"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs(os.path.join(root, "studio", "runs"))
    return root


def t_happy_path_reconstructs_and_verifies():
    root = make_root()
    try:
        build_root = import_build.import_build(RUN, repo_root=root)
        app_dir = os.path.join(build_root, "app")
        assert import_build._hash_tree(app_dir) == json.load(open(
            os.path.join(root, "builds", RUN, "manifest.json")))["files"]
        st = json.load(open(os.path.join(build_root, "build-state.json")))
        assert st["run_id"] == RUN and st["status"] == "build_ready"
        ap = json.load(open(os.path.join(root, "studio", "build-approvals",
                                         f"{RUN}.json")))
        assert ap["run_id"] == RUN and len(ap["files"]) == 441
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("happy path: exact reviewed tree reconstructed and verified",
      t_happy_path_reconstructs_and_verifies)


def _refused(root, needle):
    try:
        import_build.import_build(RUN, repo_root=root)
        raise AssertionError("import accepted a bad payload")
    except import_build.Refused as e:
        assert needle in str(e), f"{needle!r} not in {e}"
    assert not os.path.exists(os.path.join(
        root, "studio", "runs", f"{RUN}-build")), "refusal left a run dir"
    assert not os.path.exists(os.path.join(
        root, "studio", "build-approvals", f"{RUN}.json")), \
        "refusal left an approval"


def t_tampered_payload_file_refused():
    root = make_root()
    try:
        p = os.path.join(root, "builds", RUN, "app", "generated", "app.py")
        with open(p, "a") as f:
            f.write("\n# tampered\n")
        _refused(root, "does not match")
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: tampered payload file", t_tampered_payload_file_refused)


def t_tampered_vendor_source_refused():
    root = make_root()
    try:
        p = os.path.join(root, "examples", "notes-app-fusion", "fused_app",
                         "vendor", "microdot", "src", "microdot",
                         "test_client.py")
        with open(p, "a") as f:
            f.write("\n# tampered\n")
        _refused(root, "reconstructed tree does not match")
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: tampered in-repo vendor source",
      t_tampered_vendor_source_refused)


def t_extra_file_refused():
    root = make_root()
    try:
        extra = os.path.join(root, "examples", "notes-app-fusion",
                             "fused_app", "vendor", "stray.txt")
        open(extra, "w").write("stray")
        _refused(root, "reconstructed tree does not match")
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: unexpected extra file in tree", t_extra_file_refused)


def t_unsafe_manifest_paths_refused():
    for bad in ("../evil.py", "/abs.py", "vendor/../../x.py",
                "vendor//x.py", "vendor/back\\slash.py"):
        root = make_root()
        try:
            mp = os.path.join(root, "builds", RUN, "manifest.json")
            m = json.load(open(mp))
            m["files"][bad] = "0" * 64
            json.dump(m, open(mp, "w"))
            _refused(root, "unsafe manifest path")
        finally:
            shutil.rmtree(root, ignore_errors=True)
check("refuse: unsafe manifest path entries (5 shapes)",
      t_unsafe_manifest_paths_refused)


def t_manifest_missing_pin_refused():
    root = make_root()
    try:
        mp = os.path.join(root, "builds", RUN, "manifest.json")
        m = json.load(open(mp))
        del m["files"]["generated/app.py"]
        json.dump(m, open(mp, "w"))
        _refused(root, "does not pin")
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: manifest missing a payload pin",
      t_manifest_missing_pin_refused)


def t_bad_build_record_refused():
    root = make_root()
    try:
        sp = os.path.join(root, "builds", RUN, "build-state.json")
        st = json.load(open(sp))
        st["status"] = "running"
        json.dump(st, open(sp, "w"))
        _refused(root, "build record invalid")
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: build record not a reviewed ready build",
      t_bad_build_record_refused)


def t_never_overwrites():
    root = make_root()
    try:
        build_root = import_build.import_build(RUN, repo_root=root)
        marker = os.path.join(build_root, "app", "generated", "app.py")
        before = import_build._sha256(marker)
        try:
            import_build.import_build(RUN, repo_root=root)
            raise AssertionError("second import accepted")
        except import_build.Refused as e:
            assert "already imported" in str(e)
        # the pre-existing import is untouched
        assert import_build._sha256(marker) == before
        st = json.load(open(os.path.join(build_root, "build-state.json")))
        assert st["status"] == "build_ready"
    finally:
        shutil.rmtree(root, ignore_errors=True)
check("refuse: existing import is never overwritten", t_never_overwrites)


def t_bad_run_id_refused():
    for bad in ("", "run-XYZ", "run-1f58ac57911bb892/../x", None):
        try:
            import_build.import_build(bad, repo_root="/nonexistent")
            raise AssertionError(f"accepted {bad!r}")
        except import_build.Refused:
            pass
check("refuse: malformed run ids", t_bad_run_id_refused)


if __name__ == "__main__":
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
