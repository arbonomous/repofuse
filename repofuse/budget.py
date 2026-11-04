"""Durable aggregate budget accounting for one qualification run.

Every charged call (including the 1-token probe) reserves against a persisted
budget file BEFORE it fires and commits measured usage after. A second
concurrent or repeated run sees the consumed reservation and refuses once the
aggregate envelope is spent. This is local accounting, not a provider billing
cap - the dollar figure remains an estimate.
"""
from __future__ import annotations

import json
import os
import time

RUN_ENVELOPE = {
    # Original approved run: 5 charged + 5 count (2026-11-03, user grant).
    # The incident run consumed 3 charged (2 committed probes + 1
    # interrupted auto-heal reservation, unknown disposition) + 3 count.
    # 6/6 below is main's PROPOSED minimum top-up (+1/+1, remaining
    # capacity arch/glue/test, NO heal) - it is source-coherent only and
    # NOT active authority: the run stays held until the user grants it.
    "max_calls": 6,
    # provider count_tokens checks, tracked durably like charged calls.
    # Set from the approved envelope (was 5; incident consumed 3).
    "max_count_calls": 6,
    "max_input_tokens": 12000,    # per call, provider-measured preflight
    "max_output_tokens": 4096,    # per call, provider-enforced max_tokens
    "max_total_input_tokens": 60000,
    "max_total_output_tokens": 20480,
}


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            with open(path) as f:
                self.state = json.load(f)
        else:
            self.state = {"calls": [], "reserved_input": 0,
                          "reserved_output": 0,
                          "actual_input": 0, "actual_output": 0}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, self.path)

    def reserve(self, step, input_tokens, output_tokens):
        """Reserve before a charged call; raises BudgetExceeded."""
        env = RUN_ENVELOPE
        # No-retries guard: one reservation per named step, EVER. An
        # interrupted reservation (actual=None) is consumed, not reusable,
        # so a re-run of an interrupted stage refuses instead of refiring
        # (closes the incident's duplicate-probe failure mode structurally).
        if any(c["step"] == step for c in self.state["calls"]):
            raise BudgetExceeded(
                f"step {step!r} already reserved; no retries - an "
                "interrupted reservation is consumed, not reusable")
        if len(self.state["calls"]) >= env["max_calls"]:
            raise BudgetExceeded(f"call count cap {env['max_calls']}")
        if input_tokens > env["max_input_tokens"]:
            raise BudgetExceeded(f"input {input_tokens} > per-call cap")
        if output_tokens > env["max_output_tokens"]:
            raise BudgetExceeded(f"output {output_tokens} > per-call cap")
        if (self.state["reserved_input"] + input_tokens
                > env["max_total_input_tokens"]):
            raise BudgetExceeded("aggregate input cap")
        if (self.state["reserved_output"] + output_tokens
                > env["max_total_output_tokens"]):
            raise BudgetExceeded("aggregate output cap")
        self.state["calls"].append({
            "step": step, "reserved_input": input_tokens,
            "reserved_output": output_tokens, "actual": None,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        self.state["reserved_input"] += input_tokens
        self.state["reserved_output"] += output_tokens
        self._save()

    def record_count(self, step):
        """Durably record a provider count_tokens check BEFORE it fires,
        so the count-check half of the approved envelope is enforced by
        the same durable accounting as charged calls (previously untracked)."""
        env = RUN_ENVELOPE
        counts = self.state.setdefault("count_calls", [])
        # Same one-per-step guard as reserve(), applied BEFORE the count
        # endpoint fires: without it, re-running an interrupted stage would
        # still send a real count_tokens request (breaching no-retries on
        # the count endpoint) before the charged-side guard could stop it.
        if any(c["step"] == step for c in counts):
            raise BudgetExceeded(
                f"count check for step {step!r} already recorded; no "
                "retries - an interrupted stage refuses BEFORE the count "
                "endpoint fires")
        if len(counts) >= env["max_count_calls"]:
            raise BudgetExceeded(
                f"count-check cap {env['max_count_calls']}")
        counts.append({"step": step,
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())})
        self._save()

    def commit(self, step, usage):
        """Commit measured usage for the most recent reservation of step."""
        inp = int(usage.get("prompt_tokens") or 0)
        outp = int(usage.get("completion_tokens") or 0)
        for call in reversed(self.state["calls"]):
            if call["step"] == step and call["actual"] is None:
                call["actual"] = {"input": inp, "output": outp}
                break
        self.state["actual_input"] += inp
        self.state["actual_output"] += outp
        self._save()
        return {"input": inp, "output": outp}
