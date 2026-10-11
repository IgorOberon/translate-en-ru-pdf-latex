"""Clean-install diagnostics must not mistake broken tools for readiness."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doctor as d
from provenance import atomic_text


class InstallationTests(unittest.TestCase):
    def setUp(self):
        d.rows.clear()

    def test_nonzero_version_is_not_a_working_tool(self):
        reply = SimpleNamespace(returncode=1, stdout="program: missing DLL", stderr="")
        with patch.object(d.subprocess, "run", return_value=reply):
            self.assertIsNone(d._version("broken.exe"))

    def test_missing_psutil_blocks_dispatcher(self):
        with patch.object(importlib.util, "find_spec", side_effect=lambda name: None if name == "psutil" else object()):
            self.assertEqual(d.check_packages(), d.FAIL)

    def test_tex_failure_with_pdf_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_text(root / "assets/preamble.tex", "preamble fixture")
            def failed(cmd, **kwargs):
                folder = Path(kwargs["cwd"])
                (folder / "main.pdf").write_bytes(b"partial PDF")
                atomic_text(folder / "main.log", "! Undefined control sequence\n")
                return SimpleNamespace(returncode=1)
            with patch.object(d, "ROOT", root), patch.object(d.subprocess, "run", side_effect=failed):
                self.assertEqual(d.check_latex_build("xelatex", "fixture"), d.FAIL)

    def test_selected_marker_is_required_but_none_is_not(self):
        with patch.object(d, "marker", return_value="missing_marker_987654"), patch.object(d.shutil, "which", return_value=None):
            self.assertEqual(d.check_extractor("auto"), d.FAIL)
            self.assertEqual(d.check_extractor("scan"), d.FAIL)
            self.assertEqual(d.check_extractor("none"), d.OK)

    def test_server_checks_requested_model_and_versioned_url(self):
        seen = []
        def opened(url, **kwargs):
            seen.append(url)
            return io.BytesIO(json.dumps({"data": [{"id": "local-generic"}]}).encode())
        with patch.object(d, "OPENER", SimpleNamespace(open=opened)):
            self.assertEqual(d.check_lm_studio(False, "http://127.0.0.1:8080/v1", "absent"), d.FAIL)
            self.assertEqual(d.check_lm_studio(False, "http://127.0.0.1:8080/v1", "local-generic"), d.OK)
        self.assertEqual(seen, ["http://127.0.0.1:8080/v1/models"] * 2)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell installer")
    def test_installer_skips_broken_python_candidate(self):
        ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(ROOT / "install.ps1", root / "install.ps1")
            atomic_text(root / "stubs/python.cmd", "@echo off\necho broken Python 1>&2\nexit /b 1\n")
            # A working candidate emits its version on stderr: valid native output.
            # The existing fixture interpreter handles only installs and doctor.
            atomic_text(root / "stubs/python3.cmd", '@echo off\nif "%1"=="--version" (\necho Python 3.12.10 1>&2\nexit /b 0\n)\nexit /b 1\n')
            # Stop at venv creation after candidate selection; no pip/network.
            env = dict(os.environ)
            env["PATH"] = str(root / "stubs") + os.pathsep + str(ps.parent)
            r = subprocess.run([str(ps), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "install.ps1")],
                               env=env, cwd=root, capture_output=True, timeout=30)
            output = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
            self.assertIn("python3.cmd", output)
            self.assertNotIn("NativeCommandError", output)
            self.assertNotEqual(r.returncode, 0)  # fixture deliberately cannot create venv


if __name__ == "__main__":
    unittest.main()
