"""Regression: dependency extraction must not mistake tool config for
packages (reviewer 2026-11-04: pytest addopts inflated 85/99 entries)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repofuse.analyze import _pyproject_dependencies, _add_dep  # noqa: E402


class TestPyprojectScoping(unittest.TestCase):
    TOML = """
[project]
name = "demo"
dependencies = [
    "requests>=2.31",
    "flask==3.0.0",
]

[project.optional-dependencies]
test = ["pytest>=8"]

[tool.pytest.ini_options]
addopts = ["-v", "--strict-markers", "--maxfail=1", "--cov=demo"]
[tool.setuptools]
packages = ["demo"]
"""

    def test_tool_sections_are_not_dependencies(self):
        deps = _pyproject_dependencies(self.TOML)
        self.assertEqual(sorted(deps),
                         ["flask==3.0.0", "pytest>=8", "requests>=2.31"])
        self.assertNotIn("--strict-markers", deps)
        self.assertNotIn("packages", deps)


class TestRequirementLines(unittest.TestCase):
    def test_flags_and_options_rejected(self):
        d = {}
        for raw in ["-r other.txt", "--index-url https://x", "-e .",
                    "--strict-markers", "bad name", "", "# comment"]:
            self.assertFalse(_add_dep(d, raw, "requirements.txt"), raw)
        self.assertEqual(d, {})

    def test_real_requirements_kept(self):
        d = {}
        for raw in ["requests>=2.31", "flask==3.0.0  # pin", "numpy[all]",
                    "pytest"]:
            self.assertTrue(_add_dep(d, raw, "requirements.txt"), raw)
        self.assertEqual(sorted(d), ["flask", "numpy", "pytest", "requests"])
        self.assertEqual(d["flask"]["spec"], "==3.0.0")
        self.assertEqual(d["pytest"]["spec"], "*")

    def test_optional_and_test_requirements_are_development(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "tests"))
            with open(os.path.join(tmp, "pyproject.toml"), "w", encoding="utf-8") as f:
                f.write(TestPyprojectScoping.TOML)
            with open(os.path.join(tmp, "tests", "requirements.txt"), "w", encoding="utf-8") as f:
                f.write("hypothesis>=6\n")
            with open(os.path.join(tmp, "requirements.txt"), "w", encoding="utf-8") as f:
                f.write("flask==3.0.0\n")
            from repofuse.analyze import read_dependencies
            from repofuse.ingest import find_manifests
            deps = read_dependencies(tmp, find_manifests(tmp))
        self.assertTrue(deps["pytest"]["dev"])
        self.assertTrue(deps["hypothesis"]["dev"])
        self.assertNotIn("dev", deps["flask"])
        self.assertNotIn("dev", deps["requests"])


if __name__ == "__main__":
    unittest.main()
