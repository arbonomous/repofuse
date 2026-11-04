# RepoFuse

Autonomous multi-repository synthesis engine — prototype.

RepoFuse ingests two or more GitHub repositories, statically maps their
capabilities and dependencies, detects integration conflicts, builds a
structured Fuse-Manifest DAG, and — when a Meta Model API key is configured —
uses Muse models to generate the adapter glue code and integration tests that
fuse the repos into a working hybrid app, then runs those tests in an
isolated subprocess and reports only observed results.

Built for the Meta Global AI Developer Hackathon.

## Honest status (read first)

What works today, verified by the test suite in `tests/`:

- **Ingest** — shallow-clones real repos; records commit SHA, license
  (heuristic text match), language mix, manifests, file tree, README excerpt.
- **Analyze** — Python exports parsed with the stdlib `ast` module; JS/TS
  exports/routes via labeled regex heuristics; dependencies from
  `requirements.txt` / `package.json` / `pyproject.toml`; env vars and ports.
- **Plan** — repo role classification (engine / interface / data), boundary
  candidates, deterministic conflict detection (version pins, module-name
  collisions, port collisions), and the Fuse-Manifest step DAG.
- **Verify** — runs the fused app's tests in a scrubbed subprocess and
  reports pass/fail/timeout only as observed.
- **Report** — `report.json` with the full evidence trail plus per-call model
  telemetry (`telemetry.jsonl`: model, tokens, latency).

What is gated and NOT claimed:

- **Model synthesis** (architecture manifest, glue code, generated tests)
  requires `MODEL_API_KEY`. Without it RepoFuse writes the exact prompt
  bundle to `prompts/` and reports `pending_no_key`. It never fabricates
  model output, and cached/demo output is never presented as a live run.
- "Production-ready" output is not claimed. Generated code is marked
  UNVERIFIED until the verify step passes.

## Meta model usage (verified against dev.meta.ai, 2026-11-03)

- `muse-spark-1.3` via Meta Model API (`https://api.meta.ai/v1`,
  OpenAI-compatible chat completions, Bearer `MODEL_API_KEY`) drives the
  architecture-manifest, conflict-resolution, glue-synthesis and
  test-synthesis steps. Sources: https://dev.meta.ai/docs/models,
  https://dev.meta.ai/docs/quickstart
- Muse Code is a CLI coding agent that itself runs on Muse Spark — there is
  no separate `muse-code-1.0` API model. RepoFuse can optionally use Muse
  Code as a harness, but its API calls target Muse Spark directly.
  Source: https://dev.meta.ai/docs/muse-code
- Muse Image (`muse-image`) is reserved for optional brand/design-token
  generation for the fused app. Source: https://dev.meta.ai/docs/overview

## Usage

```
pip install .
repofuse run https://github.com/<a> https://github.com/<b> --out /tmp/fusion
# or without installing:
python -m repofuse run <repo-a> <repo-b> --out /tmp/fusion
```

Outputs in `--out`: `ingest.json`, `analysis.json`, `fuse_manifest.json`,
`prompts/`, `synthesis.json`, `fused_app/`, `verification.json`,
`telemetry.jsonl`, `report.json`.

## Safety

Input repos are untrusted.

- **Ingest**: hooks disabled, no submodules, blob-filtered shallow clone,
  200MB cap, symlinks escaping the repo root are refused, oversized files
  skipped during analysis. Cloned code is never executed.
- **Synthesis**: the model receives summaries only (exports, routes,
  dependency names, README excerpt, tree sample) — never full source.
  Generated files go through traversal/absolute-path/symlink/size/count
  defenses and are stamped UNVERIFIED. Generated code is never executed by
  the synthesizer.
- **Verify**: behavioral tests run inside bubblewrap kernel namespaces
  (user/net/pid/ipc/uts) on a scratch copy of the fused app, with prlimit
  caps (60s CPU, 64 procs, 256 fds, 32MB file size, 1GB RAM) and no network.
  Aggregate scratch use has a SOFT watchdog bound (~256MB, poll-enforced
  with overshoot, not a strict quota). Sandbox python runs -S -s: host
  dist-packages are not importable BY DEFAULT (automatic site loading off),
  but host files remain present under /usr in the namespace; a deliberate
  sys.path insertion could still reach them. This is default-isolation,
  not access-invisibility. Test verdicts are HMAC-signed by a trusted
  runner (one-time key consumed before untrusted imports): this defeats
  OUTPUT forgery (printed 'Ran/OK' lines, fake verdict lines), not
  in-process tampering by deliberately adversarial code - generated output
  is never treated as a security proof. The behavioral bar is a bounded
  accidental-correctness test: a fixed author-written acceptance test
  executed against real vendored code, plus a vacuity control. No
  automatic execution of unreviewed model glue: generated/*.py and
  test_fused.py must be pinned by a host-side review attestation
  (sha256 of the exact reviewed bytes) before the sandbox will run
  them; any post-review change re-gates execution.
  (proven by a test that asserts socket connection fails). If bubblewrap is
  unavailable, RepoFuse falls back to static-only compile checks and says so.
  Environment scrubbing alone is never used to run untrusted code.
- **Budget**: every charged call (probe included) passes one gated path:
  provider-measured input preflight (refusal when measurement is
  unavailable - no estimate substitutes), durable aggregate reservation in
  budget.json, provider-enforced 4096-token output cap, 60s timeout, zero
  retries; aggregate envelope 5 calls / 60k input / 20,480 output tokens.
  Transport pins the api.meta.ai host and refuses redirects so the Bearer
  token cannot leak. Dollar figures from these caps and list prices are
  ESTIMATES, not provider-enforced billing caps; measured usage lands in
  telemetry.jsonl and a provider-side spend limit is recommended.
- **Judgment**: qualification is decided by a FIXED acceptance test
  (repofuse/qualification/target.py) exercising real vendored behavior,
  with import-closure checks, an observed test-count verdict, and a vacuity
  control (suite must fail with the glue removed). Model-generated tests
  are supplementary, never the verdict. Generated files are confined to a
  generated/ slot + one test slot; vendor tree, licenses and manifests are
  immutable; writes are exclusive-create with lstat parent checks, per-file
  and aggregate byte caps.
- **Provenance**: input repos are vendored into fused_app/vendor/<slug>/
  with per-file sha256 + commit SHAs (vendor_manifest.json); licenses are
  retained verbatim. Vendored code keeps its own license; detected licenses
  are heuristic guesses — verify before publishing any fusion.

## License of inputs

RepoFuse records each input repo's license where detectable. A fusion can
only be published when every input license permits it; that check is the
user's responsibility for now.
