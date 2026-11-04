"""Schema-vs-validator contract alignment for the paid build/ideas pipeline.

Attempt 2 (run-b16b4c4b772e176d) proved the class: the charged call
succeeded, but the model wrote field type "string" because ARCH_SCHEMA
declared a free string while the validator requires FIELD_TYPES. These
checks assert, for EVERY paid schema, that every constraint the validator
enforces is either expressed in the schema (so structured output can
constrain it) or documented here as an intentional prompt-enforced gap
with the validator proven fail-closed on it. Retained REAL responses are
regression inputs. No network, no key, no calls.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_ai
import ideas_ai

PASS = 0
FAIL = []


def check(name, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  ok  {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"FAIL  {name}: {e}")


def _inner(schema):
    return schema["json_schema"]["schema"]


ARCH = _inner(build_ai.ARCH_SCHEMA)
GLUE = _inner(build_ai.GLUE_SCHEMA)
TESTS = _inner(build_ai.TESTS_SCHEMA)
IDEAS = ideas_ai.IDEA_SCHEMA["json_schema"]["schema"]
PLAN_PROPS = ARCH["properties"]["plan"]["properties"]


# ---------- architecture: every validator constraint is mapped ----------

def t_arch_field_type_enum_matches_validator():
    enum = PLAN_PROPS["fields"]["items"]["properties"]["type"]["enum"]
    assert set(enum) == set(build_ai.FIELD_TYPES), enum
check("arch: field type schema enum == validator FIELD_TYPES",
      t_arch_field_type_enum_matches_validator)


def t_arch_required_keys_match_validator_reads():
    # keys _validate_arch reads off plan
    reads = {"app_name", "crud_prefix", "entity", "fields",
             "routes", "uses", "notes"}
    assert set(ARCH["properties"]["plan"]["required"]) == reads
    assert set(PLAN_PROPS) == reads
    item = PLAN_PROPS["fields"]["items"]
    assert set(item["required"]) == {"name", "type"}
    assert set(item["properties"]) == {"name", "type"}
check("arch: required/properties match what the validator reads",
      t_arch_required_keys_match_validator_reads)


def t_arch_schema_maxes_match_validator_bounds():
    assert PLAN_PROPS["app_name"].get("maxLength") == 60
    assert PLAN_PROPS["entity"].get("maxLength") == 40
    assert PLAN_PROPS["notes"].get("maxLength") == 400
    f = PLAN_PROPS["fields"]
    assert f.get("maxItems") == 8
    assert f["items"]["properties"]["name"].get("maxLength") == 30
    r = PLAN_PROPS["routes"]
    assert r.get("maxItems") == 8
    assert r["items"].get("maxLength") == 80
    # behavioral cross-check against the validator's own bounds
    base = {"plan": {"app_name": "x" * 61, "crud_prefix": "/n",
                     "entity": "N",
                     "fields": [{"name": "t", "type": "str"}],
                     "routes": ["GET /n"], "uses": [], "notes": "ok"}}
    try:
        build_ai._validate_arch(base, set())
        raise AssertionError("validator accepted 61-char app_name")
    except build_ai.Refused:
        pass
check("arch: schema maxLength/maxItems == validator upper bounds",
      t_arch_schema_maxes_match_validator_bounds)


def t_prompts_state_schema_inexpressible_rules():
    arch = build_ai._messages("build-architecture",
                              {"title": "t", "what": "w", "fit": []},
                              [])[1]["content"]
    for needle in ("str, int", "float, bool", "snake_case",
                   "starting with /"):
        assert needle in arch, needle
    glue = build_ai._messages("build-glue",
                              {"title": "t", "what": "w", "fit": []},
                              [], {})[1]["content"]
    for needle in ("(payload, status)", "201", "bare JSON array",
                   "exact field names"):
        assert needle in glue, needle
    tests = build_ai._messages("build-tests",
                               {"title": "t", "what": "w", "fit": []},
                               [], {})[1]["content"]
    assert "import vendor" in tests
    assert tests.index("import vendor") < tests.index("generated.app")
check("prompts state the schema-inexpressible contract rules",
      t_prompts_state_schema_inexpressible_rules)


def t_arch_documented_gaps_fail_closed():
    # constraints the schema cannot express stay validator-enforced:
    # prefix pattern, routes count/length, name lengths, notes length
    base = {"plan": {"app_name": "x", "crud_prefix": "/n", "entity": "N",
                     "fields": [{"name": "t", "type": "str"}],
                     "routes": ["GET /n"], "uses": [], "notes": "ok"}}
    bad_prefix = json.loads(json.dumps(base))
    bad_prefix["plan"]["crud_prefix"] = "no-slash"
    bad_routes = json.loads(json.dumps(base))
    bad_routes["plan"]["routes"] = [f"GET /{i}" for i in range(9)]
    bad_notes = json.loads(json.dumps(base))
    bad_notes["plan"]["notes"] = "x" * 401
    for label, payload in (("prefix", bad_prefix), ("routes", bad_routes),
                           ("notes", bad_notes)):
        try:
            build_ai._validate_arch(payload, set())
            raise AssertionError(f"{label}: validator accepted")
        except build_ai.Refused:
            pass
check("arch: schema-inexpressible constraints still fail closed",
      t_arch_documented_gaps_fail_closed)


# ---------- glue / tests: exact-path and envelope alignment ----------

def t_glue_path_enum_matches_validator():
    enum = GLUE["properties"]["file"]["properties"]["path"]["enum"]
    assert enum == ["generated/app.py"], enum
check("glue: path schema enum == validator required path",
      t_glue_path_enum_matches_validator)


def t_tests_path_enum_matches_validator():
    enum = TESTS["properties"]["file"]["properties"]["path"]["enum"]
    assert enum == ["test_fused.py"], enum
check("tests: path schema enum == validator required path",
      t_tests_path_enum_matches_validator)


def t_file_envelopes_match_validator_reads():
    for schema in (GLUE, TESTS):
        assert schema["required"] == ["file"]
        f = schema["properties"]["file"]
        assert set(f["required"]) == {"path", "content"}
        assert set(f["properties"]) == {"path", "content"}
        assert f["additionalProperties"] is False
check("glue/tests: file envelope matches validator reads",
      t_file_envelopes_match_validator_reads)


def t_code_ast_gap_fails_closed():
    # content AST constraints are schema-inexpressible: validator must
    # still refuse os-importing code even though the schema allows it
    payload = {"file": {"path": "generated/app.py",
                        "content": "import os\napp = None\n"}}
    try:
        build_ai._validate_code_file(payload, "generated/app.py", True,
                                     "build-glue")
        raise AssertionError("validator accepted os import")
    except build_ai.Refused:
        pass
check("glue: AST constraints (schema-inexpressible) fail closed",
      t_code_ast_gap_fails_closed)


def t_path_slot_guard_still_normalizes():
    # the slot guard normalizes "./generated/app.py" spellings; the enum
    # constrains the RAW value, the guard handles near-misses offline
    payload = {"file": {"path": "./generated/app.py",
                        "content": "x = 1\n"}}
    try:
        build_ai._validate_code_file(payload, "generated/app.py", True,
                                     "build-glue")
    except build_ai.Refused as e:
        assert "path" not in str(e), f"guard regression: {e}"
check("glue: path slot guard still normalizes contract-adjacent spelling",
      t_path_slot_guard_still_normalizes)


# ---------- regression on RETAINED REAL responses ----------

ATTEMPT2_RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "paid-build",
                            "raw-build-architecture-run-b16b4c4b772e176d.json")
ATTEMPT2_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "testdata",
                                "arch-plan-attempt2-sanitized.json")
ATTEMPT2_EXPORTS = {"Microdot", "Request", "Response", "AutoField",
                    "Base", "BaseModelSelect"}


def _attempt2_plan():
    """The retained attempt-2 plan payload: the immutable raw record when
    present (live checkout), else the committed sanitized fixture."""
    if os.path.exists(ATTEMPT2_RAW):
        raw = json.load(open(ATTEMPT2_RAW))
        return json.loads(raw["content"]), "retained raw"
    if os.path.exists(ATTEMPT2_FIXTURE):
        fx = json.load(open(ATTEMPT2_FIXTURE))
        return fx["plan_payload"], "sanitized fixture"
    raise AssertionError("no attempt-2 evidence available (neither raw "
                         "nor fixture)")


def t_attempt2_plan_rejected_as_recorded():
    # the attempt-2 plan must reproduce the recorded refusal; on a fresh
    # checkout the sanitized fixture carries the same payload
    data, origin = _attempt2_plan()
    try:
        build_ai._validate_arch(data, ATTEMPT2_EXPORTS)
        raise AssertionError(f"attempt-2 plan ({origin}) now ACCEPTED - "
                             "validator was loosened, which is forbidden")
    except build_ai.Refused as e:
        assert "contract" in str(e)
check("regression: attempt-2 plan still refused (validator not loosened) "
      "[raw if present, else fixture]", t_attempt2_plan_rejected_as_recorded)


def t_attempt2_counterfactual_enum_values_pass():
    # COUNTERFACTUAL check on an in-memory copy (NOT a repair: the
    # retained artifact is never modified): the same plan with
    # schema-enum field types passes end-to-end, proving the enum fix
    # closes the exact observed failure mode.
    data, origin = _attempt2_plan()
    data = json.loads(json.dumps(data))  # in-memory copy only
    for f in data["plan"]["fields"]:
        f["type"] = "str"
    plan, dropped = build_ai._validate_arch(data, ATTEMPT2_EXPORTS)
    assert plan["app_name"] == "notes_api" and dropped == 0
check("counterfactual: attempt-2 plan with enum field types passes "
      "(in-memory copy; retained artifact immutable)",
      t_attempt2_counterfactual_enum_values_pass)


def t_attempt2_types_outside_new_enum():
    # every field type in the attempt-2 payload is outside the new enum:
    # structured output would now constrain it before any charged call
    data, origin = _attempt2_plan()
    enum = set(PLAN_PROPS["fields"]["items"]["properties"]["type"]["enum"])
    assert all(f["type"] not in enum for f in data["plan"]["fields"])
check("regression: attempt-2 types are outside the new enum",
      t_attempt2_types_outside_new_enum)


def t_qual2_retained_ideas_pass_ideas_validator():
    # the retained qual-2 REAL ideas response still passes its validator
    # (export_names = the union it cited; citation correctness was proven
    # live in qual-2, this proves shape alignment is unchanged)
    path = "/home/sandbox/repofuse-ideas-qual-2/paid-ideas/" \
           "raw-run-5c24e267d7801175.json"
    if not os.path.exists(path):
        print("    (skip: retained qual-2 raw not present outside the "
              "repo checkout)")
        return
    raw = json.load(open(path))
    data = json.loads(raw["content"])
    names = {x for c in data["ideas"] for x in c.get("fit", [])}
    cards, dropped = ideas_ai._validate(raw["content"], names)
    assert 1 <= len(cards) <= ideas_ai.MAX_CARDS and dropped == 0
check("regression: retained qual-2 ideas response passes ideas validator",
      t_qual2_retained_ideas_pass_ideas_validator)


def t_ideas_schema_matches_card_validator():
    # schema expresses the same bounds the validator enforces inline
    item = IDEAS["properties"]["ideas"]["items"]
    assert set(item["required"]) == {"title", "what", "fit"}
    assert item["properties"]["title"].get("maxLength") == 80
    assert item["properties"]["what"].get("maxLength") == 400
    assert item["properties"]["fit"].get("maxItems") == 8
    assert IDEAS["properties"]["ideas"].get("maxItems") == \
        ideas_ai.MAX_CARDS
    # behavioral cross-check: 81-char title dropped, 80-char kept
    def card(n):
        return {"title": "x" * n, "what": "w",
                "fit": ["Microdot"]}
    payload = json.dumps({"ideas": [card(80), card(81)]})
    cards, dropped = ideas_ai._validate(payload, {"Microdot"})
    assert len(cards) == 1 and dropped == 1
check("ideas: schema constraints == card validator bounds (behavioral)",
      t_ideas_schema_matches_card_validator)


if __name__ == "__main__":
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
