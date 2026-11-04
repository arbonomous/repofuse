# Build review approvals

One file per reviewed build run: `<run-id>.json`

```json
{
  "run_id": "run-...",
  "files": {"generated/app.py": "<sha256>", "test_fused.py": "<sha256>",
            "vendor/...": "<sha256>"},
  "reviewer": "who read the exact source",
  "reviewed_at": "when",
  "note": "scope of the review"
}
```

Rules:

- Written ONLY by a human/reviewer after reading the exact retained
  source under `studio/runs/<run-id>-build/` (see its
  `review-request.json` for the pinned hashes). NO pipeline code writes
  here; the server only reads.
- `files` must equal the build's full executable tree hash for
  EXACTLY these bytes: generated app, acceptance tests, vendored deps.
  Any mutation, addition or deletion invalidates approval; the server
  re-hashes before every spawn and refuses on mismatch.
- Without a matching manifest the generated code never executes - not
  even its own acceptance tests.
