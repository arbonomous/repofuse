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
    share = max(1, _MAX_VENDOR_FILES // max(1, len(metas)))
    for m in metas:
        src, slug = m["path"], m["slug"]
        if slug in seen_slugs and seen_slugs[slug] != m["url"]:
            raise ValueError(f"slug collision: {slug} from both "
                             f"{seen_slugs[slug]} and {m['url']}; refusing")
        seen_slugs[slug] = m["url"]
        dest = os.path.join(vendor_root, slug)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        repo_count = 0
        repo_truncated = False
        for root, dirs, files in os.walk(src, followlinks=False):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS
                       and not os.path.islink(os.path.join(root, d))]
            for fn in files:
                if repo_count >= share or count >= _MAX_VENDOR_FILES:
                    truncated = True
                    repo_truncated = True
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
                repo_count += 1
            if repo_truncated:
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
import importlib.abc as _abc
import importlib.machinery as _mach
import os
import re as _re
import sys

VENDOR = os.path.dirname(os.path.abspath(__file__))
_SKIP = {"surfaces", "__pycache__"}


def _pyident(slug):
    ident = _re.sub(r"[^A-Za-z0-9]+", "_", slug or "").strip("_")
    if not ident or ident[0].isdigit():
        ident = "repo_" + ident
    return ident


class _LenientInit(_abc.Loader):
    """Run a package __init__. A missing third-party import leaves the
    package in place so a pure submodule can still load."""

    def __init__(self, origin, pkg_dir):
        self.origin = origin
        self.pkg_dir = pkg_dir

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__path__ = [self.pkg_dir]
        module.__package__ = module.__name__
        module.__file__ = self.origin
        try:
            with open(self.origin, encoding="utf-8") as handle:
                code = compile(handle.read(), self.origin, "exec")
            exec(code, module.__dict__)
        except ModuleNotFoundError:
            pass


class _VendoredFinder(_abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not path:
            return None
        child = fullname.rpartition(".")[2]
        for entry in path:
            if os.path.commonpath((os.path.abspath(entry), VENDOR)) != VENDOR:
                continue
            pkg = os.path.join(entry, child)
            init = os.path.join(pkg, "__init__.py")
            mod = os.path.join(entry, child + ".py")
            if os.path.isfile(init) and not os.path.islink(init):
                spec = _mach.ModuleSpec(
                    fullname, _LenientInit(init, pkg), origin=init, is_package=True)
                spec.has_location = True
                return spec
        return None


if not any(isinstance(f, _VendoredFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _VendoredFinder())
for _name in sorted(os.listdir(VENDOR)):
    _base = os.path.join(VENDOR, _name)
    if _name in _SKIP or not os.path.isdir(_base):
        continue
    for _cand in (_base, os.path.join(_base, "src"),
                  os.path.join(_base, "lib")):
        if os.path.isdir(_cand) and _cand not in sys.path:
            sys.path.insert(0, _cand)
for _name in sorted(os.listdir(VENDOR)):
    _base = os.path.join(VENDOR, _name)
    _key = __name__ + "." + _name
    if _name in _SKIP or not os.path.isdir(_base) or _key in sys.modules:
        continue
    try:
        sys.modules[_key] = _il.import_module(_name)
    except Exception:
        sys.modules.pop(_key, None)
        continue
_pkg = sys.modules[__name__]
for _name in sorted(os.listdir(VENDOR)):
    _base = os.path.join(VENDOR, _name)
    if _name in _SKIP or not os.path.isdir(_base) or _name.isidentifier():
        continue
    _ident = _pyident(_name)
    _alias = __name__ + "." + _ident
    if (not _ident.isidentifier() or hasattr(_pkg, _ident)
            or _alias in sys.modules):
        continue
    try:
        _mod = _il.import_module(__name__ + ".surfaces." + _ident)
    except Exception:
        continue
    sys.modules[_alias] = _mod
    setattr(_pkg, _ident, _mod)
'''


def write_import_shim(fusion_dir):
    path = os.path.join(fusion_dir, "vendor", "__init__.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(IMPORT_SHIM)
    return path


_SURFACE = '''"""Read-only surface for one vendored repository. Does not execute it."""
import os

SLUG = {slug!r}
EXPORTS = {exports!r}


def exports():
    return list(EXPORTS)


def _find_export(root, name):
    if not name or "/" in name or not name.replace("_", "a").isalnum():
        return None
    seen = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__")]
        for fn in files:
            if not fn.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                continue
            seen += 1
            if seen > 400:
                return None
            path = os.path.join(base, fn)
            if os.path.islink(path):
                continue
            try:
                if os.path.getsize(path) > 200000:
                    continue
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read(200000)
            except OSError:
                continue
            if name in text:
                return os.path.abspath(path)
    return None


def read_text(rel, limit=4000):
    if not isinstance(rel, str) or rel.startswith(("/", "\\\\")) or "\\\\" in rel:
        raise ValueError("path must stay inside the vendored repository")
    if ".." in rel.split("/"):
        raise ValueError("path must stay inside the vendored repository")
    if not isinstance(limit, int):
        limit = 4000
    limit = max(1, min(limit, 8000))
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", SLUG))
    direct = os.path.abspath(os.path.join(root, rel))
    full = direct if os.path.commonpath((root, direct)) == root else None
    if full is None or os.path.islink(full) or not os.path.isfile(full):
        full = _find_export(root, rel)
    if not full or os.path.islink(full) or not os.path.isfile(full):
        raise ValueError("regular file inside the vendored repository required")
    if os.path.commonpath((root, full)) != root:
        raise ValueError("regular file inside the vendored repository required")
    with open(full, encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)
'''


def write_surfaces(fusion_dir, metas, analyses=None):
    """Add an importable Python module for every vendored repository.

    A JavaScript repository has no package the glue can import. This module
    lists the static export names and reads vendored files. It does not run
    the repository.
    """
    from .api_evidence import python_ident
    folder = os.path.join(fusion_dir, "vendor", "surfaces")
    os.makedirs(folder, exist_ok=True)
    init = os.path.join(folder, "__init__.py")
    if not os.path.exists(init):
        with open(init, "w", encoding="utf-8") as handle:
            handle.write('"""Importable surfaces for vendored repositories."""\n')
    by_slug = {}
    for analysis in analyses or []:
        if isinstance(analysis, dict) and analysis.get("slug"):
            by_slug[analysis["slug"]] = analysis
    written = []
    for meta in metas or []:
        slug = meta.get("slug") or ""
        ident = python_ident(slug)
        names = []
        for name in (by_slug.get(slug) or {}).get("exports") or []:
            if isinstance(name, str) and name.isidentifier() and len(name) <= 80:
                names.append(name)
            if len(names) >= 80:
                break
        path = os.path.join(folder, ident + ".py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_SURFACE.format(slug=slug, exports=tuple(names)))
        written.append(ident)
    return written
