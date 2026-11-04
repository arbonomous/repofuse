import json

"""The pinned qualification target: a persistent notes CRUD API fusing
microdot (interface, MIT) and peewee (ORM, MIT).

This contract is FIXED and written by RepoFuse's authors, not generated.
The acceptance test enforces it independently of anything the model emits.
"""

TARGET = {
    "name": "notes-api",
    "inputs": {
        "microdot": {
            "url": "https://github.com/miguelgrinberg/microdot",
            "commit": "7742db9ff9f49635de3387145fafe56bf2377a97",
            "license": "MIT",
        },
        "peewee": {
            "url": "https://github.com/coleifer/peewee",
            "commit": "e9b55c96b0c1e5c13c0053205868f188af617945",
            "license": "MIT",
        },
    },
    "contract": {
        "module": "generated/app.py",
        "app_object": "app",
        "app_type": "microdot.microdot.Microdot instance",
        "db_env": "FUSED_DB_PATH",
        "model": "Note(peewee.Model) with CharField text, bound to a "
                 "peewee.SqliteDatabase created from FUSED_DB_PATH",
        "routes": [
            "POST /notes with JSON {'text': str} -> 201 {'id': int}",
            "GET /notes -> [{'id': int, 'text': str}, ...]",
            "GET /notes/<id> -> {'id': int, 'text': str} or 404",
        ],
    },
}

ACCEPTANCE_TEST = '''"""FIXED independent acceptance test for the pinned qualification fusion.

Authored by RepoFuse, never generated. Decides whether the fused app
actually works: CRUD through the real microdot app object, persistence
through the real peewee ORM across a simulated restart, against a fresh
database file. Copied into fused_app/ at package time; the model cannot
write to it.
"""
import asyncio
import importlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vendor  # noqa: F401  activates the vendored-repo import shim

from microdot.test_client import TestClient  # vendored microdot
import peewee  # vendored peewee


def call(coro):
    return asyncio.run(coro)


class FusedNotesAcceptance(unittest.TestCase):
    DB = os.path.join(HERE, "acceptance_tmp.db")

    def setUp(self):
        if os.path.exists(self.DB):
            os.unlink(self.DB)
        os.environ["FUSED_DB_PATH"] = self.DB
        if "generated.app" in sys.modules:
            del sys.modules["generated.app"]
        self.mod = importlib.import_module("generated.app")
        self.client = TestClient(self.mod.app)

    def tearDown(self):
        if os.path.exists(self.DB):
            os.unlink(self.DB)

    def test_01_create_and_read_through_real_microdot(self):
        res = call(self.client.post(
            "/notes", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "hello fusion"})))
        self.assertEqual(res.status_code, 201, res.text)
        note_id = res.json["id"]
        res = call(self.client.get("/notes"))
        self.assertEqual(res.status_code, 200)
        texts = [n["text"] for n in res.json]
        self.assertIn("hello fusion", texts)
        res = call(self.client.get(f"/notes/{note_id}"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["text"], "hello fusion")

    def test_02_persistence_across_restart_via_peewee(self):
        res = call(self.client.post(
            "/notes", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "survives restart"})))
        self.assertEqual(res.status_code, 201, res.text)
        # simulate restart: drop module, reload against same db file
        del sys.modules["generated.app"]
        self.mod = importlib.import_module("generated.app")
        client = TestClient(self.mod.app)
        res = call(client.get("/notes"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("survives restart", [n["text"] for n in res.json])

    def test_03_storage_is_real_peewee_model(self):
        note_cls = getattr(self.mod, "Note", None)
        self.assertIsNotNone(note_cls, "generated.app must expose Note")
        self.assertTrue(issubclass(note_cls, peewee.Model),
                        "Note must be a real vendored peewee.Model")
        self.assertIsInstance(note_cls._meta.database,
                              peewee.SqliteDatabase)

    def test_04_unknown_note_is_404(self):
        res = call(self.client.get("/notes/99999"))
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
'''


def contract_prompt_fragment():
    return ("The fused app MUST satisfy this FIXED contract: "
            + json.dumps(TARGET["contract"], indent=2)
            + "\nAn independent acceptance test you do not control will "
              "exercise these behaviors through the real microdot TestClient "
              "and the real peewee ORM. Write generated/app.py accordingly.")
