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
    # HISTORICAL, CLOSED: the 2026-11-04 run under its 6/6 envelope
    # (original 5+5 grant + a +1/+1 top-up) actually consumed 4 charged
    # (2 committed probes 14/1 each, 1 interrupted auto-heal reservation
    # with unknowable disposition preserved as consumed, 1 committed
    # architecture-manifest 4879/4096 truncated) + 4 count, then FAILED
    # TERMINALLY at arch. That ledger is preserved and never reset,
    # renamed, or reused; step names probe/auto-heal/architecture-manifest
    # are burned in it. Any future attempt is a FRESH run under fresh
    # user authority with a NEW budget ledger. These constants are
    # defaults for a fresh run, not authority.
    "max_calls": 6,
    # provider count_tokens checks, tracked durably like charged calls.
    "max_count_calls": 6,
    "max_input_tokens": 12000,    # per call, provider-measured preflight
    "max_output_tokens": 4096,    # per call, provider-enforced max_tokens
    "max_total_input_tokens": 60000,
    "max_total_output_tokens": 20480,
}


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, path, envelope_path=None):
        """If envelope_path names an existing JSON file, its keys override
        RUN_ENVELOPE for THIS run's ledger only (a run-local envelope such
        as qualification/proposed_envelope.json). The file is config, not
        authority: it must be activated deliberately per run, and it never
        touches any other ledger."""
        self.path = path
        self.envelope = dict(RUN_ENVELOPE)
        if envelope_path:
            # fail closed: an explicit envelope file that is missing or
            # malformed must NEVER silently fall back to larger defaults
            if not os.path.exists(envelope_path):
                raise BudgetExceeded(
                    f"envelope file {envelope_path} missing; refusing "
                    "rather than falling back to defaults")
            try:
                with open(envelope_path) as f:
                    override = json.load(f)
            except (OSError, ValueError) as e:
                raise BudgetExceeded(
                    f"envelope file {envelope_path} unreadable: {e}; "
                    "refusing rather than falling back to defaults")
            for k in self.envelope:
                if k in override:
                    self.envelope[k] = override[k]
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
        env = self.envelope
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
        env = self.envelope
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
