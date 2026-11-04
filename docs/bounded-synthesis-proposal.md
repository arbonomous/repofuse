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

## Studio wiring status (implemented, DISARMED)

The route above is wired into Studio as a callable entrypoint, in a
state where spending is structurally impossible:

- `POST /api/build-general` (run_id): the spend/safety gate runs
  BEFORE the build thread spawns - a warn verdict without an
  out-of-band ack (studio/safety-acks/<run>.json, written by a person,
  never via HTTP) is refused with 403 before any count or provider
  call. Then run_general_build runs `run_synthesis` over THIS run's
  own vendored tree with the picked idea as user_intent and
  envelope_path=studio/envelope.general.json. That file does not
  exist: the fail-closed Budget refuses, zero provider contact. It
  also stops at pending_no_key when no key is presented. Both states
  are reported honestly as DISARMED, not as failures or successes.
- Idea click -> `POST /api/prepare-bundle` (free, key-stripped env,
  prompt bundle written, nothing sent) is the STEERING step; it is
  not generation. The click -> core-generation path is
  /api/build-general only. The fixed-stack /api/build remains for the
  recorded-notes replay only; non-recorded picks route to the general
  route.
- After a (future, separately granted) completed run: nothing
  executes. The whole tree (generated + vendored) is pinned with
  review-request.json (sha256 per file); status awaiting_review.
  `POST /api/build-general/verify` re-checks the reviewer-only
  attestation (studio's APPROVALS dir, no HTTP writer) and only then
  runs the sandboxed verify; the app is NOT auto-served. No
  attestation, or one tampered byte anywhere in the tree, refuses.
- Offline fixtures (tests/test_general_build_route.py): disarmed
  without envelope+key; armed with a fake provider + fixture envelope
  (4/4 ceiling) reaches awaiting_review with the whole tree pinned,
  nothing executed (no __pycache__ anywhere); the verify path refuses
  without attestation and states bwrap unavailability exactly.

## Reviewed serving/use path (implemented, containment-tested)

A general fused app is servable only under an explicit reviewed
contract, inside runtime containment, with the same execution gates as
verify:

- `fused_app/serving.json` declares exactly how to serve: version 1,
  kind `python-wsgi`, a dotted module + plain app_object identifier
  (a WSGI callable), a readiness path + expected HTTP status. The file
  lives INSIDE the attested tree - gluereview pins it like code, so a
  contract edited after review fails attestation. Validation is
  fail-closed (repofuse/serving.py): unknown kinds (including a plain
  `.run(host, port)` module, which cannot be contained to this
  standard), traversal, shell-ish names, missing module files, custom
  environment - all refused, never guessed.
- Generation emits the contract DETERMINISTICALLY
  (repofuse/serving.derive_contract): AST inspection only, nothing
  imported or executed; exactly one generated module exposing a
  top-level `app` is required, else no contract and an honest reason.
  The model never gets a contract write slot. The derived contract is
  added to the tree BEFORE pinning, so the reviewer attests its exact
  bytes; WSGI-shapedness is a stated hypothesis - a non-WSGI object
  fails honestly at the readiness probe.
- Serving runs inside bubblewrap with ALL namespaces unshared,
  INCLUDING NETWORK. The studio server binds and owns the listening
  loopback socket BEFORE spawn and the child only accepts on the
  inherited descriptor, so egress is architecturally impossible, there
  is no free-port race, and no foreign process can answer the probe.
  The fused tree is mounted read-only at /app; the only writable place
  is a fresh /tmp tmpfs (explicit scratch only). Environment is
  cleared and rebuilt from scrubbed values; no inherited key material.
  No bwrap, no serving - reviewed code never runs on the bare host.
- Lifecycle: POST /api/build-general/stop terminates the child and
  closes the listener; all general backends are terminated at server
  exit (atexit); the runner arms PR_SET_PDEATHSIG so the app is
  SIGKILLed if its container parent dies, closing the orphan window
  even when the server is killed -9.
- Gates before any spawn (ensure_general_backend): run build_verified;
  safety gate (reviewer sign-off on warn) still holds; whole-tree
  attestation still matches the current bytes; contract validates.
- Tested, not hypothesized (tests/test_general_serving_path.py, 27
  tests, bwrap present in this environment): every contract refusal
  shape; every gate refusal (unverified, unattested, tampered tree,
  TAMPERED CONTRACT, warn without sign-off, no containment); real
  contained serving + stop (port refuses afterward); capability proofs
  from INSIDE the container - outbound connection refused, the
  read-only tree unwritable, the host filesystem invisible; and the
  capstone: fixture generation via run_general_build -> derived
  contract -> attestation -> contained serving of the generated bytes.
