"""Vendor input-repo code into the fused app, with provenance hashes.

The fused app incorporates ACTUAL input-repo code (not just model-generated
glue): a copy under fused_app/vendor/<slug>/ with the repo's LICENSE retained
and a per-file sha256 manifest plus the cloned commit SHA. The model only
ever sees summaries (exports/routes/README excerpt), never full source;
the glue imports the vendored code at runtime via an explicit path shim.

License obligation: vendored files keep their own licenses. report.json
records each vendored repo's detected license; MIT/BSD/Apache require
retention of the license text, which vendoring preserves verbatim.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
_MAX_VENDOR_FILES = 5000  # aggregate across ALL repos and directories


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def vendor_repos(metas, fusion_dir):
    """Copy each ingested repo into fused_app/vendor/<slug>/. Returns manifest."""
    vendor_root = os.path.join(fusion_dir, "vendor")
    os.makedirs(vendor_root, exist_ok=True)
    entries = []
    hashes = {}
    count = 0
    truncated = False
    seen_slugs = {}
    for m in metas:
        src, slug = m["path"], m["slug"]
        if slug in seen_slugs and seen_slugs[slug] != m["url"]:
            raise ValueError(f"slug collision: {slug} from both "
                             f"{seen_slugs[slug]} and {m['url']}; refusing")
        seen_slugs[slug] = m["url"]
        dest = os.path.join(vendor_root, slug)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        for root, dirs, files in os.walk(src, followlinks=False):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS
                       and not os.path.islink(os.path.join(root, d))]
            for fn in files:
                if count >= _MAX_VENDOR_FILES:
                    truncated = True
                    break
                full = os.path.join(root, fn)
                if os.path.islink(full):
                    continue
                rel = os.path.relpath(full, src)
                out = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                shutil.copyfile(full, out)
                src_hash = _sha256(full)
                dst_hash = _sha256(out)  # readback: copy must match source
                if dst_hash != src_hash:
                    raise IOError(f"vendor readback mismatch: {slug}/{rel}")
                hashes[f"{slug}/{rel}"] = src_hash
                count += 1
            if truncated:
                break
        if truncated:
            break
        entries.append({
            "slug": slug, "url": m["url"], "commit_sha": m["commit_sha"],
            "license_guess": m["license_guess"],
            "license_file": m.get("license_file"),
            "file_count": count,
        })
    manifest = {"schema": "repofuse/vendor-manifest@0.1", "repos": entries,
                "truncated": truncated,
                "hashes_readback_verified": True,
                "hashes": hashes}
    with open(os.path.join(vendor_root, "hashes.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


IMPORT_SHIM = '''"""RepoFuse vendor path shim: makes vendored input repos importable.

Covers flat layout (<slug>/mod.py), package layout (<slug>/pkg/__init__.py)
and src/lib layouts (<slug>/src/pkg/...). It also binds
`from vendor import <slug>` to the REAL vendored package (sys.modules
aliasing), so the repo-checkout directory itself is never imported as a
namespace package. When a slug has no importable top-level package of the
same name, the path shim alone applies, exactly as before - aliasing never
masks a different-name package and never swallows the real one's identity.
"""
import importlib as _il
import os
import sys

VENDOR = os.path.dirname(os.path.abspath(__file__))
for _name in sorted(os.listdir(VENDOR)):
    _base = os.path.join(VENDOR, _name)
    if not os.path.isdir(_base):
        continue
    for _cand in (_base, os.path.join(_base, "src"),
                  os.path.join(_base, "lib")):
        if os.path.isdir(_cand) and _cand not in sys.path:
            sys.path.insert(0, _cand)
for _name in sorted(os.listdir(VENDOR)):
    _base = os.path.join(VENDOR, _name)
    _key = __name__ + "." + _name
    if not os.path.isdir(_base) or _key in sys.modules:
        continue
    try:
        sys.modules[_key] = _il.import_module(_name)
    except Exception:
        sys.modules.pop(_key, None)
        continue
'''


def write_import_shim(fusion_dir):
    path = os.path.join(fusion_dir, "vendor", "__init__.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(IMPORT_SHIM)
    return path
