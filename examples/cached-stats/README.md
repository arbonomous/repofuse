# Cached Descriptive Statistics Workbench

This is a retained successful RepoFuse integration of cachetools and boltons, generated during the hackathon with muse-spark-1.3. Meta generated integration logic and tests. RepoFuse supplies the fixed Python WSGI HTTP/UI workbench; it is not a generated bespoke frontend.

Upstream pins:
- cachetools: f314dfaa49fe646427581e16bea33112a2140eb2, MIT.
- boltons: d31d821d56c8f7756af9c30a864077f2e5855321, BSD-style three-clause license.

Both upstream LICENSE files remain in the vendored tree. Upstream code predates the hackathon and is not claimed as original RepoFuse work.

The generated integration in this example was not manually repaired. Seven model-written tests, eight independent probes, and real Chrome checks passed for numeric input, cache configuration, repeat hits, invalid input and restoring defaults. Earlier failed generations remain failures; this one pair does not establish arbitrary-pair support.

`source-manifest.json` lists SHA256 hashes of the exact retained execution tree. It proves integrity, not permission to execute. No runtime approval, reviewer key, credential, spending envelope, or provider request/response is shipped.

## Review and reproduction

1. Inspect the whole source tree and upstream notices. Do not run upstream setup hooks.
2. Obtain your own independent exact-byte source review through RepoFuse's gated review workflow. A fresh clone contains no retained run or approvals. This source example does not import itself into Studio as a ready-to-run run.
3. Use RepoFuse's contained Linux verification and serving path only after its current gates pass. Missing bubblewrap or namespace support is a blocker, not a reason to run generated code directly on the host.

The demonstrated workflow was supervised. No hosted judge service or automatic independent reviewer is provided. New generation requires a model credential, an approved bounded credit budget, input review and final source review. Local servers and in-memory cache state are temporary. This is not production-ready or an unattended arbitrary full-stack builder.
