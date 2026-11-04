# HAND-WRITTEN REFERENCE GLUE (author: RepoFuse builder agent, 2026-11-03).
# NOT model-generated. Exists to prove the qualification harness can judge a
# real fusion; the actual run replaces this with gated model output.
import os
import vendor  # noqa: F401  activates vendored microdot/peewee

import peewee
from microdot import Microdot

db = peewee.SqliteDatabase(os.environ.get("FUSED_DB_PATH", "notes.db"))


class Base(peewee.Model):
    class Meta:
        database = db


class Note(Base):
    text = peewee.CharField()


db.connect(reuse_if_open=True)
db.create_tables([Note])

app = Microdot()


@app.post("/notes")
def create_note(request):
    note = Note.create(text=request.json["text"])
    return {"id": note.id}, 201


@app.get("/notes")
def list_notes(request):
    return [{"id": n.id, "text": n.text} for n in Note.select()]


@app.get("/notes/<note_id>")
def get_note(request, note_id):
    note = Note.get_or_none(Note.id == int(note_id))
    if note is None:
        return {"error": "not found"}, 404
    return {"id": note.id, "text": note.text}
