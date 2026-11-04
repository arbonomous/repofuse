from microdot import Microdot, Response
from peewee import Model, CharField, BooleanField, SqliteDatabase

app = Microdot()
db = SqliteDatabase(None)

class Note(Model):
    title = CharField()
    content = CharField()
    pinned = BooleanField()
    class Meta:
        database = db

MODELS = [Note]

def to_dict(n):
    return {"id": n.id, "title": n.title, "content": n.content, "pinned": n.pinned}

@app.post("/notes")
async def create_note(request):
    data = request.json or {}
    n = Note.create(title=data.get("title", ""), content=data.get("content", ""), pinned=bool(data.get("pinned", False)))
    return (to_dict(n), 201)

@app.get("/notes")
async def list_notes(request):
    return ([to_dict(n) for n in Note.select()], 200)

@app.get("/notes/<int:note_id>")
async def read_note(request, note_id):
    n = Note.get_or_none(Note.id == note_id)
    if n is None:
        return ({"error": "not found"}, 404)
    return (to_dict(n), 200)

@app.put("/notes/<int:note_id>")
async def update_note(request, note_id):
    n = Note.get_or_none(Note.id == note_id)
    if n is None:
        return ({"error": "not found"}, 404)
    data = request.json or {}
    if "title" in data:
        n.title = data["title"]
    if "content" in data:
        n.content = data["content"]
    if "pinned" in data:
        n.pinned = bool(data["pinned"])
    n.save()
    return (to_dict(n), 200)

@app.delete("/notes/<int:note_id>")
async def delete_note(request, note_id):
    n = Note.get_or_none(Note.id == note_id)
    if n is None:
        return ({"error": "not found"}, 404)
    n.delete_instance()
    return ("", 204)
