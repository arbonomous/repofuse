# RepoFuse

A supervised repository-integration prototype built during the Meta AI Developer Hackathon.

Supply two public GitHub repository links, inspect real Meta-generated ideas, and select an eligible integration. RepoFuse pins source commits, retains licenses, checks inputs, generates integration logic and tests, then stops for independent review before contained testing and local serving.

## Current demonstrated result

The current successful pair is **cachetools + boltons**, combined into a Cached Descriptive Statistics Workbench. Actual **muse-spark-1.3** calls covered idea suggestion, architecture, integration logic and tests. RepoFuse supplies the fixed HTTP/UI workbench around generated compute logic; it does not generate an arbitrary bespoke frontend.

This generated integration was not manually repaired. Seven model-written tests, eight independent probes, and real Chrome checks passed for numeric input, cache configuration changes, repeat hits, invalid input and restoring defaults. Earlier failed generations remain failures. One successful pair is not proof that arbitrary repositories work.

The retained exact example and upstream MIT/BSD notices are under `examples/cached-stats/`. The integrity manifest is not an execution approval, and the example does not load itself into Studio as a retained run. Source review in the demonstrated workflow was supervised. No hosted judge service or live automatic reviewer is available.

Earlier itsdangerous + MarkupSafe signed-notes work remains under `examples/signed-notes/`. That earlier result required a separately labeled assistant repair for a fixed one-hour expiration. It is not the current cachetools + boltons result.

## Linux local setup and limits

Use a compatible Linux machine with Python 3, Git, bubblewrap, util-linux/prlimit and namespace support. Use a system interpreter that exists inside the runtime containment:

```sh
/usr/bin/python3 -B studio/serve.py 8317
# Open http://127.0.0.1:8317/ on that machine.
```

A Mac browser was used with Studio inside a Linux VM; native Mac containment is not supported. New generation requires a model credential, bounded spending configuration and current review gates. A key or configuration file is not a spending grant. No key, active spending envelope, private run state or approvals are included.

The supported runtime is Python WSGI with the standard library and selected compatible vendored Python packages. Input fields and result tables use a fixed workbench, not arbitrary frontend or network stacks. New runs may stop for independent review. Do not bypass the gates or run generated code on the bare host when containment is unavailable.

The product is a local supervised prototype, not a production service or unattended judge-ready builder. Local app state is temporary. Old replay links are not evidence of new generation, and a fresh clone does not include retained runtime state.

## Test status

The private assembled distribution's local subset reported 96 passed and one stale envelope-expectation failure (four expected versus the current five-call maximum). A separately qualified reviewer tree reported 355 passed. Neither statement is a blanket claim that every file in this public assembled distribution has passed a fresh complete release test. The generated cached-stats example has its own evidence described above.

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

Request counts and budgets are run-specific. No active spending envelope is included, and no request-count or token figure here is a universal price or provider-enforced dollar cap. Reserved steps are not automatically retried.

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

The current example retains cachetools MIT and boltons three-clause BSD notices. Earlier vendored libraries retain their own notices.
License detection is heuristic; inspect actual notices and redistribution
conditions before releasing a fused result. Dependencies retain their own
licenses. Do not remove upstream notices or attribute assistant repairs to the
Meta model. Original RepoFuse code and documentation are licensed under the MIT License
in `LICENSE`. Third-party code and materials remain under their own licenses.

Public repository release, hosted demo/video publication and hackathon
submission are separate owner decisions. This source does not authorize them.
