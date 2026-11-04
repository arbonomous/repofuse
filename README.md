# RepoFuse

Repository synthesis prototype for the Meta AI Developer Hackathon.

RepoFuse takes selected repositories through pinned ingest, static analysis,
license retention, safety qualification, Meta model synthesis, independent
whole-tree review, isolated tests and contained local serving.

## Demonstrated result

The demonstrated pair is Pallets **itsdangerous** + **MarkupSafe**, building
signed, expiring share links for a small notes app. This is evidence for this
pair, not a claim that arbitrary repositories can be fused successfully.

The genuine Studio generation run used **Meta Muse Spark 1.3** through the
Meta Model API. Its four charged stages were probe, architecture, glue and
tests, with four separate count-token requests. Provider-reported usage was
6,339 input / 4,526 output tokens. Actual request payloads and raw responses
were retained locally. They are runtime evidence, not bundled credentials or
an invitation to publish private prompts.

Native model output passed seven tests in Linux namespace isolation. A
negative control failed with glue removed. Review found one functional defect:
custom expiry was advertised but validation always used one hour. The final
**assistant-repaired** copy consistently uses a fixed one-hour lifetime. The
native output and raw responses are preserved separately. This is a reviewed
prototype workflow, not fully autonomous or production-ready software.

The demo notes store is **in memory**. Restarting loses notes, and each app
spawn rotates its signing secret, invalidating old links. The app is not a
persistent notes service or a security-complete sharing product.

## Local Studio: validated platform and quick start

Behavioral tests and contained serving have been exercised on **Linux with
bubblewrap**. macOS execution has **not** been validated. Native macOS does
not supply the Linux namespace containment this prototype requires; a Mac
browser may access a Studio running in a suitable Linux environment, but that
setup is not yet a verified turnkey Mac installation.

For a Linux development environment with Python 3.10+ and bubblewrap:

```sh
# From the repository root. No API key is needed to inspect the UI/free path.
PYTHONPATH="$PWD" python3 studio/serve.py 8317
# Open http://127.0.0.1:8317/ on that same machine.

# Development tests (pytest must be installed in your development environment):
python3 -m pytest tests -q
```

Studio's free stages really ingest, analyze, qualify and vendor selected
code, then stop before paid generation without a key. A retained local run
requires its runtime files; a fresh source checkout does not contain private
run state, approvals, keys or active spending envelopes. Paid builds require
a deliberately configured bounded envelope, valid credentials and the
independent safety acknowledgment where required. A configuration file is
not spending permission. Do not bypass these gates to reproduce a demo.

The reviewed app opens on an owned **127.0.0.1 local origin**. It is usable
only on that machine, not a public, phone or remote-access deployment. The
legacy `/app/<run>/` prefix proxy is not the advertised working path.

## What the pipeline does

- Ingest records actual commits and retains upstream license notices.
- Python exports use AST analysis; JS/TS extraction uses labeled heuristics.
- A deterministic manifest records boundaries, conflicts and acceptance goals.
- Synthesis builds architecture, adapter code and tests using selected-code
  metadata, public README excerpts, intent and earlier same-run model output.
  Downstream test prompts can include generated source; this is **not** a
  summaries-only privacy guarantee. Check every input's disclosure rights.
- Request payloads are retained before count/model calls, and raw responses
  are retained before parsing. Exact payload construction is shared with the
  send path. No-key architecture staging is prepared output, not generation.
- Generated and vendored files, shim and serving contract must match a
  separately reviewed whole-tree hash manifest before execution. Review of
  glue alone is insufficient; changing any pinned byte re-gates execution.
- Behavioral tests require bubblewrap isolation and a nonzero, signed test
  verdict. Vacuity testing checks that removing glue breaks the tests.
- Contained serving uses a read-only app tree, cleared environment, private
  namespaces including network, and an inherited parent-owned listener.
  A long-lived owner thread preserves child lifetime across HTTP requests;
  stop/exit closes the listener and reaps the child.

## Limits and cost

Input code and model outputs are untrusted. Static findings and advisory
lookups qualify a run, not certify it safe. No matching advisory is a WARN,
not proof of coverage or absence of vulnerabilities. Required unavailable
checks fail closed. WARN and rehydrated runs need an exact run/pin/verdict-bound
independent acknowledgment. That acknowledgment clears only that gate.

The demonstrated run was bounded to **four charged + four count requests**,
12,000 measured input / 4,096 output tokens per call, and 48,000 input /
16,384 output aggregate reservation limits. These are that run's reviewed
configuration, not universal defaults or dollar billing caps. Count checks,
reservations and actual usage are durable. Reserved steps are never retried,
including interrupted reservations. No automatic healing was used in this run.

Output caps are request controls; local budgets are not provider-enforced
billing limits. Count-endpoint billing is undocumented here and is not assumed
free. Credits can expire, billing can lag and account spending alerts are not
hard caps. Verify current account terms, available credits and authority before
spending. Promo-credit terms may permit content use for product improvement;
do not send private code or account data on the assumption of standard-mode
privacy alone.

The trusted test runner's signed verdict prevents simple output forgery, not
all adversarial in-process interference. Namespace isolation and resource
limits reduce exposure; they are not a security proof. No bare-host generated
execution is an acceptable fallback when containment is unavailable.

## Licenses and provenance

The demonstrated upstream repositories retain their BSD-3-Clause notices.
License detection is heuristic; inspect actual notices and redistribution
conditions before releasing a fused result. Dependencies retain their own
licenses. Do not remove upstream notices or attribute assistant repairs to the
Meta model. Original RepoFuse code and documentation are licensed under the MIT License
in `LICENSE`. Third-party code and materials remain under their own licenses.

Public repository release, hosted demo/video publication and hackathon
submission are separate owner decisions. This source does not authorize them.
