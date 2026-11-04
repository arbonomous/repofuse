# Edit/delete extension - provenance

Status of the original goal: the fixed goal was save/read/edit/delete. The
reviewed baseline (assistant-repaired `generated/app.py`) proved save/read
only: create, list, retrieve one, 404 handling, and persistence across a
simulated restart. Edit and delete were absent.

This extension completes the goal OFFLINE, with no model calls:

- `assistant_ext.py` - assistant-authored. Registers `PUT /notes/<id>`
  (edit, validates the body exactly like create) and `DELETE /notes/<id>`
  (204 on success) on the same microdot app object, using the same real
  vendored peewee model. 404 for unknown or non-numeric ids, 400 for an
  invalid edit payload.
- `assistant_ext_test.py` - assistant-authored. 7 tests covering edit,
  delete, 404/400 mapping, persistence of edits and deletes across a
  simulated restart, and that storage is still the real vendored
  `peewee.Model`. These tests are SEPARATE from the fixed acceptance test
  (`acceptance_test.py`), which is unchanged and still governs the original
  4 behaviors. The new tests import `assistant_ext` directly, so they
  cannot pass without the extension.

Boundaries kept:

- The reviewed baseline files (`generated/app.py`, `test_fused.py`,
  `acceptance_test.py`) are byte-UNCHANGED from the private-save package
  (commit 3194bbb8). Verified by direct comparison.
- The unmodified AI originals in `original-ai/` remain the honest record of
  what the model produced; nothing here is presented as AI output.
- No new features beyond edit/delete. No model calls, no keys, no new
  vendored code.

Verified from this tree (Python 3.10): fixed acceptance 4/4 OK, repaired
model-written tests 7/7 OK, extension tests 7/7 OK.

Run:

    cd fused_app
    python3 -m unittest acceptance_test.py     # original fixed 4 tests
    python3 -m unittest assistant_ext_test.py  # new edit/delete 7 tests
