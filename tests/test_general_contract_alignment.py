"""Offline contract-alignment checks for the general (arbitrary-repo)
synthesis pipeline. The durable gate against the attempt-2 failure class:
anything the schema declares must be enforced locally, prompts must state
the same numbers the validator enforces, and generated output must be
confinable to authorized write slots. No provider calls.
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repofuse import synthesize as synth  # noqa: E402
from repofuse.budget import BudgetExceeded  # noqa: E402


def _arch(**over):
    arch = {"source_exports": {"a": ["x"]},
            "arbitrage_opportunity": "ok",
            "required_shims": [], "bridge": [], "risks": []}
    arch.update(over)
    return arch


class TestValidatorEnforcesSchemaCaps(unittest.TestCase):
    def test_schema_caps_match_validator_constants(self):
        s = synth.ARCH_JSON_SCHEMA["properties"]
        self.assertEqual(
            s["source_exports"]["additionalProperties"]["maxItems"],
            synth.ARCH_MAX_EXPORTS_PER_REPO)
        self.assertEqual(
            s["source_exports"]["additionalProperties"]["items"]
            ["maxLength"], synth.ARCH_MAX_STR)
        self.assertEqual(s["bridge"]["maxItems"], synth.ARCH_MAX_BRIDGE)
        self.assertEqual(s["required_shims"]["maxItems"],
                         synth.ARCH_MAX_SHIMS)
        self.assertEqual(s["risks"]["maxItems"], synth.ARCH_MAX_RISKS)
        self.assertEqual(s["arbitrage_opportunity"]["maxLength"], 400)

    def test_list_caps_rejected(self):
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                source_exports={"a": ["x"] *
                                (synth.ARCH_MAX_EXPORTS_PER_REPO + 1)}))
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                bridge=[{"from_repo": "a", "from_export": "x",
                         "to_repo": "b", "to_route_or_input": "y"}] *
                (synth.ARCH_MAX_BRIDGE + 1)))
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                risks=["r"] * (synth.ARCH_MAX_RISKS + 1)))

    def test_string_maxlength_enforced_locally(self):
        """The schema declares maxLength but provider enforcement is
        unconfirmed; the local validator must refuse oversized strings."""
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                arbitrage_opportunity="o" * 401))
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                source_exports={"a": ["x" * (synth.ARCH_MAX_STR + 1)]}))
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                required_shims=["s" * (synth.ARCH_MAX_STR + 1)]))
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(_arch(
                risks=["r" * (synth.ARCH_MAX_STR + 1)]))

    def test_char_budget_rejected(self):
        big = _arch(source_exports={
            f"repo{i}": ["x" * synth.ARCH_MAX_STR] *
            synth.ARCH_MAX_EXPORTS_PER_REPO for i in range(6)})
        # each piece is within per-string caps but the whole exceeds budget
        self.assertGreater(
            len(__import__("json").dumps(big)),
            synth.ARCH_OUTPUT_CHAR_BUDGET)
        with self.assertRaises(BudgetExceeded):
            synth.validate_architecture_size(big)

    def test_valid_architecture_passes(self):
        self.assertTrue(synth.validate_architecture_size(_arch()))


class TestPromptSchemaAgreement(unittest.TestCase):
    MANIFEST = {"repos": [{"slug": "a", "role": "library",
                           "exports": [], "routes": [],
                           "dependency_count": 0},
                          {"slug": "b", "role": "service",
                           "exports": [], "routes": [],
                           "dependency_count": 0}],
                "boundary_candidates": [], "conflicts": [],
                "acceptance_criteria": ["c1"],
                "qualification_contract": {"app_module": "generated/app.py"}}

    def test_arch_prompt_states_schema_numbers(self):
        msgs = synth.build_architecture_prompt(self.MANIFEST, [])
        blob = msgs[1]["content"]
        for n in (synth.ARCH_MAX_EXPORTS_PER_REPO, synth.ARCH_MAX_BRIDGE,
                  synth.ARCH_MAX_SHIMS, synth.ARCH_MAX_RISKS,
                  synth.ARCH_MAX_STR, synth.ARCH_OUTPUT_CHAR_BUDGET):
            self.assertIn(str(n), blob)
        self.assertIn("source_exports", blob)
        self.assertIn("arbitrage_opportunity", blob)

    def test_test_prompt_matches_test_schema_key(self):
        schema_key = synth.TEST_JSON_SCHEMA["required"][0]
        msgs = synth.build_test_prompt(self.MANIFEST, _arch(),
                                       {"app.py": "x = 1"})
        self.assertIn(schema_key, msgs[1]["content"])
        self.assertEqual(schema_key, "test_fused.py")
        # prompt requires exercising the real vendored inputs, not only glue
        self.assertIn("vendored input repos", msgs[1]["content"])
        self.assertIn("wall-clock", msgs[1]["content"])

    def test_glue_is_honestly_unconstrained(self):
        """Glue maps arbitrary filenames, so json_object only - and the
        code must never claim schema constraint it does not have."""
        self.assertEqual(synth.GLUE_RESPONSE_FORMAT, {"type": "json_object"})


class TestWriteSlotConfinement(unittest.TestCase):
    def test_glue_names_snake_case_only(self):
        rx = synth._GENERATED_NAME
        for ok in ("app.py", "adapter_shim.py", "fuse_bridge_v2.py"):
            self.assertTrue(rx.match(ok), ok)
        for bad in ("App.py", "app.PY", "../app.py", "a-b.py",
                    "app.py/evil", "app", ".py", "9app.py"):
            self.assertFalse(rx.match(bad), bad)

    def test_write_files_confines_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            wrote = synth._write_files(d, {
                "generated/app.py": "print(1)",
                "../escape.py": "evil",
                "test_fused.py": "evil",  # glue slot must refuse test slot
                "UPPER.PY": "evil",
            }, "m", "t")
            self.assertEqual(wrote, [os.path.join("generated", "app.py")])
            content = open(os.path.join(d, "generated", "app.py")).read()
            self.assertTrue(content.startswith("# Generated by m"))
            # second write of the same name refuses (never overwrite)
            wrote2 = synth._write_files(d, {"app.py": "print(2)"}, "m", "t")
            self.assertEqual(wrote2, [])
            self.assertIn("print(1)",
                          open(os.path.join(d, "generated", "app.py")).read())

    def test_test_slot_exact_name_only(self):
        with tempfile.TemporaryDirectory() as d:
            wrote = synth._write_files(d, {"test_fused.py": "import unittest",
                                           "test_other.py": "evil"},
                                       "m", "t", slot="test")
            self.assertEqual(wrote, ["test_fused.py"])


if __name__ == "__main__":
    unittest.main()
