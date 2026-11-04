"""Serving contract for a GENERAL fused app.

A general app has no fixed shape, so it may be served only under an
explicit, REVIEWED contract: serving.json at the fused_app root. The
file lives INSIDE the attested tree, so the whole-tree attestation
that gates execution also pins the contract's exact bytes - a contract
edited after review fails the same attestation and refuses to serve.

Validation is fail-closed and deliberately narrow: one kind
(python-module, a Flask-shaped object with .run(host=, port=)), dotted
identifiers only, no shell strings, no absolute paths, bounded lists.
Anything else is an honest 'unsupported contract' refusal, never a
guess."""
import json
import os
import re

_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,5}$")
_OBJECT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$")
_PATH = re.compile(r"^/[A-Za-z0-9_/.-]{0,120}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
# Reviewer-mandated allowlist: even a well-formed env NAME is not enough.
# Only these variables may be declared as spawn secrets, so a contract can
# never shadow execution-control variables (PATH, PYTHONPATH, LD_PRELOAD,
# HOME, MODEL_API_KEY, ...) with runner-generated values.
ALLOWED_SPAWN_SECRETS = frozenset({"REPOFUSE_APP_SECRET"})

CONTRACT_NAME = "serving.json"


def load_contract(fusion_dir):
    """Return (ok, contract_or_reason). Never raises."""
    path = os.path.join(fusion_dir, CONTRACT_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError) as e:
        return False, f"no readable serving contract ({CONTRACT_NAME}): {e}"
    if not isinstance(c, dict):
        return False, "serving contract is not an object"
    if c.get("version") != 1:
        return False, "serving contract version must be exactly 1"
    if c.get("kind") != "python-wsgi":
        return False, (f"serving contract kind {c.get('kind')!r} is not "
                       "servable: only 'python-wsgi' (a WSGI callable) can "
                       "be contained to the required standard - the parent "
                       "owns the listening socket, the contained child only "
                       "accepts on the inherited descriptor")
    module = c.get("module")
    obj = c.get("app_object")
    if not (isinstance(module, str) and _MODULE.match(module)):
        return False, "serving contract module must be a dotted python name"
    if not (isinstance(obj, str) and _OBJECT.match(obj)):
        return False, "serving contract app_object must be a plain identifier"
    # the module file must exist inside the tree (no absolute paths, no ..)
    rel = module.replace(".", os.sep) + ".py"
    full = os.path.normpath(os.path.join(fusion_dir, rel))
    if not full.startswith(os.path.abspath(fusion_dir) + os.sep):
        return False, "serving contract module escapes the fused tree"
    if not os.path.isfile(full):
        return False, f"serving contract module file missing: {rel}"
    readiness = c.get("readiness_path", "/")
    if not (isinstance(readiness, str) and _PATH.match(readiness)):
        return False, "serving contract readiness_path is not a plain path"
    status = c.get("readiness_status", 200)
    if not (isinstance(status, int) and 100 <= status <= 599):
        return False, "serving contract readiness_status must be an HTTP code"
    if c.get("env"):
        return False, ("serving contract v1 passes NO custom environment; "
                       "the child always gets the scrubbed allowlist")
    # spawn_secrets is the ONLY secret mechanism: it names env vars whose
    # values the runner generates fresh per spawn (os.urandom(32).hex()).
    # No literal secret material can EVER appear in a contract: the only
    # accepted value is the generator name "random-hex-32", so the contract
    # stays safe to attest, pin, and commit inside the tree.
    spawn_secrets = c.get("spawn_secrets") or {}
    if not isinstance(spawn_secrets, dict):
        return False, "serving contract spawn_secrets must be an object"
    for k, v in spawn_secrets.items():
        if not (isinstance(k, str) and _ENV_NAME.match(k)):
            return False, (f"serving contract spawn_secrets key {k!r} is not "
                           "a plain uppercase env name")
        if k not in ALLOWED_SPAWN_SECRETS:
            return False, (f"serving contract spawn_secrets key {k!r} is not "
                           "on the allowlist (only "
                           + ", ".join(sorted(ALLOWED_SPAWN_SECRETS))
                           + "); refusing to let a contract shadow "
                           "execution-control environment")
        if v != "random-hex-32":
            return False, ("serving contract spawn_secrets values may ONLY "
                           "name the generator 'random-hex-32' (a fresh "
                           "per-spawn secret); literal secret material is "
                           "never allowed in a contract")
    return True, {"module": module, "app_object": obj,
                  "readiness_path": readiness,
                  "readiness_status": status,
                  "spawn_secrets": dict(spawn_secrets)}


def runner_snippet(contract, listen_fd):
    """Build the child-process runner from VALIDATED parts only. The
    identifiers matched strict python-name patterns and the fd is an int
    the PARENT owns, so this is construction, not interpolation of free
    text. The pdeathsig arm is OUR infrastructure line: the app is
    SIGKILLed when its container parent dies, closing the orphan window
    even if the studio server itself is killed -9 (server death ->
    bwrap death -> app death). The child NEVER opens a socket: it
    accepts on the parent's inherited listening descriptor only, which
    is what makes a fully network-unshared namespace servable."""
    mod = contract["module"]
    obj = contract["app_object"]
    # Fresh per-spawn secrets: generated HERE from os.urandom at process
    # start, present only in the contained child's environment. The contract
    # names only the variables; no secret value exists at rest anywhere.
    sec = contract.get("spawn_secrets") or {}
    secret_lines = "".join(
        f"_os.environ[{k!r}] = _os.urandom(32).hex()\n" for k in sorted(sec))
    return ("import ctypes as _c\n"
            "_c.CDLL(None).prctl(1, 9, 0, 0, 0)  # PR_SET_PDEATHSIG=SIGKILL\n"
            "import os as _os\n"
            + secret_lines +
            "import socket as _s\n"
            "from wsgiref.simple_server import (\n"
            "    WSGIServer as _W, WSGIRequestHandler as _H)\n"
            "import vendor  # RepoFuse shim: vendored pinned repos on sys.path\n"
            f"import {mod} as _m\n"
            f"_app = getattr(_m, {obj!r})\n"
            f"_sock = _s.fromfd({listen_fd}, _s.AF_INET, _s.SOCK_STREAM)\n"
            "_srv = _W(('127.0.0.1', 0), _H, bind_and_activate=False)\n"
            "_srv.socket = _sock\n"
            "_srv.server_address = _sock.getsockname()\n"
            "_srv.server_name = '127.0.0.1'\n"
            "_srv.server_port = _sock.getsockname()[1]\n"
            "_srv.setup_environ()\n"
            "_srv.set_app(_app)\n"
            "_srv.serve_forever()\n")


import ast
import shutil

_SYSTEM_BINDS = tuple(d for d in ("/usr", "/lib", "/lib64", "/bin", "/sbin")
                      if os.path.isdir(d))


def containment_available():
    """Serving containment is bubblewrap, same primitive the sandboxed
    verify uses. No bwrap, no serving - reviewed code never runs on the
    bare host."""
    return shutil.which("bwrap") is not None


def build_serve_cmd(fusion_dir, contract, listen_fd, python):
    """bwrap command for SERVING under the containment standard: ALL
    namespaces unshared INCLUDING NETWORK (the child answers on the
    parent's inherited listening descriptor, so it needs no network at
    all - egress is architecturally impossible), the fused tree mounted
    READ-ONLY at /app, one explicit scratch (/tmp tmpfs) only, cleared
    environment with only the values below, die-with-parent, new
    session. An app that needs outbound network or a writable tree is
    unservable under v1 and fails honestly at startup or probe time."""
    cmd = (["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            "--clearenv"]
           + [flag for d in _SYSTEM_BINDS
              for flag in ("--ro-bind", d, d)]
           + ["--ro-bind", os.path.abspath(fusion_dir), "/app",
              "--tmpfs", "/tmp",
              "--chdir", "/app",
              "--setenv", "HOME", "/tmp",
              "--setenv", "PATH", "/usr/bin:/bin",
              "--setenv", "PYTHONPATH", "/app",
              "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
              "--setenv", "PYTHONNOUSERSITE", "1",
              "--", python, "-S", "-s", "-c",
              runner_snippet(contract, listen_fd)])
    return cmd


def derive_contract(fusion_dir):
    """FREE, deterministic candidate-contract emission after glue
    synthesis: if exactly one generated module assigns a top-level
    `app`, write serving.json pointing at it (AST inspection only -
    nothing is imported or executed). Otherwise write nothing and
    return the honest reason; serving then refuses until a reviewer
    authors a contract, which the attestation pins like any byte."""
    gen = os.path.join(fusion_dir, "generated")
    if not os.path.isdir(gen):
        return None, "no generated/ directory - nothing to serve"
    found = []
    for fn in sorted(os.listdir(gen)):
        if not fn.endswith(".py") or fn == "__init__.py":
            continue
        path = os.path.join(gen, fn)
        if os.path.islink(path):
            return None, f"generated/{fn} is a symlink; refusing to inspect"
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError) as e:
            return None, f"generated/{fn} does not parse: {e}"
        for node in tree.body:
            if ((isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "app"
                         for t in node.targets))
                    or (isinstance(node, (ast.FunctionDef,
                                          ast.AsyncFunctionDef))
                        and node.name == "app")):
                found.append(fn[:-3])
                break
    if len(found) != 1:
        return None, (f"{len(found)} generated modules expose a top-level "
                      "'app'; a serving contract needs exactly one, so "
                      "none was derived")
    # WSGI-shaped is a HYPOTHESIS the reviewer attests with the tree; if
    # the object is not a WSGI callable, serving fails honestly at the
    # readiness probe, never silently.
    # REPOFUSE_APP_SECRET is the one standardized per-spawn secret: apps
    # that sign anything read it from the environment (the generation
    # contract instructs this); apps that do not need it ignore it.
    contract = {"version": 1, "kind": "python-wsgi",
                "module": f"generated.{found[0]}", "app_object": "app",
                "readiness_path": "/", "readiness_status": 200,
                "spawn_secrets": {"REPOFUSE_APP_SECRET": "random-hex-32"}}
    with open(os.path.join(fusion_dir, CONTRACT_NAME), "w",
              encoding="utf-8") as f:
        json.dump(contract, f, indent=2)
    return contract, None

