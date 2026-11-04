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


if __name__ == "__main__":
    unittest.main()
