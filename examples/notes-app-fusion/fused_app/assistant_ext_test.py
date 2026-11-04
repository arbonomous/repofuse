# ASSISTANT-AUTHORED EXTENSION TESTS (offline, no model calls).
# These tests are SEPARATE from the fixed RepoFuse-authored acceptance test
# (acceptance_test.py), which is unchanged and still governs the baseline
# create/list/read/404/restart behavior. These cover ONLY the added
# edit/delete routes in assistant_ext.py. They import the extension module
# directly, so they cannot pass without it.
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


class NotesEditDeleteAcceptance(unittest.TestCase):
    DB = os.path.join(HERE, "ext_acceptance_tmp.db")

    def setUp(self):
        if os.path.exists(self.DB):
            os.unlink(self.DB)
        os.environ["FUSED_DB_PATH"] = self.DB
        for mod in ("assistant_ext", "generated.app"):
            if mod in sys.modules:
                del sys.modules[mod]
        importlib.import_module("generated.app")
        self.ext = importlib.import_module("assistant_ext")
        self.client = TestClient(self.ext.app)

    def tearDown(self):
        if os.path.exists(self.DB):
            os.unlink(self.DB)

    def _create(self, text):
        res = call(self.client.post(
            "/notes", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": text})))
        self.assertEqual(res.status_code, 201, res.text)
        return res.json["id"]

    def test_01_edit_updates_text_through_real_microdot(self):
        nid = self._create("before edit")
        res = call(self.client.put(
            f"/notes/{nid}", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "after edit"})))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json, {"id": nid, "text": "after edit"})
        res = call(self.client.get(f"/notes/{nid}"))
        self.assertEqual(res.json["text"], "after edit")

    def test_02_edit_unknown_or_bad_id_is_404(self):
        res = call(self.client.put(
            "/notes/99999", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "x"})))
        self.assertEqual(res.status_code, 404)
        res = call(self.client.put(
            "/notes/abc", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "x"})))
        self.assertEqual(res.status_code, 404)

    def test_03_edit_rejects_invalid_payload_400(self):
        nid = self._create("keep me")
        for bad in ({}, {"text": ""}, {"text": 5}):
            res = call(self.client.put(
                f"/notes/{nid}", headers={"Content-Type": "application/json"},
                body=json.dumps(bad)))
            self.assertEqual(res.status_code, 400, res.text)
        res = call(self.client.get(f"/notes/{nid}"))
        self.assertEqual(res.json["text"], "keep me")  # unchanged

    def test_04_delete_removes_note(self):
        nid = self._create("delete me")
        res = call(self.client.delete(f"/notes/{nid}"))
        self.assertEqual(res.status_code, 204, res.text)
        res = call(self.client.get(f"/notes/{nid}"))
        self.assertEqual(res.status_code, 404)
        res = call(self.client.get("/notes"))
        self.assertNotIn(nid, [n["id"] for n in res.json])

    def test_05_delete_unknown_or_bad_id_is_404(self):
        res = call(self.client.delete("/notes/99999"))
        self.assertEqual(res.status_code, 404)
        res = call(self.client.delete("/notes/abc"))
        self.assertEqual(res.status_code, 404)

    def test_06_edit_and_delete_persist_across_restart(self):
        nid = self._create("original")
        call(self.client.put(
            f"/notes/{nid}", headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "edited before restart"})))
        gone = self._create("deleted before restart")
        call(self.client.delete(f"/notes/{gone}"))
        # simulate restart: drop modules, reload against the same db file
        for mod in ("assistant_ext", "generated.app"):
            del sys.modules[mod]
        importlib.import_module("generated.app")
        ext = importlib.import_module("assistant_ext")
        client = TestClient(ext.app)
        res = call(client.get(f"/notes/{nid}"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["text"], "edited before restart")
        res = call(client.get(f"/notes/{gone}"))
        self.assertEqual(res.status_code, 404)

    def test_07_storage_still_real_peewee_model(self):
        import generated.app as fused
        self.assertTrue(issubclass(fused.Note, peewee.Model))
        self.assertIsInstance(fused.Note._meta.database,
                              peewee.SqliteDatabase)


if __name__ == "__main__":
    unittest.main()
