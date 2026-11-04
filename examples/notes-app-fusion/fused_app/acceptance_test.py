"""FIXED independent acceptance test for the pinned qualification fusion.

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
