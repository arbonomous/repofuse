# ASSISTANT-AUTHORED EXTENSION (written by the assistant, offline, no model
# calls): adds the missing edit/delete behavior to the notes app.
#
# The reviewed assistant-repaired baseline in generated/app.py is byte-UNCHANGED;
# this module imports it and registers the two additional routes on the same
# microdot app object. Provenance: the original fixed goal was
# save/read/edit/delete; the baseline proved save/read only (see PROVENANCE.md).
# This module completes edit (PUT) and delete (DELETE). Nothing else is added.
from generated.app import (
    app, Note, DoesNotExist, HTTPException, json_response,
    validate_note_payload,
)
from microdot import Response


def _get_note_or_404(id):
    try:
        nid = int(id)
    except Exception:
        raise HTTPException(404, "not found")
    try:
        return Note.get_by_id(nid)
    except DoesNotExist:
        raise HTTPException(404, "not found")


@app.route("/notes/<id>", methods=["PUT"])
async def update_note(request, id):
    # edit: validate body the same way create does, then persist via peewee
    note = _get_note_or_404(id)
    note.text = validate_note_payload(request)
    note.save()
    return json_response({"id": note.id, "text": note.text})


@app.route("/notes/<id>", methods=["DELETE"])
async def delete_note(request, id):
    # delete: remove the row; 204 No Content on success
    note = _get_note_or_404(id)
    nid = note.id
    note.delete_instance()
    return Response("", status_code=204)
