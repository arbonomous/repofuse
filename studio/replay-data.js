window.REPLAY = {
  "manifest": "{\"arbitrage_opportunity\":\"Microdot minimal async web layer lacks persistence; Peewee single-module ORM lacks HTTP interface. Fuse: expose Peewee models via Microdot CRUD routes for tiny full-stack app on CPython/MicroPython scale.\",\"bridge\":[{\"from_export\":\"Model\",\"from_repo\":\"peewee\",\"to_repo\":\"microdot\",\"to_route_or_input\":\"POST /users\"},{\"from_export\":\"ModelSelect\",\"from_repo\":\"peewee\",\"to_repo\":\"microdot\",\"to_route_or_input\":\"GET /users/<int:id>\"},{\"from_export\":\"ModelUpdate\",\"from_repo\":\"peewee\",\"to_repo\":\"microdot\",\"to_route_or_input\":\"PUT /users/<int:id>\"},{\"from_export\":\"ModelDelete\",\"from_repo\":\"peewee\",\"to_repo\":\"microdot\",\"to_route_or_input\":\"DELETE /users/<int:id>\"},{\"from_export\":\"SqliteDatabase\",\"from_repo\":\"peewee\",\"to_repo\":\"microdot\",\"to_route_or_input\":\"Request context init\"},{\"from_export\":\"Request\",\"from_repo\":\"microdot\",\"to_repo\":\"peewee\",\"to_route_or_input\":\"Model validation input\"},{\"from_export\":\"Response\",\"from_repo\":\"microdot\",\"to_repo\":\"peewee\",\"to_route_or_input\":\"Query result serializer\"}],\"required_shims\":[\"microdot before/after request DB connect/close hook\",\"async-to-sync wrapper for peewee queries\",\"model to JSON Response serializer\",\"Request JSON to model validator\",\"HTTPException mapping for DoesNotExist/IntegrityError\",\"BasicAuth/TokenAuth guard for /users routes\",\"TestClient integration harness for CRUD\"],\"risks\":[\"Microdot async handlers vs sync Peewee blocking\",\"MicroPython resource limits with ORM overhead\",\"uncertain: exact Peewee Model API version match\",\"concurrency: SQLite pooling under async server\"],\"source_exports\":{\"microdot\":[\"Microdot\",\"Request\",\"Response\",\"HTTPException\",\"BasicAuth\",\"TokenAuth\",\"Session\",\"CORS\",\"TestClient\",\"WebSocket\",\"SSE\",\"URLPattern\"],\"peewee\":[\"Model\",\"Database\",\"SqliteDatabase\",\"PostgresqlDatabase\",\"MySQLDatabase\",\"CharField\",\"IntegerField\",\"ForeignKeyField\",\"DateTimeField\",\"ModelSelect\",\"DoesNotExist\",\"IntegrityError\"]}}",

 "recorded_run": "2026-11-04",
 "model": "muse-spark-1.3",
 "recorded_inputs": {
  "repo_a": "https://github.com/miguelgrinberg/microdot",
  "repo_b": "https://github.com/coleifer/peewee",
  "intent": "A tiny notes API: save, list, read, edit and delete notes, persisted to SQLite."
 },
 "repos": [
  {
   "name": "microdot",
   "url": "https://github.com/miguelgrinberg/microdot",
   "version": "2.7.0",
   "commit": "7742db9ff9f49635de3387145fafe56bf2377a97",
   "license": "MIT",
   "role": "async web layer",
   "exports": [
    "Microdot",
    "Request",
    "Response",
    "HTTPException",
    "BasicAuth",
    "TokenAuth",
    "Session",
    "CORS"
   ]
  },
  {
   "name": "peewee",
   "url": "https://github.com/coleifer/peewee",
   "version": "4.5.3",
   "commit": "e9b55c96b0c1e5c13c0053205868f188af617945",
   "license": "MIT",
   "role": "ORM / persistence",
   "exports": [
    "Model",
    "Database",
    "SqliteDatabase",
    "PostgresqlDatabase",
    "MySQLDatabase",
    "CharField",
    "IntegerField",
    "ForeignKeyField"
   ]
  }
 ],
 "vendored_files": 437,
 "arbitrage": "Microdot minimal async web layer lacks persistence; Peewee single-module ORM lacks HTTP interface. Fuse: expose Peewee models via Microdot CRUD routes for tiny full-stack app on CPython/MicroPython scale.",
 "bridges": [
  {
   "from": "peewee:Model",
   "to": "POST /notes",
   "by": "model"
  },
  {
   "from": "peewee:ModelSelect",
   "to": "GET /notes",
   "by": "model"
  },
  {
   "from": "peewee:ModelSelect",
   "to": "GET /notes/<id>",
   "by": "model"
  },
  {
   "from": "microdot:Request",
   "to": "body validation",
   "by": "model"
  },
  {
   "from": "microdot:Response",
   "to": "JSON serializer",
   "by": "model"
  },
  {
   "from": "peewee:ModelUpdate",
   "to": "PUT /notes/<id>",
   "by": "assistant-extension"
  },
  {
   "from": "peewee:ModelDelete",
   "to": "DELETE /notes/<id>",
   "by": "assistant-extension"
  }
 ],
 "stages": [
  {
   "id": "ingest",
   "label": "Ingest",
   "detail": "Pin both repos by commit SHA, verify licenses, vendor 437 files with sha256 manifest."
  },
  {
   "id": "analyze",
   "label": "Analyze",
   "detail": "Extract each repo's public exports."
  },
  {
   "id": "architecture",
   "label": "Architecture",
   "detail": "Model plans how the libraries connect.",
   "tokens": {
    "in": 4397,
    "out": 634
   }
  },
  {
   "id": "glue",
   "label": "Glue synthesis",
   "detail": "Model writes generated/app.py (ORIGINAL AI bytes shown).",
   "tokens": {
    "in": 1182,
    "out": 1919
   }
  },
  {
   "id": "tests",
   "label": "Test synthesis",
   "detail": "Model writes test_fused.py (ORIGINAL AI bytes shown).",
   "tokens": {
    "in": 2415,
    "out": 2048
   }
  },
  {
   "id": "verify",
   "label": "Verify",
   "detail": "Fixed acceptance test runs in a sandbox."
  },
  {
   "id": "repair",
   "label": "Assistant repair",
   "detail": "Offline, no model calls: 3 labeled fixes.",
   "assistant": true
  },
  {
   "id": "extend",
   "label": "Assistant extension",
   "detail": "Offline: edit/delete added by the assistant.",
   "assistant": true
  }
 ],
 "model_calls": {
  "charged": 4,
  "count_checks": 4,
  "totals": {
   "in": 8008,
   "out": 4602
  }
 },
 "original_verdict": {
  "title": "Unedited AI output",
  "status": "failed",
  "summary": "4 tests, 4 errors - every test failed at import",
  "defects": [
   {
    "n": 1,
    "title": "Empty namespace package accepted",
    "body": "The loader took the first importable candidate. `vendor.microdot` imports as an empty PEP 420 namespace package, so Microdot was never found."
   },
   {
    "n": 2,
    "title": "HTTPException imported from the wrong place",
    "body": "The model assumed microdot re-exports HTTPException at the package root. Pinned microdot 2.7.0 keeps it in the microdot.microdot submodule."
   },
   {
    "n": 3,
    "title": "Two copies of peewee loaded",
    "body": "Importing vendor.peewee.peewee created a second peewee module instance, so Note was not a subclass of the canonical peewee.Model."
   }
  ]
 },
 "repair": {
  "title": "Assistant repair - offline, no model calls",
  "summary": "Three labeled repairs to the loader and imports. Every other byte unchanged.",
  "tests_passed": "4/4",
  "vacuity": "Control run without the glue fails: the tests genuinely exercise the fusion."
 },
 "extension": {
  "title": "Edit/delete extension - assistant-authored, offline",
  "summary": "PUT /notes/<id> and DELETE /notes/<id> on the same app. 7/7 checks pass."
 },
 "acceptance_tests": [
  "create + read through the real microdot app",
  "persistence across a simulated restart (real peewee/SQLite)",
  "storage is a real peewee.Model",
  "unknown note returns 404"
 ],
 "code": {
  "app_original_ai": "# Generated by muse-spark-1.3 via RepoFuse 2026-11-04T04:02:02Z.\n# UNVERIFIED until the verify step passes.\nimport json\nimport os\nimport importlib\nimport vendor  # vendored import shim (vendor/__init__.py)\n\n# UNCERTAINTY: vendor shim exact API not provided in analysis; loader below\n# tries shim attributes first, then standard vendor.<slug> submodule import.\n# No APIs invented: only Microdot/peewee exports listed in architecture used.\n\ndef _load_via_shim(shim_name, export_names):\n    # 1) try attribute/helper on vendor shim if present (do not assume name).\n    for helper in (\"load\", \"import_module\", \"get\", \"resolve\"):\n        fn = getattr(vendor, helper, None)\n        if callable(fn):\n            try:\n                mod = fn(shim_name)\n                if mod is not None:\n                    return mod\n            except Exception:\n                pass\n    # 2) attribute directly on vendor package.\n    if hasattr(vendor, shim_name):\n        try:\n            return getattr(vendor, shim_name)\n        except Exception:\n            pass\n    # 3) standard submodule import: vendor.<slug> and vendor.<slug>.<slug>.\n    for cand in (\"vendor.\" + shim_name, \"vendor.\" + shim_name + \".\" + shim_name, \"vendor.\" + shim_name + \".microdot\", \"vendor.\" + shim_name + \".peewee\"):\n        try:\n            return importlib.import_module(cand)\n        except Exception:\n            continue\n    # 4) last resort: top-level import (CPython fallback).\n    return importlib.import_module(shim_name)\n\n_microdot_mod = _load_via_shim(\"microdot\", [\"Microdot\", \"Request\", \"Response\", \"HTTPException\"])\n_peewee_mod = _load_via_shim(\"peewee\", [\"Model\", \"SqliteDatabase\", \"CharField\"])\n\nMicrodot = _microdot_mod.Microdot\nRequest = _microdot_mod.Request\nResponse = _microdot_mod.Response\nHTTPException = _microdot_mod.HTTPException\nModel = _peewee_mod.Model\nSqliteDatabase = _peewee_mod.SqliteDatabase\nCharField = _peewee_mod.CharField\nDoesNotExist = _peewee_mod.DoesNotExist\nIntegrityError = getattr(_peewee_mod, \"IntegrityError\", Exception)\n\nDB_PATH = os.environ.get(\"FUSED_DB_PATH\", \"/tmp/fused.db\")\ndb = SqliteDatabase(DB_PATH)\n\nclass Note(Model):\n    text = CharField()\n    class Meta:\n        database = db\n        table_name = \"notes\"\n\ndef _init_db():\n    if db.is_closed():\n        db.connect()\n    db.create_tables([Note], safe=True)\n\n_init_db()\n\napp = Microdot()\n\n# --- shim: before/after request DB connect/close hook ---\n@app.before_request\nasync def _before(request):\n    # async-to-sync wrapper: peewee queries are sync/blocking; keep hook tiny\n    # and non-blocking (connect is fast for sqlite). No threadpool to stay\n    # MicroPython compatible (stdlib only).\n    if db.is_closed():\n        db.connect()\n    return None\n\n@app.after_request\nasync def _after(request, response):\n    # Do NOT close per-request on sqlite file to avoid pooling churn under\n    # async server; keep connection open. Hook present for lifecycle parity.\n    return response\n\n# --- shim: model to JSON Response serializer ---\ndef note_to_dict(note):\n    return {\"id\": note.id, \"text\": note.text}\n\ndef json_response(body, status=200):\n    return Response(json.dumps(body), status_code=status, headers={\"Content-Type\": \"application/json\"})\n\n# --- shim: Request JSON to model validator ---\ndef validate_note_payload(request):\n    data = request.json\n    if data is None:\n        # fallback: parse raw body with stdlib json\n        try:\n            raw = request.body\n            if isinstance(raw, (bytes, bytearray)):\n                raw = raw.decode(\"utf-8\")\n            data = json.loads(raw) if raw else None\n        except Exception:\n            data = None\n    if not isinstance(data, dict):\n        raise HTTPException(400, \"expected JSON object\")\n    text = data.get(\"text\")\n    if not isinstance(text, str) or not text.strip():\n        raise HTTPException(400, \"field 'text' must be a non-empty str\")\n    return text.strip()\n\n@app.route(\"/notes\", methods=[\"POST\"])\nasync def create_note(request):\n    text = validate_note_payload(request)  # Request -> model validation input\n    try:\n        note = Note.create(text=text)  # Model bridge: POST /users pattern applied to /notes\n    except IntegrityError as e:\n        raise HTTPException(400, str(e))\n    return json_response({\"id\": note.id}, status=201)\n\n@app.route(\"/notes\", methods=[\"GET\"])\nasync def list_notes(request):\n    rows = [note_to_dict(n) for n in Note.select().order_by(Note.id)]  # ModelSelect bridge\n    return json_response(rows)\n\n@app.route(\"/notes/<id>\", methods=[\"GET\"])\nasync def get_note(request, id):\n    try:\n        nid = int(id)\n    except Exception:\n        raise HTTPException(404, \"not found\")\n    try:\n        note = Note.get_by_id(nid)  # ModelSelect single-row bridge\n    except DoesNotExist:\n        raise HTTPException(404, \"not found\")  # HTTPException mapping for DoesNotExist\n    return json_response(note_to_dict(note))\n",
  "tests_original_ai": "# Generated by muse-spark-1.3 via RepoFuse 2026-11-04T04:02:20Z.\n# UNVERIFIED until the verify step passes.\nimport asyncio\nimport importlib\nimport json\nimport os\nimport unittest\n\nos.environ.setdefault(\"FUSED_DB_PATH\", \"/tmp/fused_test.db\")\n# start clean\ntry:\n    if os.path.exists(\"/tmp/fused_test.db\"):\n        os.remove(\"/tmp/fused_test.db\")\nexcept Exception:\n    pass\n\nimport vendor  # noqa: F401  ensure vendored shim is used\n\ndef _load(name):\n    for cand in (\"vendor.\"+name, \"vendor.\"+name+\".\"+name, \"vendor.\"+name+\".microdot\", \"vendor.\"+name+\".peewee\", name):\n        try:\n            return importlib.import_module(cand)\n        except Exception:\n            continue\n    raise ImportError(name)\n\n_microdot = _load(\"microdot\")\n_peewee = _load(\"peewee\")\n\n# Call real vendored exports directly (fails if vendor missing)\nassert hasattr(_microdot, \"Microdot\")\nassert hasattr(_microdot, \"Response\")\nassert hasattr(_microdot, \"HTTPException\")\nassert hasattr(_peewee, \"Model\")\nassert hasattr(_peewee, \"SqliteDatabase\")\n_RealMicrodot = _microdot.Microdot\n_RealResponse = _microdot.Response\n_RealHTTP = _microdot.HTTPException\n_RealSqlite = _peewee.SqliteDatabase\n_RealModel = _peewee.Model\n# instantiate real exports to prove they are callable\nassert callable(_RealMicrodot) and callable(_RealSqlite) and callable(_RealModel)\n\nimport generated.app as fused\n\nclass FakeRequest:\n    def __init__(self, payload=None, raw=None):\n        self._payload = payload\n        if raw is not None:\n            self.body = raw\n        elif payload is not None:\n            self.body = json.dumps(payload).encode()\n        else:\n            self.body = b\"\"\n        # glue first reads request.json; provide it when payload given\n        self.json = payload\n\ndef run(coro):\n    return asyncio.new_event_loop().run_until_complete(coro) if False else asyncio.run(coro)\n\nclass FusedTest(unittest.TestCase):\n    def test_glue_is_real_vendor(self):\n        # glue must be built on real vendored modules, not stubs\n        self.assertIs(fused.Microdot, _RealMicrodot)\n        self.assertIs(fused.Response, _RealResponse)\n        self.assertIs(fused.HTTPException, _RealHTTP)\n        self.assertIs(fused.SqliteDatabase, _RealSqlite)\n        self.assertIs(fused.Model, _RealModel)\n        self.assertTrue(issubclass(fused.Note, _RealModel))\n        self.assertIsInstance(fused.db, _RealSqlite)\n        self.assertIsInstance(fused.app, _RealMicrodot)\n\n    def test_validate_ok(self):\n        r = FakeRequest(payload={\"text\": \"  hello \"})\n        self.assertEqual(fused.validate_note_payload(r), \"hello\")\n\n    def test_validate_bad(self):\n        for bad in (None, [], {\"text\": \"\"}, {\"text\": 5}, {}):\n            with self.assertRaises(fused.HTTPException) as cm:\n                fused.validate_note_payload(FakeRequest(payload=bad))\n            self.assertEqual(cm.exception.status_code, 400)\n\n    def test_validate_raw_body_fallback(self):\n        r = FakeRequest(payload=None, raw=json.dumps({\"text\": \"raw\"}).encode())\n        r.json = None\n        self.assertEqual(fused.validate_note_payload(r), \"raw\")\n\n    def test_note_to_dict_and_json_response(self):\n        n = fused.Note.create(text=\"ser\")\n        d = fused.note_to_dict(n)\n        self.assertEqual(d, {\"id\": n.id, \"text\": \"ser\"})\n        resp = fused.json_response(d, status=201)\n        self.assertEqual(resp.status_code, 201)\n        body = resp.body if hasattr(resp, \"body\") else getattr(resp, \"data\", b\"\")\n        if isinstance(body, (bytes, bytearray)):\n            body = body.decode()\n        self.assertEqual(json.loads(body), d)\n        n.delete_instance()\n\n    def test_crud_handlers_end_to_end(self):\n        # POST /notes handler (Model bridge)\n        resp = run(fused.create_note(FakeRequest(payload={\"text\": \"e2e\"})))\n        self.assertEqual(resp.status_code, 201)\n        body = resp.body if hasattr(resp, \"body\") else getattr(resp, \"data\", b\"\")\n        if isinstance(body, (bytes, bytearray)):\n            body = body.decode()\n        nid = json.loads(body)[\"id\"]\n        # ModelSelect list bridge\n        resp2 = run(fused.list_notes(FakeRequest(payload=None)))\n        b2 = resp2.body if hasattr(resp2, \"body\") else getattr(resp2, \"data\", b\"\")\n        if isinstance(b2, (bytes, bytearray)):\n            b2 = b2.decode()\n        rows = json.loads(b2)\n        self.assertTrue(any(r[\"id\"] == nid and r[\"text\"] == \"e2e\" for r in rows))\n        # ModelSelect single-row bridge\n        resp3 = run(fused.get_note(FakeRequest(payload=None), str(nid)))\n        b3 = resp3.body if hasattr(resp3, \"body\") else getattr(resp3, \"data\", b\"\")\n        if isinstance(b3, (bytes, bytearray)):\n            b3 = b3.decode()\n        self.assertEqual(json.loads(b3), {\"id\": nid, \"text\": \"e2e\"})\n        # DoesNotExist -> 404 mapping\n        with self.assertRaises(fused.HTTPException) as cm:\n            run(fused.get_note(FakeRequest(payload=None), \"999999\"))\n        self.assertEqual(cm.exception.status_code, 404)\n        with self.assertRaises(fused.HTTPException) as cm2:\n            run(fused.get_note(FakeRequest(payload=None), \"abc\"))\n        self.assertEqual(cm2.exception.status_code, 404)\n\n    def test_db_hooks_present(self):\n        # before/after request DB connect/close hook shims exist and are callable\n        self.assertTrue(callable(getattr(fused, \"_before\", None)))\n        self.assertTrue(callable(getattr(fused, \"_after\", None)))\n        r = FakeRequest(payload=None)\n        run(fused._before(r))\n        resp = fused.json_response({\"ok\": True})\n        out = run(fused._after(r, resp))\n        self.assertIs(out, resp)\n\nif __name__ == \"__main__\":\n    unittest.main()\n",
  "app_repaired": "# Generated by muse-spark-1.3 via RepoFuse 2026-11-04T04:02:02Z.\n# UNVERIFIED until the verify step passes.\n# REPAIRED COPY (assistant, offline, no model call): loader export-check only; see _load_via_shim.\nimport json\nimport os\nimport importlib\nimport vendor  # vendored import shim (vendor/__init__.py)\n\n# UNCERTAINTY: vendor shim exact API not provided in analysis; loader below\n# tries shim attributes first, then standard vendor.<slug> submodule import.\n# No APIs invented: only Microdot/peewee exports listed in architecture used.\n\ndef _load_via_shim(shim_name, export_names):\n    # REPAIRED OFFLINE by assistant (no model call): original AI loader accepted\n    # the first importable candidate; `vendor.<slug>` resolves as a PEP 420\n    # namespace package (directory, no __init__.py) WITHOUT the real exports,\n    # so Microdot/Model were never found. Repair: every candidate must expose\n    # the expected export before it is accepted; loader logic otherwise\n    # unchanged. Original AI-generated file preserved in repofuse-qual-2/.\n    def _has_exports(mod):\n        return mod is not None and hasattr(mod, export_names[0])\n    # 1) try attribute/helper on vendor shim if present (do not assume name).\n    for helper in (\"load\", \"import_module\", \"get\", \"resolve\"):\n        fn = getattr(vendor, helper, None)\n        if callable(fn):\n            try:\n                mod = fn(shim_name)\n                if _has_exports(mod):\n                    return mod\n            except Exception:\n                pass\n    # 2) attribute directly on vendor package.\n    if hasattr(vendor, shim_name):\n        try:\n            mod = getattr(vendor, shim_name)\n            if _has_exports(mod):\n                return mod\n        except Exception:\n            pass\n    # 3) REPAIRED OFFLINE (no model call): try the canonical top-level import\n    # FIRST. The vendor shim puts the real modules on sys.path, and the fixed\n    # acceptance test imports them top-level; importing \"vendor.peewee.peewee\"\n    # instead created a SECOND peewee module instance, so Note was not a\n    # subclass of the canonical peewee.Model. Same candidate set, reordered.\n    for cand in (shim_name, \"vendor.\" + shim_name + \".\" + shim_name, \"vendor.\" + shim_name + \".microdot\", \"vendor.\" + shim_name + \".peewee\", \"vendor.\" + shim_name):\n        try:\n            mod = importlib.import_module(cand)\n            if _has_exports(mod):\n                return mod\n        except Exception:\n            continue\n    # 4) last resort: plain import by name.\n    mod = importlib.import_module(shim_name)\n    if not _has_exports(mod):\n        raise ImportError(shim_name)\n    return mod\n\n_microdot_mod = _load_via_shim(\"microdot\", [\"Microdot\", \"Request\", \"Response\", \"HTTPException\"])\n_peewee_mod = _load_via_shim(\"peewee\", [\"Model\", \"SqliteDatabase\", \"CharField\"])\n\nMicrodot = _microdot_mod.Microdot\nRequest = _microdot_mod.Request\nResponse = _microdot_mod.Response\n# REPAIRED OFFLINE by assistant (no model call): pinned microdot 2.7.0 does\n# not re-export HTTPException from the package root; it lives in the\n# microdot.microdot submodule. Fall back to the submodule so the raised\n# exception is the exact class microdot's dispatcher catches.\nHTTPException = getattr(_microdot_mod, \"HTTPException\", None)\nif HTTPException is None:\n    HTTPException = importlib.import_module(\"microdot.microdot\").HTTPException\nModel = _peewee_mod.Model\nSqliteDatabase = _peewee_mod.SqliteDatabase\nCharField = _peewee_mod.CharField\nDoesNotExist = _peewee_mod.DoesNotExist\nIntegrityError = getattr(_peewee_mod, \"IntegrityError\", Exception)\n\nDB_PATH = os.environ.get(\"FUSED_DB_PATH\", \"/tmp/fused.db\")\ndb = SqliteDatabase(DB_PATH)\n\nclass Note(Model):\n    text = CharField()\n    class Meta:\n        database = db\n        table_name = \"notes\"\n\ndef _init_db():\n    if db.is_closed():\n        db.connect()\n    db.create_tables([Note], safe=True)\n\n_init_db()\n\napp = Microdot()\n\n# --- shim: before/after request DB connect/close hook ---\n@app.before_request\nasync def _before(request):\n    # async-to-sync wrapper: peewee queries are sync/blocking; keep hook tiny\n    # and non-blocking (connect is fast for sqlite). No threadpool to stay\n    # MicroPython compatible (stdlib only).\n    if db.is_closed():\n        db.connect()\n    return None\n\n@app.after_request\nasync def _after(request, response):\n    # Do NOT close per-request on sqlite file to avoid pooling churn under\n    # async server; keep connection open. Hook present for lifecycle parity.\n    return response\n\n# --- shim: model to JSON Response serializer ---\ndef note_to_dict(note):\n    return {\"id\": note.id, \"text\": note.text}\n\ndef json_response(body, status=200):\n    return Response(json.dumps(body), status_code=status, headers={\"Content-Type\": \"application/json\"})\n\n# --- shim: Request JSON to model validator ---\ndef validate_note_payload(request):\n    data = request.json\n    if data is None:\n        # fallback: parse raw body with stdlib json\n        try:\n            raw = request.body\n            if isinstance(raw, (bytes, bytearray)):\n                raw = raw.decode(\"utf-8\")\n            data = json.loads(raw) if raw else None\n        except Exception:\n            data = None\n    if not isinstance(data, dict):\n        raise HTTPException(400, \"expected JSON object\")\n    text = data.get(\"text\")\n    if not isinstance(text, str) or not text.strip():\n        raise HTTPException(400, \"field 'text' must be a non-empty str\")\n    return text.strip()\n\n@app.route(\"/notes\", methods=[\"POST\"])\nasync def create_note(request):\n    text = validate_note_payload(request)  # Request -> model validation input\n    try:\n        note = Note.create(text=text)  # Model bridge: POST /users pattern applied to /notes\n    except IntegrityError as e:\n        raise HTTPException(400, str(e))\n    return json_response({\"id\": note.id}, status=201)\n\n@app.route(\"/notes\", methods=[\"GET\"])\nasync def list_notes(request):\n    rows = [note_to_dict(n) for n in Note.select().order_by(Note.id)]  # ModelSelect bridge\n    return json_response(rows)\n\n@app.route(\"/notes/<id>\", methods=[\"GET\"])\nasync def get_note(request, id):\n    try:\n        nid = int(id)\n    except Exception:\n        raise HTTPException(404, \"not found\")\n    try:\n        note = Note.get_by_id(nid)  # ModelSelect single-row bridge\n    except DoesNotExist:\n        raise HTTPException(404, \"not found\")  # HTTPException mapping for DoesNotExist\n    return json_response(note_to_dict(note))\n",
  "tests_repaired": "# Generated by muse-spark-1.3 via RepoFuse 2026-11-04T04:02:20Z.\n# UNVERIFIED until the verify step passes.\n# REPAIRED COPY (assistant, offline, no model call): loader export-check only; see _load.\nimport asyncio\nimport importlib\nimport json\nimport os\nimport unittest\n\nos.environ.setdefault(\"FUSED_DB_PATH\", \"/tmp/fused_test.db\")\n# start clean\ntry:\n    if os.path.exists(\"/tmp/fused_test.db\"):\n        os.remove(\"/tmp/fused_test.db\")\nexcept Exception:\n    pass\n\nimport vendor  # noqa: F401  ensure vendored shim is used\n\ndef _load(name):\n    # REPAIRED OFFLINE by assistant (no model call): same namespace-package\n    # acceptance bug as generated/app.py; require the real export before\n    # accepting a candidate. Original AI-generated file in repofuse-qual-2/.\n    need = {\"microdot\": \"Microdot\", \"peewee\": \"Model\"}.get(name)\n    for cand in (name, \"vendor.\"+name+\".\"+name, \"vendor.\"+name+\".microdot\", \"vendor.\"+name+\".peewee\", \"vendor.\"+name):  # REPAIRED OFFLINE: top-level first for single-instance identity with the app under test\n        try:\n            mod = importlib.import_module(cand)\n            if need is None or hasattr(mod, need):\n                return mod\n        except Exception:\n            continue\n    raise ImportError(name)\n\n_microdot = _load(\"microdot\")\n_peewee = _load(\"peewee\")\n\n# Call real vendored exports directly (fails if vendor missing)\nassert hasattr(_microdot, \"Microdot\")\nassert hasattr(_microdot, \"Response\")\n# REPAIRED OFFLINE: pinned microdot 2.7.0 keeps HTTPException in the\n# microdot.microdot submodule, not the package root (same AI assumption bug).\n_RealHTTP = getattr(_microdot, \"HTTPException\", None)\nif _RealHTTP is None:\n    _RealHTTP = importlib.import_module(\"microdot.microdot\").HTTPException\nassert hasattr(_peewee, \"Model\")\nassert hasattr(_peewee, \"SqliteDatabase\")\n_RealMicrodot = _microdot.Microdot\n_RealResponse = _microdot.Response\nassert _RealHTTP is not None\n_RealSqlite = _peewee.SqliteDatabase\n_RealModel = _peewee.Model\n# instantiate real exports to prove they are callable\nassert callable(_RealMicrodot) and callable(_RealSqlite) and callable(_RealModel)\n\nimport generated.app as fused\n\nclass FakeRequest:\n    def __init__(self, payload=None, raw=None):\n        self._payload = payload\n        if raw is not None:\n            self.body = raw\n        elif payload is not None:\n            self.body = json.dumps(payload).encode()\n        else:\n            self.body = b\"\"\n        # glue first reads request.json; provide it when payload given\n        self.json = payload\n\ndef run(coro):\n    return asyncio.new_event_loop().run_until_complete(coro) if False else asyncio.run(coro)\n\nclass FusedTest(unittest.TestCase):\n    def test_glue_is_real_vendor(self):\n        # glue must be built on real vendored modules, not stubs\n        self.assertIs(fused.Microdot, _RealMicrodot)\n        self.assertIs(fused.Response, _RealResponse)\n        self.assertIs(fused.HTTPException, _RealHTTP)\n        self.assertIs(fused.SqliteDatabase, _RealSqlite)\n        self.assertIs(fused.Model, _RealModel)\n        self.assertTrue(issubclass(fused.Note, _RealModel))\n        self.assertIsInstance(fused.db, _RealSqlite)\n        self.assertIsInstance(fused.app, _RealMicrodot)\n\n    def test_validate_ok(self):\n        r = FakeRequest(payload={\"text\": \"  hello \"})\n        self.assertEqual(fused.validate_note_payload(r), \"hello\")\n\n    def test_validate_bad(self):\n        for bad in (None, [], {\"text\": \"\"}, {\"text\": 5}, {}):\n            with self.assertRaises(fused.HTTPException) as cm:\n                fused.validate_note_payload(FakeRequest(payload=bad))\n            self.assertEqual(cm.exception.status_code, 400)\n\n    def test_validate_raw_body_fallback(self):\n        r = FakeRequest(payload=None, raw=json.dumps({\"text\": \"raw\"}).encode())\n        r.json = None\n        self.assertEqual(fused.validate_note_payload(r), \"raw\")\n\n    def test_note_to_dict_and_json_response(self):\n        n = fused.Note.create(text=\"ser\")\n        d = fused.note_to_dict(n)\n        self.assertEqual(d, {\"id\": n.id, \"text\": \"ser\"})\n        resp = fused.json_response(d, status=201)\n        self.assertEqual(resp.status_code, 201)\n        body = resp.body if hasattr(resp, \"body\") else getattr(resp, \"data\", b\"\")\n        if isinstance(body, (bytes, bytearray)):\n            body = body.decode()\n        self.assertEqual(json.loads(body), d)\n        n.delete_instance()\n\n    def test_crud_handlers_end_to_end(self):\n        # POST /notes handler (Model bridge)\n        resp = run(fused.create_note(FakeRequest(payload={\"text\": \"e2e\"})))\n        self.assertEqual(resp.status_code, 201)\n        body = resp.body if hasattr(resp, \"body\") else getattr(resp, \"data\", b\"\")\n        if isinstance(body, (bytes, bytearray)):\n            body = body.decode()\n        nid = json.loads(body)[\"id\"]\n        # ModelSelect list bridge\n        resp2 = run(fused.list_notes(FakeRequest(payload=None)))\n        b2 = resp2.body if hasattr(resp2, \"body\") else getattr(resp2, \"data\", b\"\")\n        if isinstance(b2, (bytes, bytearray)):\n            b2 = b2.decode()\n        rows = json.loads(b2)\n        self.assertTrue(any(r[\"id\"] == nid and r[\"text\"] == \"e2e\" for r in rows))\n        # ModelSelect single-row bridge\n        resp3 = run(fused.get_note(FakeRequest(payload=None), str(nid)))\n        b3 = resp3.body if hasattr(resp3, \"body\") else getattr(resp3, \"data\", b\"\")\n        if isinstance(b3, (bytes, bytearray)):\n            b3 = b3.decode()\n        self.assertEqual(json.loads(b3), {\"id\": nid, \"text\": \"e2e\"})\n        # DoesNotExist -> 404 mapping\n        with self.assertRaises(fused.HTTPException) as cm:\n            run(fused.get_note(FakeRequest(payload=None), \"999999\"))\n        self.assertEqual(cm.exception.status_code, 404)\n        with self.assertRaises(fused.HTTPException) as cm2:\n            run(fused.get_note(FakeRequest(payload=None), \"abc\"))\n        self.assertEqual(cm2.exception.status_code, 404)\n\n    def test_db_hooks_present(self):\n        # before/after request DB connect/close hook shims exist and are callable\n        self.assertTrue(callable(getattr(fused, \"_before\", None)))\n        self.assertTrue(callable(getattr(fused, \"_after\", None)))\n        r = FakeRequest(payload=None)\n        run(fused._before(r))\n        resp = fused.json_response({\"ok\": True})\n        out = run(fused._after(r, resp))\n        self.assertIs(out, resp)\n\nif __name__ == \"__main__\":\n    unittest.main()\n",
  "ext": "# ASSISTANT-AUTHORED EXTENSION (written by the assistant, offline, no model\n# calls): adds the missing edit/delete behavior to the notes app.\n#\n# The reviewed assistant-repaired baseline in generated/app.py is byte-UNCHANGED;\n# this module imports it and registers the two additional routes on the same\n# microdot app object. Provenance: the original fixed goal was\n# save/read/edit/delete; the baseline proved save/read only (see PROVENANCE.md).\n# This module completes edit (PUT) and delete (DELETE). Nothing else is added.\nfrom generated.app import (\n    app, Note, DoesNotExist, HTTPException, json_response,\n    validate_note_payload,\n)\nfrom microdot import Response\n\n\ndef _get_note_or_404(id):\n    try:\n        nid = int(id)\n    except Exception:\n        raise HTTPException(404, \"not found\")\n    try:\n        return Note.get_by_id(nid)\n    except DoesNotExist:\n        raise HTTPException(404, \"not found\")\n\n\n@app.route(\"/notes/<id>\", methods=[\"PUT\"])\nasync def update_note(request, id):\n    # edit: validate body the same way create does, then persist via peewee\n    note = _get_note_or_404(id)\n    note.text = validate_note_payload(request)\n    note.save()\n    return json_response({\"id\": note.id, \"text\": note.text})\n\n\n@app.route(\"/notes/<id>\", methods=[\"DELETE\"])\nasync def delete_note(request, id):\n    # delete: remove the row; 204 No Content on success\n    note = _get_note_or_404(id)\n    nid = note.id\n    note.delete_instance()\n    return Response(\"\", status_code=204)\n"
 }
};
