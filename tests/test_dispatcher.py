"""Deterministic local-first dispatch contracts; no LLM/GPU required."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pipeline as p
import procutils
from endpoint_policy import validate_endpoint, Guard, model_opener
from build_ocr_md import join_hyphen
from accept_fraktur import blocks_of
from translate import split_blocks, validate_candidate
from editorial import review_ledger
from provenance import atomic_text, sha_text, write_json
from urllib.request import Request


class DispatcherTests(unittest.TestCase):
    def test_lms_success_does_not_hide_other_gpu_model(self):
        cuda = SimpleNamespace(is_available=lambda: True, mem_get_info=lambda: (1 * 2**30, 16 * 2**30))
        with patch.dict(sys.modules, torch=SimpleNamespace(cuda=cuda)), patch.object(procutils.shutil, "which", return_value=__file__), patch.object(procutils.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="[]")):
            with self.assertRaises(SystemExit):
                procutils.unload_llm()

    def test_live_lock_not_stolen_by_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = procutils.PipelineLock(name="fixture")
            lock.path = Path(tmp) / "fixture.lock"
            atomic_text(lock.path, "{}")
            os.utime(lock.path, (1, 1))
            self.assertFalse(lock._stale({"pid": os.getpid()}))

    def test_failure_resume_and_done_skip_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            atomic_text(d / "source.md", "# Test\n\nA source paragraph.")
            root = d / "job"
            p.initialize(d / "source.md", root)
            def cmds(fail):
                return [("one", [sys.executable, "-c", "from pathlib import Path; Path('one').write_text('ok')"], None),
                        ("two", [sys.executable, "-c", "raise SystemExit(3)" if fail else "from pathlib import Path; Path('two').write_text('ok')"], None)]
            with patch.object(p, "PipelineLock"), patch.object(p, "outputs_for", side_effect=lambda r, n, _: p.fingerprints(r, [r / n])):
                with patch.object(p, "steps_for", return_value=cmds(True)):
                    self.assertEqual(p.run_job(root), 3)
                self.assertEqual(p.status(root)["status"], "needs_attention")
                first = (root / "one").stat().st_mtime_ns
                with patch.object(p, "steps_for", return_value=cmds(False)):
                    self.assertEqual(p.run_job(root), 0)
                self.assertEqual((root / "one").stat().st_mtime_ns, first)
                self.assertEqual(p.status(root)["status"], "done")
                with patch.object(p.subprocess, "Popen", side_effect=AssertionError("done must not launch")):
                    self.assertEqual(p.run_job(root), 0)
                atomic_text(root / "two", "tampered")
                self.assertEqual(p.status(root)["status"], "stale")

    def test_timeout_is_bounded_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            atomic_text(d / "source.md", "Text")
            root = d / "job"
            p.initialize(d / "source.md", root, {"timeout": 1})
            steps = [("hang", [sys.executable, "-c", "import time; time.sleep(60)"], None)]
            with patch.object(p, "PipelineLock"), patch.object(p, "steps_for", return_value=steps):
                self.assertEqual(p.run_job(root), 1)
            self.assertEqual(p.status(root)["status"], "needs_attention")
            self.assertIn("timeout", p.status(root)["reason"])
            self.assertNotIn("child_pid", p.read(root / p.STATE))

    def test_live_child_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            atomic_text(d / "source.md", "Text")
            root = d / "job"
            p.initialize(d / "source.md", root)
            state = p.read(root / p.STATE)
            state.update(status="running", pid=987654, started=1,
                         child_pid=os.getpid(), child_started=p.process_stamp(os.getpid()))
            write_json(root / p.STATE, state)
            self.assertEqual(p.status(root)["next_action"], "inspect_live_child")
            with self.assertRaises(ValueError):
                p.run_job(root)

    def test_cheap_omission_gates(self):
        source = "Text α) quality (§. 98.) β) quantity (§. 105.) γ) relation [^n]."
        target = "Текст α) качество (§. 98.) β) количество (§. 105.) γ) отношение [^n]."
        self.assertTrue(validate_candidate(source, target).ok)
        for bad in (target.replace("105", "106"), target.replace("β)", ""), target.replace("[^n]", "")):
            self.assertFalse(validate_candidate(source, bad).ok)
        self.assertTrue(validate_candidate("Value 3.14.", "Значение 3,14.").ok)

    def test_loopback_only_and_explicit_remote(self):
        for url in ("http://localhost:1234", "http://127.0.0.1:8080/v1", "http://[::1]:8080"):
            self.assertEqual(validate_endpoint(url), url)
        for url in ("http://localhost.evil.test", "https://example.com/v1", "http://192.168.1.1:8080", "http://user:pass@localhost", "http://localhost/?key=x"):
            with self.assertRaises(ValueError):
                validate_endpoint(url)
        self.assertEqual(validate_endpoint("https://example.com/v1", True), "https://example.com/v1")

    def test_redirect_escape_refused_before_transport(self):
        with patch.dict(os.environ, FREETRANSLATE_LOCAL_ONLY="1"):
            with self.assertRaises(ValueError):
                Guard().redirect_request(Request("http://localhost:1234"), None, 307, "redirect", {}, "https://example.com/")
            with self.assertRaises(ValueError):
                model_opener().open("https://example.com/", timeout=1)

    def test_strict_settings(self):
        for cfg in ({"allow_remote": "false"}, {"polish": True}, {"force": True}, {"parallel": 0}, {"timeout": -1}, {"mode": "polish"}):
            with self.assertRaises(ValueError):
                p.validate_settings(cfg, "books")

    def test_single_book_isolated_and_no_polish(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = d / "book.md"
            atomic_text(src, "# Force\n\nForce $F=ma$.\n")
            root = d / "job"
            job = p.initialize(src, root)
            cmd = p.steps_for(root, job)[0][1]
            self.assertIn("translate_book.py", " ".join(cmd))
            self.assertNotIn("--polish", cmd)
            self.assertNotIn("--auto-glossary", cmd)
            self.assertNotIn("--force", cmd)
            self.assertNotIn(str(src), cmd)
            self.assertEqual(p.status(root)["status"], "ready")
            atomic_text(src, "changed original, snapshot still stable")
            p.load_job(root)
            atomic_text(root / "input/book-001/book.md", "changed snapshot")
            with self.assertRaises(ValueError):
                p.load_job(root)

    def test_folder_does_not_translate_its_manuals(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "books").mkdir()
            for name in ("one.pdf", "README.md", "glossary.md", "one.ru.pdf"):
                atomic_text(d / "books" / name, "fixture")
            job = p.initialize(d / "books", d / "job")
            self.assertEqual([r["name"] for r in job["books"]], ["one.pdf"])
            with self.assertRaises(ValueError):
                p.initialize(d / "books", d / "job")

    def test_ocr_routes_and_context_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            atomic_text(d / "ocr/pages/p0001.txt", "Der Begriff.")
            write_json(d / "ocr/structure.json", {})
            atomic_text(d / "ocr/final.pdf", "DO NOT TOUCH")
            job = p.initialize(d / "ocr", d / "job", {"mode": "generic"})
            steps = p.steps_for(d / "job", job)
            self.assertEqual([r[0] for r in steps], ["prepare", "translate", "build"])
            self.assertIn("generic", steps[1][1])
            self.assertEqual(job["settings"]["source_lang"], "German")
            self.assertFalse((d / "job/input/final.pdf").exists())

    def test_skeleton_is_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            atomic_text(d / "sk/book/main.tex", "fixture")
            atomic_text(d / "sk/source.pdf", "fixture")
            job = p.initialize(d / "sk", d / "job")
            step = p.steps_for(d / "job", job)[0]
            self.assertEqual(step[0], "skeleton")
            self.assertEqual(step[2], d / "job/work/book/main.pdf")
            self.assertNotIn(str(d / "sk"), step[1])

    def test_last_block_ledger_lf_crlf_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for eol in ("\n", "\r\n"):
                text = eol.join(["", "Titel", "", "Der letzte Satz.", ""])
                (d / "book.md").write_bytes(text.encode())
                manifest = {"manifest_sha256": "fixture"}
                ledger = {"schema": 1, **manifest, "findings": [{"id": "last", "source_sha256": sha_text("Der letzte Satz."),
                          "source_quote": "letzte Satz", "status": "resolved", "resolution": "checked scan"}]}
                write_json(d / "editorial.findings.json", ledger)
                self.assertEqual(blocks_of(d / "book.md"), split_blocks((d / "book.md").read_text(encoding="utf-8")))
                self.assertEqual(review_ledger(d, manifest, blocks_of(d / "book.md"))["status"], "passed")
                with self.assertRaises(ValueError):
                    review_ledger(d, manifest, ["Titel", "Der erste Satz."])
                ledger["findings"][0]["status"] = "unresolved"
                write_json(d / "editorial.findings.json", ledger)
                self.assertEqual(review_ledger(d, manifest, blocks_of(d / "book.md"))["status"], "failed")

    def test_hyphen_conjunction_is_not_midword(self):
        for tail in ("und Wesenloses", "oder Wesenloses", "bzw. Wesenloses"):
            self.assertEqual(join_hyphen("Halt-", tail), "Halt- " + tail)
        self.assertEqual(join_hyphen("dar-", "unter"), "darunter")
        self.assertEqual(join_hyphen("Aus-", "druck"), "Ausdruck")
        self.assertEqual(join_hyphen("Selbst-", "Bestimmung"), "Selbst-Bestimmung")


if __name__ == "__main__":
    unittest.main()
