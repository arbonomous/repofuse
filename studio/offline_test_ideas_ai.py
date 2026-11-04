"""Offline tests for ideas_ai.py - NO network, NO key, NO model.

The transport (repofuse.model_api) is stubbed; the budget machinery
(repofuse.budget) is the REAL durable implementation. Every fail-closed
path is exercised. Run: python3 studio/offline_test_ideas_ai.py
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
import ideas_ai


class StubModelAPI:
    class ModelCallError(RuntimeError):
        pass

    def __init__(self):
        self.key_present = True
        self.count_result = 100
        self.chat_result = None
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
        return self.chat_result


GOOD_CONTENT = json.dumps({"ideas": [
    {"title": "Tiny notes API", "what": "REST notes on a real database.",
     "fit": ["Microdot", "Model"]},
    {"title": "Inventory API", "what": "Track items with quantities.",
     "fit": ["HTTPException", "Database"]},
]})
FAKE_EXPORT_CONTENT = json.dumps({"ideas": [
    {"title": "Fake idea", "what": "cites things that do not exist",
     "fit": ["NotARealExport"]},
    {"title": "Real idea", "what": "cites real exports only",
     "fit": ["Microdot"]},
]})
ALL_FAKE_CONTENT = json.dumps({"ideas": [
    {"title": "Fake", "what": "all citations invented",
     "fit": ["Nope"]},
]})
METAS = {
    "microdot": {"commit_sha": "7742db9ff9f49635de3387145fafe56bf2377a97",
                 "license_guess": "MIT",
                 "analysis": {"exports": ["Microdot", "Request", "Response",
                                          "HTTPException"],
                              "python_files": ["microdot.py"]}},
    "peewee": {"commit_sha": "e9b55c96b0c1e5c13c0053205868f188af617945",
               "license_guess": "MIT",
               "analysis": {"exports": ["Model", "Database", "CharField"],
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
    """Fresh workdir + envelope state; stub installed as model_api."""
    tmp = tempfile.mkdtemp(prefix="ideas-ai-test-")
    if envelope == "valid":
        env = dict(ideas_ai.ALLOWED)
    elif envelope == "absent":
        env = None
    elif envelope == "malformed":
        env = "not json{"
    elif envelope == "partial":
        env = {"max_calls": 1}
    elif envelope == "wide":
        e = dict(ideas_ai.ALLOWED); e["max_calls"] = 2; env = e
    elif envelope == "zero":
        e = dict(ideas_ai.ALLOWED); e["max_calls"] = 0; env = e
    if env is None:
        try:
            os.remove(os.path.join(STUDIO, "envelope.ideas.json"))
        except FileNotFoundError:
            pass
    else:
        with open(os.path.join(STUDIO, "envelope.ideas.json"), "w") as f:
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
        os.remove(os.path.join(STUDIO, "envelope.ideas.json"))
    except FileNotFoundError:
        pass


def good_chat(stub, content=GOOD_CONTENT):
    stub.chat_result = {
        "content": content, "model": "muse-spark-1.3",
        "usage": {"prompt_tokens": 97, "completion_tokens": 120},
        "latency_ms": 42, "finish_reason": "stop"}


def t_not_configured():
    stub = StubModelAPI(); tmp, old = setup(stub, "absent")
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.NotConfigured:
            pass
        assert stub.count_calls == 0 and stub.chat_calls == 0
    finally:
        teardown(old)


def t_malformed_envelope():
    stub = StubModelAPI(); tmp, old = setup(stub, "malformed")
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert not e.spent
        assert stub.count_calls == 0 and stub.chat_calls == 0
    finally:
        teardown(old)


def t_partial_envelope():
    stub = StubModelAPI(); tmp, old = setup(stub, "partial")
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert "missing keys" in str(e) and not e.spent
        assert stub.count_calls == 0 and stub.chat_calls == 0
    finally:
        teardown(old)


def t_wide_envelope():
    stub = StubModelAPI(); tmp, old = setup(stub, "wide")
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert "outside allowed" in str(e) and not e.spent
        assert stub.count_calls == 0 and stub.chat_calls == 0
    finally:
        teardown(old)


def t_zero_envelope():
    stub = StubModelAPI(); tmp, old = setup(stub, "zero")
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert not e.spent
    finally:
        teardown(old)


def t_no_key():
    stub = StubModelAPI(); stub.key_present = False
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert not e.spent
        assert stub.count_calls == 0 and stub.chat_calls == 0
        assert not os.path.exists(os.path.join(tmp, "idea-ledger.json"))
    finally:
        teardown(old)


def t_count_unavailable():
    stub = StubModelAPI(); stub.count_result = None
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert not e.spent
        assert stub.count_calls == 1 and stub.chat_calls == 0
        # the count check was durably recorded: a retry refuses BEFORE the
        # count endpoint fires again
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("retry should have raised")
        except ideas_ai.Refused:
            pass
        assert stub.count_calls == 1, "count endpoint fired twice!"
    finally:
        teardown(old)


def t_count_over_cap():
    stub = StubModelAPI(); stub.count_result = 999999
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert "cap" in str(e) and not e.spent
        assert stub.chat_calls == 0
    finally:
        teardown(old)


def t_charged_call_error():
    stub = StubModelAPI(); stub.chat_raises = "boom"
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert e.spent
        # reservation consumed: actual stays None, never reusable
        ledger = json.load(open(os.path.join(tmp, "idea-ledger.json")))
        assert ledger["calls"][0]["actual"] is None
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("retry should have raised")
        except ideas_ai.Refused as e2:
            assert "no retries" in str(e2) or "already" in str(e2)
        assert stub.chat_calls == 1
    finally:
        teardown(old)


def t_non_json_retained():
    stub = StubModelAPI(); good_chat(stub, "this is not json")
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert e.spent and "non-JSON" in str(e)
        raw = json.load(open(os.path.join(tmp, "raw-run-t.json")))
        assert raw["content"] == "this is not json"  # retained BEFORE parse
    finally:
        teardown(old)


def t_rejected_provenance_durable():
    """Every spent rejection leaves a durable record next to the raw:
    reason/model/usage/measured/ts - without touching raw or ledger."""
    stub = StubModelAPI()
    good_chat(stub, json.dumps({"response": [
        {"title": "x", "what": "y", "fit": ["Model"]}]}))
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused:
            pass
        rec = json.load(open(os.path.join(tmp, "rejected-run-t.json")))
        assert rec["status"] == "rejected"
        assert rec["spent"] is True
        assert "envelope" in rec["reason"]
        assert isinstance(rec["measured_input_tokens"], int)
        assert rec["measured_input_tokens"] > 0
        assert rec["usage"] is not None and "input" in rec["usage"]
        assert rec["model"] and rec["ts"]
        # raw and consumed ledger untouched by the record write
        raw = json.load(open(os.path.join(tmp, "raw-run-t.json")))
        assert "response" in json.loads(raw["content"])
        ledger = json.load(open(os.path.join(tmp, "idea-ledger.json")))
        assert ledger  # still parses; reservation stands
    finally:
        teardown(old)


def t_no_rejected_record_on_success():
    stub = StubModelAPI()
    good_chat(stub)
    tmp, old = setup(stub)
    try:
        cards, prov = ideas_ai.suggest_with_model(METAS, "run-t",
                                                  state_dir=tmp)
        assert cards
        assert not os.path.exists(os.path.join(tmp, "rejected-run-t.json"))
        assert os.path.exists(os.path.join(tmp, "provenance-run-t.json"))
    finally:
        teardown(old)


def t_indeterminate_record_on_unknown_error():
    """A non-Refused escape after the reservation must be recorded as
    spent UNKNOWN (null), never as zero."""
    stub = StubModelAPI()
    good_chat(stub)
    def boom(messages, **kw):
        raise ValueError("transport exploded mid-call")
    stub.chat_completion = boom
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ValueError:
            pass
        rec = json.load(open(os.path.join(tmp, "rejected-run-t.json")))
        assert rec["status"] == "rejected"
        assert rec["spent"] is None  # indeterminate, not False, not True
        assert "transport exploded" in rec["reason"]
        assert isinstance(rec["measured_input_tokens"], int)
    finally:
        teardown(old)


def t_bare_array_rejected():
    """Bare arrays were the old contract; under the defined envelope they
    must REFUSE - strictness, not repair."""
    stub = StubModelAPI()
    good_chat(stub, json.dumps([{"title": "x", "what": "y", "fit": ["Model"]}]))
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert e.spent and "envelope" in str(e)
    finally:
        teardown(old)


def t_real_wrapper_shape_still_refused():
    """Regression for the REAL qualification failure: {"response": [...]}
    must refuse exactly as it did live."""
    stub = StubModelAPI()
    good_chat(stub, json.dumps({"response": [
        {"title": "Tiny Form Logger API", "what": "real card",
         "fit": ["Microdot", "Request"]}]}))
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert e.spent and "envelope" in str(e)
        raw = json.load(open(os.path.join(tmp, "raw-run-t.json")))
        assert "response" in json.loads(raw["content"])  # verbatim retained
    finally:
        teardown(old)


def t_documented_schema_sent():
    """The request must use the documented json_schema constrained-decoding
    format with the DEFINED envelope - not json_object, not guesses."""
    captured = {}
    stub = StubModelAPI()
    real_chat = stub.chat_completion
    def spy(messages, **kw):
        captured.update(kw)
        return real_chat(messages, **kw)
    stub.chat_completion = spy
    good_chat(stub)
    tmp, old = setup(stub)
    try:
        ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
        rf = captured.get("response_format") or {}
        assert rf.get("type") == "json_schema", rf
        js = rf.get("json_schema") or {}
        schema = js.get("schema") or {}
        assert schema.get("type") == "object"
        assert schema.get("required") == ["ideas"]
        assert schema["properties"]["ideas"]["type"] == "array"
        assert captured.get("reasoning_effort") == "minimal"
        assert captured.get("max_tokens") == ideas_ai.ALLOWED["max_output_tokens"]
    finally:
        teardown(old)


def t_fake_export_dropped():
    stub = StubModelAPI(); good_chat(stub, FAKE_EXPORT_CONTENT)
    tmp, old = setup(stub)
    try:
        cards, prov = ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
        assert len(cards) == 1 and cards[0]["title"] == "Real idea"
        assert prov["dropped_invalid"] == 1
        assert prov["source"] == "model:muse-spark-1.3"
    finally:
        teardown(old)


def t_all_fake_refused():
    stub = StubModelAPI(); good_chat(stub, ALL_FAKE_CONTENT)
    tmp, old = setup(stub)
    try:
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("should have raised")
        except ideas_ai.Refused as e:
            assert e.spent and "verification" in str(e)
    finally:
        teardown(old)


def t_schema_violations_dropped():
    bad = json.dumps({"ideas": [
        {"title": "x" * 200, "what": "title too long", "fit": ["Model"]},
        {"title": "No fit", "what": "empty citations", "fit": []},
        {"title": "Good", "what": "valid", "fit": ["Model", "Database"]},
        "not even an object",
    ]})
    stub = StubModelAPI(); good_chat(stub, bad)
    tmp, old = setup(stub)
    try:
        cards, prov = ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
        assert [c["title"] for c in cards] == ["Good"]
        assert prov["dropped_invalid"] == 3
    finally:
        teardown(old)


def t_happy_path():
    stub = StubModelAPI(); good_chat(stub)
    tmp, old = setup(stub)
    try:
        cards, prov = ideas_ai.suggest_with_model(METAS, "run-t9", state_dir=tmp)
        assert len(cards) == 2
        assert cards[0]["id"] == "tiny-notes-api"
        assert prov["usage"] == {"input": 97, "output": 120}
        assert prov["measured_input_tokens"] == 100
        assert prov["run_id"] == "run-t9"
        assert os.path.exists(os.path.join(tmp, "raw-run-t9.json"))
        assert os.path.exists(os.path.join(tmp, "provenance-run-t9.json"))
        ledger = json.load(open(os.path.join(tmp, "idea-ledger.json")))
        assert ledger["calls"][0]["actual"] == {"input": 97, "output": 120}
        assert len(ledger["count_calls"]) == 1
        assert stub.count_calls == 1 and stub.chat_calls == 1
    finally:
        teardown(old)


def t_ledger_reuse_refused():
    stub = StubModelAPI(); good_chat(stub)
    tmp, old = setup(stub)
    try:
        ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
        try:
            ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
            raise AssertionError("second run in same dir should refuse")
        except ideas_ai.Refused:
            pass
        assert stub.chat_calls == 1
    finally:
        teardown(old)


def t_concurrency_refused():
    stub = StubModelAPI(); good_chat(stub)
    tmp, old = setup(stub)
    try:
        assert ideas_ai._paid_lock.acquire(blocking=False)
        try:
            try:
                ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
                raise AssertionError("should have raised")
            except ideas_ai.Refused as e:
                assert "in flight" in str(e) and not e.spent
            assert stub.chat_calls == 0
        finally:
            ideas_ai._paid_lock.release()
    finally:
        teardown(old)


def t_cross_process_lock_refused():
    """A second server PROCESS holding the flock must refuse the paid path
    before any traffic - one grant is one call, period."""
    import subprocess
    stub = StubModelAPI(); good_chat(stub)
    tmp, old = setup(stub)
    try:
        holder_code = chr(10).join([
            "import fcntl, os, time",
            "fd = os.open(os.path.join(" + repr(tmp) + ", 'idea.lock'), os.O_CREAT | os.O_RDWR, 0o600)",
            "fcntl.flock(fd, fcntl.LOCK_EX)",
            "print('holding', flush=True)",
            "time.sleep(30)",
        ])
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code],
            stdout=subprocess.PIPE)
        assert holder.stdout.readline().strip() == b"holding"
        try:
            try:
                ideas_ai.suggest_with_model(METAS, "run-t", state_dir=tmp)
                raise AssertionError("should have raised")
            except ideas_ai.Refused as e:
                assert "lock" in str(e) and not e.spent
            assert stub.count_calls == 0 and stub.chat_calls == 0
            assert not os.path.exists(os.path.join(tmp, "idea-ledger.json"))
        finally:
            holder.terminate(); holder.wait()
    finally:
        teardown(old)


if __name__ == "__main__":
    for name, fn in sorted(dict(
        not_configured=t_not_configured,
        malformed_envelope=t_malformed_envelope,
        partial_envelope=t_partial_envelope,
        wide_envelope=t_wide_envelope,
        zero_envelope=t_zero_envelope,
        no_key=t_no_key,
        count_unavailable=t_count_unavailable,
        count_over_cap=t_count_over_cap,
        charged_call_error=t_charged_call_error,
        non_json_retained=t_non_json_retained,
        rejected_provenance_durable=t_rejected_provenance_durable,
        no_rejected_record_on_success=t_no_rejected_record_on_success,
        indeterminate_record_on_unknown_error=t_indeterminate_record_on_unknown_error,
        bare_array_rejected=t_bare_array_rejected,
        real_wrapper_shape_still_refused=t_real_wrapper_shape_still_refused,
        documented_schema_sent=t_documented_schema_sent,
        fake_export_dropped=t_fake_export_dropped,
        all_fake_refused=t_all_fake_refused,
        schema_violations_dropped=t_schema_violations_dropped,
        happy_path=t_happy_path,
        ledger_reuse_refused=t_ledger_reuse_refused,
        concurrency_refused=t_concurrency_refused,
        cross_process_lock_refused=t_cross_process_lock_refused,
    ).items()):
        check(name, fn)
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
