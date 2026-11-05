"""RepoFuse vendor path shim: makes vendored input repos importable.

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
