"""The execution-review gate must pin EVERY file the sandbox can execute:
model-generated glue/tests AND the entire vendored tree. Pre-vendor-scope
attestations fail closed."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repofuse import gluereview  # noqa: E402


class GateCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rf-gate-")
        os.makedirs(os.path.join(self.dir, "generated"))
        os.makedirs(os.path.join(self.dir, "vendor", "somerepo"))
        with open(os.path.join(self.dir, "generated", "app.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(self.dir, "test_fused.py"), "w") as f:
            f.write("import unittest\n")
        with open(os.path.join(self.dir, "vendor", "somerepo",
                               "mod.py"), "w") as f:
            f.write("y = 2\n")
        self.att = os.path.join(self.dir, "..", "att.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_targets_include_vendor_tree(self):
        t = gluereview.review_targets(self.dir)
        self.assertIn(os.path.join("vendor", "somerepo", "mod.py"), t)
        self.assertIn(os.path.join("generated", "app.py"), t)
        self.assertIn("test_fused.py", t)

    def test_attestation_pins_vendor_bytes(self):
        doc = gluereview.write_attestation(self.dir, self.att)
        self.assertIn(os.path.join("vendor", "somerepo", "mod.py"),
                      doc["files"])
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertTrue(ok, why)

    def test_vendor_change_after_review_refuses(self):
        gluereview.write_attestation(self.dir, self.att)
        with open(os.path.join(self.dir, "vendor", "somerepo",
                               "mod.py"), "w") as f:
            f.write("y = 3  # tampered after review\n")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("changed since review", why)

    def test_legacy_attestation_without_vendor_fails_closed(self):
        """An attestation written when only glue was pinned must NOT
        authorize execution once vendored code is present."""
        import hashlib
        import json
        files = {}
        for rel in gluereview.generated_targets(self.dir):
            with open(os.path.join(self.dir, rel), "rb") as f:
                files[rel] = hashlib.sha256(f.read()).hexdigest()
        with open(self.att, "w") as f:
            json.dump({"files": files}, f)
        ok, why, pending = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("not covered by attestation", why)
        self.assertIn(os.path.join("vendor", "somerepo", "mod.py"), pending)

    def test_new_vendor_file_after_review_refuses(self):
        gluereview.write_attestation(self.dir, self.att)
        with open(os.path.join(self.dir, "vendor", "somerepo",
                               "extra.py"), "w") as f:
            f.write("z = 4\n")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("not covered by attestation", why)

    def test_empty_fusion_dir_passes_without_attestation(self):
        empty = tempfile.mkdtemp(prefix="rf-gate-empty-")
        try:
            ok, why, _ = gluereview.check_attestation(empty, None)
            self.assertTrue(ok)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class SymlinkCase(unittest.TestCase):
    """Symlinks in the execution tree must FAIL the gate, loudly: the
    sandbox copies with link resolution, so a link would smuggle
    unreviewed bytes into execution."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rf-link-")
        os.makedirs(os.path.join(self.dir, "generated"))
        os.makedirs(os.path.join(self.dir, "vendor", "somerepo"))
        with open(os.path.join(self.dir, "generated", "app.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(self.dir, "vendor", "somerepo",
                               "mod.py"), "w") as f:
            f.write("y = 2\n")
        self.att = os.path.join(self.dir, "..", "att.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _symlink(self, rel, target):
        os.symlink(target, os.path.join(self.dir, rel))

    def test_symlinked_generated_file_refused(self):
        self._symlink(os.path.join("generated", "evil.py"), "/etc/passwd")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("symlink", why)

    def test_symlinked_vendor_file_refused(self):
        self._symlink(os.path.join("vendor", "somerepo", "evil.py"),
                      "/etc/passwd")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("symlink", why)

    def test_symlinked_vendor_dir_refused(self):
        self._symlink(os.path.join("vendor", "otherdir"), "/tmp")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("symlink", why)

    def test_symlinked_test_fused_refused(self):
        self._symlink("test_fused.py", "/etc/passwd")
        ok, why, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertFalse(ok)
        self.assertIn("symlink", why)

    def test_write_attestation_refuses_symlink_tree(self):
        self._symlink(os.path.join("vendor", "somerepo", "evil.py"),
                      "/etc/passwd")
        with self.assertRaises(ValueError):
            gluereview.write_attestation(self.dir, self.att)

    def test_clean_tree_still_passes(self):
        gluereview.write_attestation(self.dir, self.att)
        ok, _, _ = gluereview.check_attestation(self.dir, self.att)
        self.assertTrue(ok)

    def test_execution_symlinks_lists_all(self):
        self._symlink(os.path.join("generated", "a.py"), "/tmp")
        self._symlink(os.path.join("vendor", "b"), "/tmp")
        hits = gluereview.execution_symlinks(self.dir)
        self.assertEqual(len(hits), 2)
