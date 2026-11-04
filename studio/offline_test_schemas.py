#!/usr/bin/env python3
"""Every structured-output schema this app can send, checked OFFLINE against
the documented Meta Model API rules (dev.meta.ai/docs/structured-output,
fetched 2026-11-04):
- strict subset (we send strict: true): root plain object (no anyOf/oneOf/
  allOf/enum/not); no allOf/oneOf ANYWHERE; every object sets
  additionalProperties: false; every object's required lists ALL properties
- no $ref / recursion
- limits: depth <= 10, total properties <= 5000, combined name/enum/const
  string length <= 120000, enum values <= 1000
A violation here means a deterministic provider HTTP 400 - caught offline,
never discovered by a charged call again."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_ai
import ideas_ai

FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" - {detail}" if detail
                                                   and not cond else ""))
    if not cond:
        FAILURES.append(name)


BANNED_ANYWHERE = {"allOf", "oneOf"}
BANNED_ROOT = BANNED_ANYWHERE | {"anyOf", "enum", "not", "$ref"}


def walk(node, path, depth, stats, problems):
    if depth > 10:
        problems.append(f"{path}: nesting depth {depth} > 10")
    if not isinstance(node, dict):
        return
    for banned in BANNED_ANYWHERE | {"$ref"}:
        if banned in node:
            problems.append(f"{path}: banned keyword {banned}")
    t = node.get("type")
    if t == "object" and "properties" in node:
        props = node["properties"]
        if node.get("additionalProperties") is not False:
            problems.append(f"{path}: object without "
                            "additionalProperties: false")
        req = node.get("required")
        if not isinstance(req, list) or set(req) != set(props):
            problems.append(f"{path}: required does not list every "
                            f"property (has {req}, want {sorted(props)})")
        stats["properties"] += len(props)
        for k, sub in props.items():
            stats["chars"] += len(k)
            walk(sub, f"{path}.{k}", depth + 1, stats, problems)
    elif t == "object":
        # an object WITHOUT properties is an open map - strict rejects it
        problems.append(f"{path}: open-map object (no properties)")
    if t == "array" and isinstance(node.get("items"), dict):
        walk(node["items"], f"{path}[]", depth + 1, stats, problems)
    for enum in (node.get("enum") or []):
        stats["enums"] += 1
        if isinstance(enum, str):
            stats["chars"] += len(enum)
    if isinstance(node.get("const"), str):
        stats["chars"] += len(node["const"])


def audit(label, envelope):
    check(f"{label}: wrapper type json_schema",
          envelope.get("type") == "json_schema")
    js = envelope.get("json_schema") or {}
    check(f"{label}: strict true sent",
          js.get("strict") is True and isinstance(js.get("name"), str))
    schema = js.get("schema") or {}
    check(f"{label}: root is plain object",
          schema.get("type") == "object"
          and not (BANNED_ROOT & set(schema)))
    stats = {"properties": 0, "chars": 0, "enums": 0}
    problems = []
    walk(schema, "$", 1, stats, problems)
    for p in problems:
        check(f"{label}: {p}", False)
    check(f"{label}: strict subset clean", not problems)
    check(f"{label}: limits ok",
          stats["properties"] <= 5000 and stats["chars"] <= 120000
          and stats["enums"] <= 1000, json.dumps(stats))
    print(f"  ({label}: {stats['properties']} props, "
          f"{stats['chars']} chars, {stats['enums']} enum values)")


def main():
    audit("ARCH", build_ai.ARCH_SCHEMA)
    audit("GLUE", build_ai.GLUE_SCHEMA)
    audit("TESTS", build_ai.TESTS_SCHEMA)
    audit("IDEAS", ideas_ai.IDEA_SCHEMA)
    # error-body retention through the REAL _post: status + bounded,
    # key-redacted excerpt on ModelCallError
    import io
    import urllib.error
    import repofuse.model_api as ma

    class FakeResp:
        def read(self, n=-1):
            return b'{"error":{"message":"schema invalid at uses: ' \
                   b'additionalProperties must be false, key leak ' \
                   b'secret-test-key-123"}}'

    def fake_open(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {}, FakeResp())
    old_opener = ma._OPENER
    ma._OPENER = type("O", (), {"open": staticmethod(fake_open)})()
    try:
        try:
            ma._post("https://api.meta.ai/v1/chat/completions", {},
                     "secret-test-key-123", 5)
            check("_post error path raises", False)
        except ma.ModelCallError as e:
            check("status retained", e.status == 400)
            check("provider diagnostic retained",
                  e.body_excerpt and "additionalProperties" in
                  e.body_excerpt)
            check("key redacted from diagnostic",
                  "secret-test-key-123" not in (e.body_excerpt or "")
                  and "[redacted]" in (e.body_excerpt or ""))
    finally:
        ma._OPENER = old_opener

    # the actual serialization path: response_format passed verbatim
    import inspect
    import repofuse.model_api as ma
    src = inspect.getsource(ma.chat_completion)
    check("chat_completion passes response_format verbatim",
          'payload["response_format"] = response_format' in src)
    check("chat_completion refuses max_tokens > 4096",
          "exceeds hard cap 4096" in src)
    print(f"\n{len(FAILURES)} failures")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
