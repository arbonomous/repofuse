# Qualification run protocol (controlled, pinned, measured)

## Where it runs

The qualification run executes entirely in a Linux environment with
bubblewrap available - the same class of environment where the
hostile-boundary suite passed. Jose's Mac / OrbStack is NOT required for the
qualification run itself. Mac involvement is only needed later for Jose's
own demo recording, if he chooses that.

## Pinned input snapshots

Qualification does not clone "whatever the branch points at now". Both repos
are pinned to observed commits; ingest refuses a pin mismatch:

- microdot  https://github.com/miguelgrinberg/microdot @ 7742db9ff9f49635de3387145fafe56bf2377a97 (MIT)
- peewee    https://github.com/coleifer/peewee        @ e9b55c96b0c1e5c13c0053205868f188af617945 (MIT)

General/arbitrary user-supplied repo URLs are out of scope for the
qualification build (bounded ingestion only); arbitrary-input hardening is
separate future work.

## Charged-call gating, in order (all calls pass one gated path)

1. Prompts are built deterministically and written to prompts/ for review.
2. A 1-TOKEN PROBE runs first and is counted in the budget: its
   usage.prompt_tokens must agree with the count_tokens measurement for the
   same messages, or the run aborts before any further spend.
3. Every call (probe, architecture, glue, test, heal) reserves against a
   durable budget file (budget.json) BEFORE firing and commits measured
   usage after: per-call 12,000 measured input tokens, provider-enforced
   4096 output tokens, 60s timeout, zero retries; aggregate envelope
   5 calls / 60k input / 20,480 output tokens. count_tokens unavailable,
   unparseable, or unsupported = REFUSE. No estimate is accepted on the
   charged path.
4. Transport: endpoint host pinned to api.meta.ai, redirects refused (a
   redirect could forward the Bearer token), response/error bodies
   byte-capped, key read from env and never written to disk or logs.
5. telemetry.jsonl records measured usage per call; the report shows
   measured tokens and list-price math labeled as an estimate.

## Decisive judgment: a FIXED acceptance test, not the model's own tests

The qualification verdict comes from repofuse/qualification/target.py's
ACCEPTANCE_TEST - authored by RepoFuse, copied into fused_app/ at package
time, and NOT writable by the model (generated files are confined to a
generated/ slot plus one test_fused.py slot; vendor/, LICENSEs, manifests
and existing files are immutable). It drives the real vendored microdot app
through microdot's own async TestClient, verifies persistence through the
real vendored peewee ORM across a simulated restart, asserts the storage
class is a genuine peewee.Model on a SqliteDatabase, and checks 404
behavior. The verdict channel defeats output forgery only (HMAC-signed by a trusted runner); deliberately adversarial in-process code could still tamper, so a pass is a bounded accidental-correctness signal, not a security proof. A behavioral pass additionally requires: import closure (stdlib +
vendored + generated only), an observed "Ran N tests / OK" verdict with
N >= 1 (exit code 0 alone never counts), and a vacuity control proving the
suite FAILS with the glue removed. The model-generated test_fused.py is
supplementary evidence, never the verdict.

## Verification of the result

- Generated files pass traversal/size/count defenses before being written.
- Behavioral tests run only inside the bubblewrap sandbox (no network, fresh
  namespaces, rlimits); there is no host execution fallback. Without
  bubblewrap the run reports static_only and stops.
- The fused app is vendored inputs (sha256-pinned) + generated glue; nothing
  is claimed working unless the sandbox run observed the tests passing.

## What is NOT claimed

No production-readiness, no novelty, no judging-rubric score, no arbitrary
repo support, no provider-enforced dollar cap.
