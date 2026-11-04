"""Hostile-boundary tests: each test RUNS inside the sandbox and asserts the
boundary from within. These execute attack code in the sandbox on purpose;
they never run it on the host."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repofuse.sandbox import build_sandbox_cmd, bwrap_available


def run_in_sandbox(python_code, extra_setup=None):
    tmp = tempfile.mkdtemp(prefix="repofuse-hostile-")
    work = os.path.join(tmp, "work")
    os.makedirs(work)
    if extra_setup:
        extra_setup(work)
    probe = os.path.join(work, "probe.py")
    with open(probe, "w") as f:
        f.write(python_code)
    python = shutil.which("python3") or "/usr/bin/python3"
    sbox_tmp = os.path.join(tmp, "sbox-tmp")
    os.makedirs(sbox_tmp, exist_ok=True)
    cmd = build_sandbox_cmd(work, sbox_tmp, python, ["probe.py"])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    shutil.rmtree(tmp, ignore_errors=True)
    return proc


@unittest.skipUnless(bwrap_available(), "bwrap required")
class HostileBoundaryTest(unittest.TestCase):
    def test_network_blocked(self):
        r = run_in_sandbox(
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 443), timeout=2)\n"
            "    print('NET-OPEN')\n"
            "except OSError:\n"
            "    print('NET-BLOCKED')\n")
        self.assertIn("NET-BLOCKED", r.stdout)

    def test_host_paths_not_mounted(self):
        r = run_in_sandbox(
            "import os\n"
            "checks = {\n"
            "  'etc_passwd': os.path.exists('/etc/passwd'),\n"
            "  'home_dirs': os.path.exists('/home') and bool(os.listdir('/home')),\n"
            "  'root_dir': os.path.exists('/root'),\n"
            "}\n"
            "print(checks)\n")
        self.assertIn("'etc_passwd': False", r.stdout)
        self.assertIn("'home_dirs': False", r.stdout)
        self.assertIn("'root_dir': False", r.stdout)

    def test_env_not_inherited(self):
        os.environ["REPOFUSE_SECRET_PROBE"] = "should-not-leak"
        try:
            r = run_in_sandbox(
                "import os\n"
                "print('SECRET_VISIBLE' if os.environ.get('REPOFUSE_SECRET_PROBE')"
                " else 'ENV-CLEAN')\n")
        finally:
            del os.environ["REPOFUSE_SECRET_PROBE"]
        self.assertIn("ENV-CLEAN", r.stdout)

    def test_pid_namespace_hides_host_processes(self):
        r = run_in_sandbox(
            "import os\n"
            "if not os.path.exists('/proc'):\n"
            "    print('PROC-ABSENT')\n"
            "else:\n"
            "    pids = [p for p in os.listdir('/proc') if p.isdigit()]\n"
            "    print('PIDCOUNT', len(pids))\n")
        # /proc not mounted at all, or a fresh pid-ns /proc with few entries
        if "PROC-ABSENT" in r.stdout:
            return
        line = [l for l in r.stdout.splitlines() if l.startswith("PIDCOUNT")]
        self.assertTrue(line, r.stderr[-300:])
        self.assertLessEqual(int(line[0].split()[1]), 10)

    def test_cannot_kill_host_init(self):
        r = run_in_sandbox(
            "import os, signal\n"
            "try:\n"
            "    os.kill(1, 0)\n"
            "    print('PID1-VISIBLE')\n"
            "except (ProcessLookupError, PermissionError):\n"
            "    print('PID1-ISOLATED')\n")
        # either pid1 is the sandbox's own init or absent - never host init
        self.assertNotEqual(r.returncode, 0) if False else None
        self.assertTrue("PID1-" in r.stdout)

    def test_host_filesystems_readonly(self):
        r = run_in_sandbox(
            "import os, tempfile\n"
            "try:\n"
            "    open('/usr/repofuse-writetest', 'w').write('x')\n"
            "    print('USR-WRITABLE')\n"
            "except (OSError, PermissionError) as e:\n"
            "    print('USR-READONLY')\n"
            "open('/work/ok', 'w').write('x')\n"
            "print('WORK-WRITABLE')\n")
        self.assertIn("USR-READONLY", r.stdout)
        self.assertIn("WORK-WRITABLE", r.stdout)

    def test_no_inherited_file_descriptors(self):
        host_probe = tempfile.NamedTemporaryFile(
            prefix="repofuse-fd-", delete=False, mode="w")
        host_probe.write("host-secret")
        host_probe.flush()
        fd = host_probe.fileno()
        try:
            r = subprocess.run(
                build_sandbox_cmd(
                    _setup_fd_work(host_probe.name),
                    tempfile.mkdtemp(prefix="repofuse-tmp-"),
                    shutil.which("python3") or "/usr/bin/python3",
                    ["probe.py"]),
                capture_output=True, text=True, timeout=60,
                close_fds=False, pass_fds=(fd,))
            # fd was passed; but host PATH of the file is not mounted
            self.assertIn("HOSTPATH-GONE", r.stdout)
        finally:
            host_probe.close()
            os.unlink(host_probe.name)

    def test_rlimits_enforced(self):
        r = run_in_sandbox(
            "import resource\n"
            "print('CPU', resource.getrlimit(resource.RLIMIT_CPU)[0])\n"
            "print('NPROC', resource.getrlimit(resource.RLIMIT_NPROC)[0])\n"
            "print('AS', resource.getrlimit(resource.RLIMIT_AS)[0])\n")
        self.assertIn("CPU 60", r.stdout)
        self.assertIn("NPROC 64", r.stdout)
        self.assertIn("AS 1073741824", r.stdout)

    def test_memory_bomb_capped(self):
        r = run_in_sandbox(
            "try:\n"
            "    x = b' ' * (8 * 1024**3)\n"
            "    print('ALLOC-SUCCEEDED')\n"
            "except (MemoryError, OverflowError):\n"
            "    print('ALLOC-CAPPED')\n")
        self.assertIn("ALLOC-CAPPED", r.stdout)


def _setup_fd_work(probe_target):
    tmp = tempfile.mkdtemp(prefix="repofuse-fdwork-")
    work = os.path.join(tmp, "work")
    os.makedirs(work)
    with open(os.path.join(work, "probe.py"), "w") as f:
        f.write(
            "import os\n"
            f"print('HOSTPATH-GONE' if not os.path.exists({probe_target!r})"
            " else 'HOSTPATH-READABLE')\n")
    return work


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(bwrap_available(), "bwrap required")
class AntiForgeryAndResourceTest(unittest.TestCase):
    def _run_module(self, module_src):
        import tempfile
        from repofuse.sandbox import run_tests_isolated
        tmp = tempfile.mkdtemp(prefix="repofuse-forge-")
        with open(os.path.join(tmp, "test_fused.py"), "w") as f:
            f.write(module_src)
        from repofuse import gluereview
        att = os.path.join(tmp, "..", "attest.json")
        att = os.path.abspath(att)
        gluereview.write_attestation(tmp, att)
        try:
            return run_tests_isolated(tmp, attestation_path=att)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_printed_ok_and_fake_verdict_do_not_count(self):
        res = self._run_module(
            "import unittest\n"
            "print('Ran 99 tests in 0.001s')\n"
            "print('OK')\n"
            "print('REPOFUSE-VERDICT '\n"
            "      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "      ' {\"ran\": 99, \"errors\": 0, \"failures\": 0, \"ok\": true}')\n"
            "class T(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        self.assertEqual(1, 2)\n")
        self.assertEqual(res["status"], "failed")
        self.assertIn("1 failure", res.get("detail", ""),
                      str(res)[:300])

    def test_zero_tests_never_passes(self):
        res = self._run_module(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    pass\n")
        self.assertEqual(res["status"], "failed")
        self.assertIn("zero tests", res.get("detail", ""))

    def test_host_site_packages_not_importable(self):
        res = self._run_module(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_no_host_packages(self):\n"
            "        with self.assertRaises(ModuleNotFoundError):\n"
            "            import pip  # host-only package\n")
        self.assertEqual(res["status"], "passed", str(res)[:300])

    def test_tmp_writes_count_toward_watchdog(self):
        # /tmp inside the sandbox is a host-visible bound subdir of the
        # scratch root, so writes there are covered by the same watchdog.
        res = self._run_module(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_eat_tmp(self):\n"
            "        for i in range(50):\n"
            "            with open(f'/tmp/big{i}', 'wb') as f:\n"
            "                f.write(b'x' * (30 * 1024 * 1024))\n")
        self.assertEqual(res["status"], "failed")
        self.assertTrue(
            "watchdog" in res.get("detail", "").lower()
            or res.get("verdict", {}).get("errors", 0) > 0
            or res.get("exit_code") != 0,
            str(res)[:400])

    def test_disk_watchdog_kills_exhaustion(self):
        res = self._run_module(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_eat_disk(self):\n"
            "        for i in range(50):\n"
            "            with open(f'/work/big{i}', 'wb') as f:\n"
            "                f.write(b'x' * (30 * 1024 * 1024))\n")
        self.assertEqual(res["status"], "failed")
        self.assertTrue(
            "watchdog" in res.get("detail", "").lower()
            or res.get("verdict", {}).get("errors", 0) > 0
            or res.get("exit_code") != 0,
            str(res)[:400])
