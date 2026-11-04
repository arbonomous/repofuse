# Bounded proposal: one general synthesis run on a chosen vendor tree

Status: PREPARED, NOT requested, NOT granted. This document exists so a
future decision can be exact. It authorizes nothing by itself; a run
also requires Jose's explicit per-run grant, a pass/acknowledged-warn
safety verdict bound to the run's commits, and the reviewer gate.

## What the run is

One fresh `run_synthesis` over the fusion dir a Studio fuse run already
built (plan manifest + acceptance criteria + the SELECTED repos'
vendored, readback-verified code). A fresh budget ledger - the
2026-11-04 ledger is closed and never reused.

## Charged calls: EXACTLY 4, in this order - no headroom

1. probe (max_tokens=1; validates auth + usage accounting)
2. architecture-manifest (strict json_schema; output budget text caps
   the response under 6000 chars; <=12 exports/repo, <=8 bridge,
   <=8 shims, <=6 risks, strings <=160 chars)
3. glue-synthesis (valid-JSON mode ONLY - never claimed
   schema-constrained; writes only generated/<name>.py slots)
4. test-synthesis (strict json_schema; writes only test_fused.py)

The RUN_ENVELOPE constants (6 charged / 6 count) are a CEILING, not
the ask. This run activates a run-local envelope file (fail-closed:
missing or malformed refuses) set to EXACTLY 4 charged calls and 4
count calls - so a fifth call of either kind is a mechanical
BudgetExceeded, not a policy hope. There is NO heal step in this path
and NO retry: truncation is terminal (raw retained, usage committed).
The 2-call difference between the ceiling and this envelope is not
available to anything.

`reasoning_effort="minimal"` on the three steps (the model otherwise
burns reasoning tokens against max_tokens).

## Hard bounds (repofuse/budget.py RUN_ENVELOPE)

- <=6 charged calls and <=6 count-preflight calls, durably checkpointed
- per call: provider-measured input <=12000 tokens (count preflight;
  an unavailable count endpoint REFUSES the charged call), output
  max_tokens <=4096 (provider-enforced)
- aggregate: <=60000 in / <=20480 out; breach aborts the run
- prompt chars <=48000 per call (hard bound, not a token substitute)
- generation caps: <=20 files, <=200KB/file, <=1MB aggregate; vendor
  tree, manifests and LICENSEs immutable to the writer

## Failure semantics (verified offline)

- finish_reason="length" -> terminal TruncatedOutput: raw response
  retained, usage committed, NO retry (the 2026-11-04 arch truncation
  at 4879/4096 failed exactly this way; that failure mode is handled,
  not claimed fixed)
- every raw paid response retained BEFORE parsing
- schema/size validation fail-closed; retained output never repaired
- no auto-heal in this path

## Review and execution posture after generation

- NOTHING executes until an independent whole-tree sha256 attestation
  (generated/ + test_fused.py + entire vendor/) approves the exact
  bytes; symlinks anywhere in the tree fail the attestation and the
  sandbox spawn
- WARN safety verdict additionally requires the out-of-band reviewer
  acknowledgment (studio/safety-acks, commit- and verdict-hash-bound)
- verify = sandboxed run (no network, cleared env) + derived acceptance
  criteria + vacuity control; the model's own tests are a supporting
  signal, never the bar

## Steering

The user's chosen idea or intent text enters every prompt as bounded
(<=500 chars) `user_intent` data - steering only, never executed,
never authority. Empty intent means the bundle carries an empty
string, stated plainly.

## What is verified ready today (offline, fixtures)

- the staged path (probe -> arch -> glue -> test) drives to completion
  over a chosen vendor tree with a contract-faithful fake provider:
  4 charged + 4 preflight, files written into authorized slots only,
  raw responses retained (tests/test_mock_synthesis_qualification.py)
- the review gate pins mock-generated files AND the chosen vendor tree;
  one tampered vendored byte fails it
- the no-key path writes the real prompt bundle and stops
  (pending_no_key, zero provider contact)

## What is NOT promised

- no arbitrary-pair success guarantee: synthesis quality for any given
  repo pair is unknown until tried
- no tonight end-to-end commitment
- no execution of generated or vendored code without the gates above
