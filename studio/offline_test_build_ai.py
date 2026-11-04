"""Offline tests for build_ai.py - NO network, NO key, NO model.

The transport (repofuse.model_api) is stubbed; the budget machinery
(repofuse.budget) is the REAL durable implementation. Run:
python3 studio/offline_test_build_ai.py
"""
import json
import os
import sys
import tempfile
import types

STUDIO = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(STUDIO)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, STUDIO)

import repofuse.budget as real_budget          # the REAL durable ledger
import build_ai


class StubModelAPI:
    class ModelCallError(RuntimeError):
        pass

    def __init__(self):
        self.key_present = True
        self.count_result = 100
        self.chat_queue = []
        self.chat_raises = None
        self.count_calls = 0
        self.chat_calls = 0

    def have_model_key(self):
        return self.key_present

    def count_tokens(self, messages, **kw):
        self.count_calls += 1
        return self.count_result

    def chat_completion(self, messages, **kw):
        self.chat_calls += 1
        if self.chat_raises:
            raise StubModelAPI.ModelCallError(self.chat_raises)
        return self.chat_queue.pop(0)


def raw(content):
    return {"content": content, "model": "muse-spark-1.3",
            "usage": {"prompt_tokens": 900, "completion_tokens": 700},
            "latency_ms": 42, "finish_reason": "stop"}


GOOD_ARCH = json.dumps({"plan": {
    "app_name": "notes", "crud_prefix": "/notes", "entity": "note",
    "fields": [{"name": "text", "type": "str"}],
    "routes": ["GET /notes", "POST /notes", "GET /notes/<id>",
               "PUT /notes/<id>", "DELETE /notes/<id>"],
    "uses": {"microdot": ["Microdot", "Request"],
             "peewee": ["Model", "CharField", "NotARealExport"]},
    "notes": "small notes api"}})

GOOD_GLUE = json.dumps({"file": {"path": "generated/app.py", "content": (
    "from microdot import Microdot\n"
    "from peewee import Model, SqliteDatabase, CharField\n\n"
    "db = SqliteDatabase(None)\n"
    "MODELS = []\n\n"
    "class Note(Model):\n"
    "    text = CharField()\n"
    "    class Meta:\n"
    "        database = db\n\n"
    "MODELS = [Note]\n"
    "app = Microdot()\n\n"
    "@app.get('/notes')\n"
    "def list_notes(request):\n"
    "    return []\n")}})

GOOD_TESTS = json.dumps({"file": {"path": "test_fused.py", "content": (
    "from generated.app import app\n"
    "from microdot import TestClient\n\n"
    "def test_list():\n"
    "    c = TestClient(app)\n"
    "    assert c.get('/notes').status_code == 200\n")}})

CARD = {"title": "Personal notes API with login",
        "what": "Notes with auth.", "fit": ["Microdot", "Model"]}
METAS = {
    "microdot": {"commit_sha": "7742db9ff9f49635de3387145fafe56bf2377a97",
                 "license_guess": "MIT",
                 "analysis": {"exports": ["Microdot", "Request", "Response",
                                          "TestClient"],
                              "python_files": ["microdot.py"]}},
    "peewee": {"commit_sha": "e9b55c96b0c1e5c13c0053205868f188af617945",
               "license_guess": "MIT",
               "analysis": {"exports": ["Model", "SqliteDatabase",
                                        "CharField"],
                            "python_files": ["peewee.py"]}},
}

PASS, FAIL = 0, []


def check(name, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  ok  {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"FAIL  {name}: {e}")


def setup(stub, envelope="valid"):
    tmp = tempfile.mkdtemp(prefix="build-ai-test-")
    if envelope == "valid":
        env = dict(build_ai.ALLOWED)
    elif envelope == "absent":
        env = None
    elif envelope == "malformed":
        env = "not json{"
    elif envelope == "partial":
        env = {"max_calls": 3}
    elif envelope == "wide":
        e = dict(build_ai.ALLOWED); e["max_calls"] = 4; env = e
    elif envelope == "zero":
        e = dict(build_ai.ALLOWED); e["max_calls"] = 0; env = e
    if env is None:
        try:
            os.remove(os.path.join(STUDIO, "envelope.build.json"))
        except FileNotFoundError:
            pass
    else:
        with open(os.path.join(STUDIO, "envelope.build.json"), "w") as f:
            f.write(env if isinstance(env, str) else json.dumps(env))
    fake_pkg = types.ModuleType("repofuse")
    fake_pkg.budget = real_budget
    fake_pkg.model_api = stub
    old = sys.modules.get("repofuse")
    sys.modules["repofuse"] = fake_pkg
    return tmp, old


def teardown(old):
    if old is not None:
        sys.modules["repofuse"] = old
    try:
        os.remove(os.path.join(STUDIO, "envelope.build.json"))
    except FileNotFoundError:
        pass


def good_queue(stub):
    stub.chat_queue = [raw(GOOD_ARCH), raw(GOOD_GLUE), raw(GOOD_TESTS)]


def t_not_configured():
    stub = StubModelAPI(); tmp, old = setup(stub, "absent")
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.NotConfigured:
            pass
        assert stub.chat_calls == 0 and stub.count_calls == 0
    finally:
        teardown(old)


def t_no_key():
    stub = StubModelAPI(); stub.key_present = False
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert not e.spent and stub.chat_calls == 0
    finally:
        teardown(old)


def t_happy_path():
    stub = StubModelAPI(); good_queue(stub)
    tmp, old = setup(stub)
    try:
        plan, code, tests, provs = build_ai.run_build_steps(
            METAS, CARD, "run-t", state_dir=tmp)
        assert plan["crud_prefix"] == "/notes"
        assert "app = Microdot()" in code
        assert "generated.app" in tests
        assert [p["step"] for p in provs] == list(build_ai.STEPS)
        assert stub.count_calls == 3 and stub.chat_calls == 3
        # fake citation dropped, real ones kept
        assert provs[0]["dropped_citations"] == 1
        assert plan["uses"]["peewee"] == ["Model", "CharField"]
        files = sorted(os.listdir(tmp))
        for step in build_ai.STEPS:
            assert f"raw-{step}-run-t.json" in files
            assert f"provenance-{step}-run-t.json" in files
        assert not any(f.startswith("rejected-") for f in files)
        ledger = json.load(open(os.path.join(tmp, "build-ledger.json")))
        assert len(ledger["calls"]) == 3 and len(ledger["count_calls"]) == 3
    finally:
        teardown(old)


def t_step_refusal_stops_sequence():
    """Glue returns non-JSON: refused spent, tests step NEVER fires."""
    stub = StubModelAPI()
    stub.chat_queue = [raw(GOOD_ARCH), raw("not json{")]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert e.spent and e.step == "build-glue"
        assert stub.chat_calls == 2 and stub.count_calls == 2
        rec = json.load(open(os.path.join(
            tmp, "rejected-build-glue-run-t.json")))
        assert rec["spent"] is True and rec["step"] == "build-glue"
        assert os.path.exists(os.path.join(
            tmp, "raw-build-glue-run-t.json"))
        ledger = json.load(open(os.path.join(tmp, "build-ledger.json")))
        assert len(ledger["calls"]) == 2  # interrupted reservation consumed
    finally:
        teardown(old)


def t_arch_wrapper_shape_refused():
    """The REAL ideas-qualification failure shape must refuse here too."""
    stub = StubModelAPI()
    stub.chat_queue = [raw(json.dumps({"response": [GOOD_ARCH]}))]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert e.spent and "envelope" in str(e)
        rec = json.load(open(os.path.join(
            tmp, "rejected-build-architecture-run-t.json")))
        assert rec["spent"] is True and "envelope" in rec["reason"]
        assert rec["usage"] is not None and rec["model"] == "muse-spark-1.3"
    finally:
        teardown(old)


def t_denied_import_refused():
    stub = StubModelAPI()
    bad = json.dumps({"file": {"path": "generated/app.py", "content":
        "import os\nfrom microdot import Microdot\n"
        "app = Microdot()\n"}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(bad)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert e.spent and "denied module: os" in str(e)
    finally:
        teardown(old)


def t_app_run_and_open_refused():
    stub = StubModelAPI()
    bad = json.dumps({"file": {"path": "generated/app.py", "content": (
        "from microdot import Microdot\n"
        "app = Microdot()\n"
        "app.run(host='0.0.0.0')\n")}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(bad)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert ".run()" in str(e)
    finally:
        teardown(old)


def t_missing_app_assignment_refused():
    stub = StubModelAPI()
    bad = json.dumps({"file": {"path": "generated/app.py", "content": (
        "from microdot import Microdot\n"
        "def nothing():\n"
        "    return 1\n")}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(bad)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert "app = Microdot" in str(e)
    finally:
        teardown(old)


def t_path_slot_guard():
    """'./generated/app.py' normalizes; 'app.py' refuses."""
    stub = StubModelAPI()
    dot = json.dumps({"file": {"path": "./generated/app.py",
                               "content": json.loads(GOOD_GLUE)["file"]
                               ["content"]}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(dot), raw(GOOD_TESTS)]
    tmp, old = setup(stub)
    try:
        plan, code, tests, _ = build_ai.run_build_steps(
            METAS, CARD, "run-t", state_dir=tmp)
        assert code
    finally:
        teardown(old)
    stub = StubModelAPI()
    wrong = json.dumps({"file": {"path": "app.py", "content": "x=1\n"}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(wrong)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t2", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert "path" in str(e)
    finally:
        teardown(old)


def t_ledger_reuse_refused():
    """Steps are one-shot: a second run finds the grant consumed."""
    stub = StubModelAPI(); good_queue(stub)
    tmp, old = setup(stub)
    try:
        build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
        good_queue(stub)
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t2", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert not e.spent
        assert stub.chat_calls == 3  # nothing new fired
    finally:
        teardown(old)


def t_indeterminate_record():
    stub = StubModelAPI(); good_queue(stub)
    def boom(messages, **kw):
        raise ValueError("transport exploded mid-call")
    stub.chat_completion = boom
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ValueError:
            pass
        rec = json.load(open(os.path.join(
            tmp, "rejected-build-architecture-run-t.json")))
        assert rec["spent"] is None
        assert "transport exploded" in rec["reason"]
    finally:
        teardown(old)


def t_count_over_cap():
    stub = StubModelAPI(); good_queue(stub)
    stub.count_result = 99999
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert not e.spent and "cap" in str(e)
        assert stub.chat_calls == 0
    finally:
        teardown(old)


def t_bad_envelopes_refuse():
    for kind in ("malformed", "partial", "wide", "zero"):
        stub = StubModelAPI(); good_queue(stub)
        tmp, old = setup(stub, kind)
        try:
            try:
                build_ai.run_build_steps(METAS, CARD, "run-t",
                                         state_dir=tmp)
                raise AssertionError(f"{kind} should have raised")
            except build_ai.Refused as e:
                assert not e.spent
            assert stub.chat_calls == 0
        finally:
            teardown(old)


def t_card_contract():
    stub = StubModelAPI(); good_queue(stub)
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, {"title": ""}, "run-t",
                                     state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert "card contract" in str(e)
        assert stub.chat_calls == 0 and stub.count_calls == 0
    finally:
        teardown(old)


def t_db_path_pinned_to_none():
    """Generated code may never name a database path (file isolation)."""
    stub = StubModelAPI()
    bad = json.dumps({"file": {"path": "generated/app.py", "content": (
        "from microdot import Microdot\n"
        "from peewee import Model, SqliteDatabase\n"
        "db = SqliteDatabase('/etc/passwd')\n"
        "MODELS = []\n"
        "app = Microdot()\n")}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(bad)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert "SqliteDatabase(None)" in str(e)
    finally:
        teardown(old)


def t_tests_file_gate():
    """The tests file also passes the static gate (no app required)."""
    stub = StubModelAPI()
    bad = json.dumps({"file": {"path": "test_fused.py", "content":
        "import subprocess\n"}})
    stub.chat_queue = [raw(GOOD_ARCH), raw(GOOD_GLUE), raw(bad)]
    tmp, old = setup(stub)
    try:
        try:
            build_ai.run_build_steps(METAS, CARD, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except build_ai.Refused as e:
            assert "denied module" in str(e)
    finally:
        teardown(old)


if __name__ == "__main__":
    for name, fn in sorted(
            {k: v for k, v in globals().items()
             if k.startswith("t_")}.items()):
        check(name, fn)
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
