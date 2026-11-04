"""Offline tests for the 0.6.3 incident repairs (2026-11-04).

Covers the two reviewer blockers:
- durable duplicate-step refusal INCLUDING an interrupted reservation
  (a stage killed after reserving but before committing must refuse to
  re-fire - the exact failure mode that caused the duplicate probe), and
- provider count_tokens checks recorded durably BEFORE the endpoint call
  and capped by the same budget accounting as charged calls.

No provider calls anywhere in this module; model_api is monkeypatched.
"""
import json
import os
import tempfile
import unittest

from repofuse import model_api
from repofuse import synthesize as synth_mod
from repofuse.budget import Budget, BudgetExceeded, RUN_ENVELOPE

# The incident run's ACTUAL preserved budget history (2026-11-04),
# verbatim: 4 charged + 4 count consumed, closed with a terminal arch
# failure. Never reset, renamed, or reused.
INCIDENT_CALLS = [
    {"step": "probe", "reserved_input": 171, "reserved_output": 1,
     "actual": {"input": 14, "output": 1}, "ts": "2026-11-04T03:25:19Z"},
    {"step": "auto-heal", "reserved_input": 2041, "reserved_output": 4096,
     "actual": None, "ts": "2026-11-04T03:25:22Z"},
    {"step": "probe", "reserved_input": 171, "reserved_output": 1,
     "actual": {"input": 14, "output": 1}, "ts": "2026-11-04T03:26:07Z"},
    {"step": "architecture-manifest", "reserved_input": 5036,
     "reserved_output": 4096,
     "actual": {"input": 4879, "output": 4096},
     "ts": "2026-11-04T03:40:11Z"},
]
INCIDENT_COUNT_CALLS = [
    {"step": "probe", "ts": "2026-11-04T03:25:19Z", "backfilled": True},
    {"step": "auto-heal", "ts": "2026-11-04T03:25:22Z", "backfilled": True},
    {"step": "probe", "ts": "2026-11-04T03:26:07Z", "backfilled": True},
    {"step": "architecture-manifest", "ts": "2026-11-04T03:40:11Z",
     "backfilled": True},
]


def make_budget(tmp, state=None):
    path = os.path.join(tmp, "budget.json")
    if state is not None:
        with open(path, "w") as f:
            json.dump(state, f)
    return Budget(path)


def incident_state():
    return {"calls": [dict(c) for c in INCIDENT_CALLS],
            "count_calls": [dict(c) for c in INCIDENT_COUNT_CALLS],
            "reserved_input": 7419, "reserved_output": 8194,
            "actual_input": 4907, "actual_output": 4098}


class DuplicateStepRefusal(unittest.TestCase):
    """The no-retry guarantee, including the interrupted-stage case."""

    def test_committed_step_refuses_second_reservation(self):
        tmp = tempfile.mkdtemp(prefix="rf063-dup-")
        b = make_budget(tmp)
        b.reserve("architecture-manifest", 100, 10)
        b.commit("architecture-manifest",
                 {"prompt_tokens": 90, "completion_tokens": 5})
        with self.assertRaises(BudgetExceeded) as ctx:
            b.reserve("architecture-manifest", 100, 10)
        self.assertIn("already reserved", str(ctx.exception))
        self.assertIn("no retries", str(ctx.exception))

    def test_interrupted_reservation_refuses_rerun(self):
        """Interrupted-stage test: a reservation whose commit never landed
        (process killed mid-call, actual=None) is CONSUMED, not reusable;
        re-running that stage must refuse instead of duplicating the call."""
        tmp = tempfile.mkdtemp(prefix="rf063-interrupted-")
        b = make_budget(tmp)
        b.reserve("test-synthesis", 5000, 4096)
        # simulate the kill: no commit() ever runs; actual stays None
        b2 = make_budget(tmp)  # fresh process re-reads durable state
        self.assertIsNone(b2.state["calls"][0]["actual"])
        with self.assertRaises(BudgetExceeded) as ctx:
            b2.reserve("test-synthesis", 5000, 4096)
        self.assertIn("interrupted reservation is consumed",
                      str(ctx.exception))
        # and the refusal is durable: no new reservation was appended
        b3 = make_budget(tmp)
        self.assertEqual(len(b3.state["calls"]), 1)

    def test_distinct_steps_still_allowed(self):
        tmp = tempfile.mkdtemp(prefix="rf063-distinct-")
        b = make_budget(tmp)
        b.reserve("architecture-manifest", 100, 10)
        b.reserve("glue-synthesis", 100, 10)  # different step: fine
        self.assertEqual(len(b.state["calls"]), 2)


class CountCallAccounting(unittest.TestCase):
    def test_count_recorded_before_endpoint_call(self):
        """call_gated must durably record the count check BEFORE
        model_api.count_tokens fires (checkpoint-before-every-request)."""
        tmp = tempfile.mkdtemp(prefix="rf063-order-")
        b = make_budget(tmp)
        observed = {}

        orig_count = model_api.count_tokens
        orig_chat = model_api.chat_completion

        def spying_count(*a, **k):
            # at the moment the endpoint is (would be) hit, the durable
            # ledger must already contain this step's count reservation
            on_disk = json.load(open(b.path))
            observed["counts_on_disk"] = [
                c["step"] for c in on_disk.get("count_calls", [])]
            return 100

        model_api.count_tokens = spying_count
        model_api.chat_completion = lambda *a, **k: {
            "content": "ok", "model": "m",
            "usage": {"prompt_tokens": 90, "completion_tokens": 5},
            "latency_ms": 1}
        try:
            synth_mod.call_gated("glue-synthesis",
                                 [{"role": "user", "content": "hi"}], tmp, b)
        finally:
            model_api.count_tokens = orig_count
            model_api.chat_completion = orig_chat
        self.assertEqual(observed["counts_on_disk"], ["glue-synthesis"])

    def test_count_cap_enforced(self):
        tmp = tempfile.mkdtemp(prefix="rf063-countcap-")
        b = make_budget(tmp)
        for i in range(RUN_ENVELOPE["max_count_calls"]):
            b.record_count(f"c{i}")
        with self.assertRaises(BudgetExceeded) as ctx:
            b.record_count("one-too-many")
        self.assertIn("count-check cap", str(ctx.exception))

    def test_migration_preserves_history(self):
        """A pre-0.6.3 budget.json (no count_calls key) migrates via
        setdefault; a backfilled incident ledger keeps every entry."""
        tmp = tempfile.mkdtemp(prefix="rf063-migrate-")
        b = make_budget(tmp, {"calls": [], "reserved_input": 0,
                              "reserved_output": 0,
                              "actual_input": 0, "actual_output": 0})
        b.record_count("probe")
        self.assertEqual(len(b.state["count_calls"]), 1)
        # incident fixture: all 3 charged + 3 count entries survive intact
        b2 = make_budget(tmp, incident_state())
        self.assertEqual(len(b2.state["calls"]), 4)
        self.assertEqual(len(b2.state["count_calls"]), 4)
        self.assertIsNone(b2.state["calls"][1]["actual"])  # unknown kept


class IncidentEnvelopeCoherence(unittest.TestCase):
    """The ACTUAL 4+4 incident ledger is closed: probe, auto-heal AND
    architecture-manifest are burned; 2+2 slots remain numerically but the
    run can never complete (arch is gone, glue/test depend on it), and the
    driver records the run failed_terminal. A future attempt is a fresh
    ledger under fresh authority - this one is never reused."""

    def test_closed_ledger_burned_steps_and_terminal(self):
        tmp = tempfile.mkdtemp(prefix="rf063-envelope-")
        b = make_budget(tmp, incident_state())
        # all three executed step names refuse
        for step, args in (("probe", (171, 1)),
                           ("auto-heal", (2041, 4096)),
                           ("architecture-manifest", (5036, 4096))):
            with self.assertRaises(BudgetExceeded):
                b.reserve(step, *args)
            with self.assertRaises(BudgetExceeded):
                b.record_count(step)
        # 2+2 slots numerically remain (6/6 envelope) but cannot finish
        # the pipeline; a 7th call is impossible regardless
        b.reserve("glue-synthesis", 12000, 4096)
        b.reserve("test-synthesis", 12000, 4096)
        with self.assertRaises(BudgetExceeded):
            b.reserve("extra", 100, 10)
        b.record_count("glue-synthesis")
        b.record_count("test-synthesis")
        with self.assertRaises(BudgetExceeded):
            b.record_count("extra")
        self.assertEqual(len(b.state["calls"]), 6)
        self.assertEqual(len(b.state["count_calls"]), 6)
        self.assertLessEqual(b.state["reserved_input"],
                             RUN_ENVELOPE["max_total_input_tokens"])
        self.assertLessEqual(b.state["reserved_output"],
                             RUN_ENVELOPE["max_total_output_tokens"])


class DriverStateRecovery(unittest.TestCase):
    """Driver-level recovery: repaired staged state routes to arch; an
    unrepaired (failed) probe blocks; heal stage refuses outright."""

    def _load_driver(self):
        import importlib.util
        # External runtime artifact; set REPOFUSE_TEST_DRIVER_PATH to enable.
        path = os.environ.get("REPOFUSE_TEST_DRIVER_PATH", "")
        if not os.path.isfile(path):
            self.skipTest("REPOFUSE_TEST_DRIVER_PATH not set to a staged driver file")
        spec = importlib.util.spec_from_file_location("run_qual_staged",
                                                      path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_repaired_probe_state_routes_to_arch(self):
        drv = self._load_driver()
        st = {"status": "in_progress", "files_written": [],
              "steps": {"probe": {"status": "ok", "measured": 171,
                                  "actual": {"input": 14, "output": 1}}}}
        self.assertEqual(drv.next_action(st), "arch")

    def test_failed_probe_state_blocks(self):
        drv = self._load_driver()
        st = {"status": "failed", "files_written": [],
              "steps": {"probe": {"status": "failed", "detail": "x"}}}
        self.assertTrue(drv.next_action(st).startswith("BLOCKED"))

    def test_failed_acceptance_is_terminal_no_heal(self):
        drv = self._load_driver()
        st = {"status": "in_progress", "files_written": [],
              "steps": {"probe": {"status": "ok"},
                        "architecture-manifest": "done",
                        "glue-synthesis": "done",
                        "test-synthesis": "done"},
              "acceptance_status": "failed", "attested": True}
        nxt = drv.next_action(st)
        self.assertTrue(nxt.startswith("TERMINAL"), nxt)
        self.assertIn("NO HEAL", nxt)


if __name__ == "__main__":
    unittest.main()


class CountEndpointNoRetry(unittest.TestCase):
    """The reviewer's final blocker: an interrupted-stage rerun must refuse
    at record_count, BEFORE count_tokens fires - zero endpoint invocations,
    ledger byte-identical."""

    def test_interrupted_rerun_fires_no_count_request(self):
        tmp = tempfile.mkdtemp(prefix="rf063-countguard-")
        # stage was interrupted: charged reservation AND count checkpoint
        # both already on disk for this step
        state = {"calls": [{"step": "test-synthesis", "reserved_input": 5000,
                            "reserved_output": 4096, "actual": None,
                            "ts": "2026-11-04T03:25:22Z"}],
                 "count_calls": [{"step": "test-synthesis",
                                  "ts": "2026-11-04T03:25:22Z"}],
                 "reserved_input": 5000, "reserved_output": 4096,
                 "actual_input": 0, "actual_output": 0}
        b = make_budget(tmp, state)
        before = open(b.path, "rb").read()
        calls = {"n": 0}
        orig_count = model_api.count_tokens
        orig_chat = model_api.chat_completion

        def forbidden(*a, **k):
            calls["n"] += 1
            raise AssertionError("endpoint must never be reached")

        model_api.count_tokens = forbidden
        model_api.chat_completion = forbidden
        try:
            b2 = make_budget(tmp)  # fresh process re-reads durable state
            with self.assertRaises(BudgetExceeded) as ctx:
                synth_mod.call_gated("test-synthesis",
                                     [{"role": "user", "content": "hi"}],
                                     tmp, b2)
        finally:
            model_api.count_tokens = orig_count
            model_api.chat_completion = orig_chat
        self.assertIn("already recorded", str(ctx.exception))
        self.assertEqual(calls["n"], 0, "endpoint was invoked on a rerun")
        self.assertEqual(open(b.path, "rb").read(), before,
                         "ledger changed by refused rerun")

    def test_count_duplicate_guard_allows_new_steps(self):
        tmp = tempfile.mkdtemp(prefix="rf063-countguard2-")
        b = make_budget(tmp, incident_state())
        # burned steps refuse at the count checkpoint
        for step in ("probe", "auto-heal", "architecture-manifest"):
            with self.assertRaises(BudgetExceeded):
                b.record_count(step)
        # glue/test have no count entries yet and must pass
        for step in ("glue-synthesis", "test-synthesis"):
            b.record_count(step)
        self.assertEqual(len(b.state["count_calls"]), 6)
