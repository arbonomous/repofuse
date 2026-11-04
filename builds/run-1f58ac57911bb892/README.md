# Saved reviewed AI-built notes app (run-1f58ac57911bb892)

A real app the RepoFuse paid pipeline generated on 2026-11-04 from a
LOCALLY-GENERATED analysis card (the input card was not AI-selected - 0
model calls produced it; the 3 paid model calls were the architecture,
glue, and test steps).

Honest status:
- The generated app code (`app/generated/app.py`) is UNEDITED model output.
- The model's own test script (`app/test_fused.py`) FAILS as retained
  (test-side API misuse of microdot's async TestClient). It is kept
  unedited as historical evidence, never repaired or relabeled.
- The verification that passed: the fixed, model-independent CRUD
  contract acceptance, plus browser-driven create/edit/delete and
  restart-persistence checks on the original machine.
- Every file was hash-reviewed by an independent reviewer BEFORE the
  generated code ever executed. `manifest.json` pins the exact sha256 of
  all 441 files. `studio/import_build.py` re-verifies every byte against
  that manifest on this machine and refuses anything that differs.

To run it locally (free, no key, no model calls):

    python3 studio/import_build.py run-1f58ac57911bb892
    sh studio/run.sh
    # open http://127.0.0.1:8317/ and click
    # "Open the saved reviewed AI-built notes app"

The app starts with a fresh empty local database on this machine.
