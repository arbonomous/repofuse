"""RepoFuse vendor path shim: makes vendored input repos importable.

Covers flat layout (<slug>/mod.py), package layout (<slug>/pkg/__init__.py)
and src/lib layouts (<slug>/src/pkg/...).
"""
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
