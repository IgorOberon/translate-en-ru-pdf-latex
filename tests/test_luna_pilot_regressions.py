"""Regressions from the real §§84–85 pilot; no live model or private book files."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_ocr_md as ocr
from provenance import sha_text
from editorial import ocr_findings, source_review, term_guard_findings
import provenance as pv
import agent_exchange as exchange
import run_doc_translate as runner
from translate import build_messages, split_blocks
from request_plan import plan_fragments


class OCRPilot(unittest.TestCase):
    def test_sentence_dash_is_not_a_word_hyphen(self):
        self.assertEqual(ocr.join_lines(["Zum Wesen. —", "Die nächste Aussage."]),
                         "Zum Wesen. — Die nächste Aussage.")
        self.assertEqual(ocr.join_lines(["Das sinn-", "liche Bewußtseyn."]),
                         "Das sinnliche Bewußtseyn.")

    def test_unit_line_flushes_buffer(self):
        rows = ocr.page_items("Der erste Absatz endet.\nZusatz. Ein neuer Absatz.\nSeine Fortsetzung.", 1, False)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1]["text"].startswith("Zusatz."))

    def test_unit_can_continue_over_page_hyphen(self):
        rows = [{"kind": "para", "page": 1, "text": "Zusatz. Das sinn-"},
                {"kind": "para", "page": 2, "text": "liche Bewußtseyn."}]
        out = ocr.merge_split_paragraphs(rows)
        self.assertEqual(len(out), 1)
        self.assertIn("sinnliche", out[0]["text"])
        self.assertEqual(out[0]["extra_pages"], [2])

    def test_unit_does_not_absorb_a_new_unit(self):
        rows = [{"kind": "para", "page": 1, "text": "Zusatz. unfinished-"},
                {"kind": "para", "page": 2, "text": "Anmerkung. New unit."}]
        self.assertEqual(len(ocr.merge_split_paragraphs(rows)), 2)

    def test_early_fixes_allow_unit_segmentation(self):
        raw = "Der Satz endet.\nZufſaß. Der neue Satz."
        prepared, log = ocr.prepare_ocr_page(raw, 8, {"word_fixes": {"Zufsaß": "Zusatz"}})
        self.assertEqual(len(ocr.page_items(prepared, 8, False, source_raw=raw)), 2)
        self.assertEqual(log[0]["line"], 2)
        self.assertEqual(log[0]["old"], "Zufsaß")

    def test_checked_ocr_correction_not_global_guess(self):
        raw = "vgl. 5. 31."
        rule = {"id": "ref", "page": 1, "source_sha256": sha_text(raw),
                "old": "5. 31.", "new": "§. 31.", "reason": "scan inspected"}
        self.assertEqual(ocr.prepare_ocr_page(raw, 1, {"ocr_corrections": [rule]})[0], "vgl. §. 31.")
        with self.assertRaises(ValueError):
            ocr.prepare_ocr_page(raw + " changed", 1, {"ocr_corrections": [rule]})
        self.assertEqual(ocr.prepare_ocr_page(raw, 1, {})[0], raw)

    def test_duplicate_alias_only_adjacent_and_explicit(self):
        head = {"kind": "head", "level": 1, "page": 1, "text": "A confirmed title",
                "ocr_aliases": ["OCR title"]}
        paragraphs = [{"kind": "para", "page": 1, "text": s}
                      for s in ["OCR title", "Actual prose.", "OCR title"]]
        out = ocr.place_headings([head], paragraphs, 1)
        self.assertEqual([r["text"] for r in out], ["A confirmed title", "Actual prose.", "OCR title"])
        self.assertEqual(head["consumed_ocr_aliases"][0]["text"], "OCR title")

    def test_ocr_warnings_keep_footnotes_and_math(self):
        self.assertFalse(ocr_findings("*emphasis* $a * b$ `--+` *) footnote"))
        text = "Text * stray ' --+ vgl. 5. 31."
        kinds = {r["kind"] for r in ocr_findings(text)}
        self.assertTrue({"stray-star", "isolated-apostrophe", "mixed-dash-plus", "ambiguous-reference"} <= kinds)
        self.assertEqual(source_review([text], {"ocr_review": {"strict": True}})["status"], "failed")
        self.assertEqual(source_review([text], {})["status"], "warning")

    def test_term_guards_detect_confusion_without_replacement(self):
        rules = [{"id": "contrast", "source_pattern": "für sich unbestimmtes",
                  "required_target_pattern": "сам по себе|для себя",
                  "forbidden_target_pattern": "неопредел[её]нным в себе"}]
        source, target = "ein für sich unbestimmtes Substrat", "неопределённым в себе субстратом"
        self.assertEqual(len(term_guard_findings(source, target, rules)), 1)
        self.assertFalse(term_guard_findings(source, "сам по себе неопределённый субстрат", rules))
        self.assertFalse(term_guard_findings("another context", target, rules))
        self.assertEqual(target, "неопределённым в себе субстратом")

    def test_exact_agent_export_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = "First source line.\r\nSecond source line.\r\n\r\nAnother block."
            for name in ("book.md", "book.part1.md"):
                (root / name).write_bytes(raw.encode("utf-8"))
            pv.create_manifest(root)
            data = exchange.export_requests(root, model="test", split_chars=900)
            expected = [build_messages(f["text"], "hymt", "Russian", "", source_lang="German")
                        for b in split_blocks(raw) for f in plan_fragments(b, 900)]
            self.assertEqual([r["messages"] for r in data["requests"]], expected)
            self.assertTrue(any("\r\n" in r["source"] for r in data["requests"]))
            with self.assertRaises(ValueError):
                exchange.export_requests(root, model="test", glossary=root / "missing.md")

    def test_export_rejects_unmasked_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("book.md", "book.part1.md"):
                pv.atomic_text(root / name, "The equation $a+b$ is protected.")
            pv.create_manifest(root)
            with self.assertRaisesRegex(ValueError, "unmasked"):
                exchange.export_requests(root, model="test")

    def test_strict_ocr_review_blocks_before_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("book.md", "book.part1.md"):
                pv.atomic_text(root / name, "Meaningful prose --+ with an OCR artifact.")
            pv.write_json(root / "structure.json", {"ocr_review": {"strict": True}})
            pv.create_manifest(root)
            with self.assertRaisesRegex(ValueError, "strict OCR review"):
                exchange.export_requests(root, model="test")
            with patch.object(sys, "argv", ["run_doc", str(root)]), patch.object(runner.subprocess, "run") as api:
                self.assertEqual(runner.main(), 5)
                api.assert_not_called()

    def test_review_waiver_is_bound_to_block(self):
        text = "Text * an actual source marker."
        cfg = {"ocr_review": {"strict": True, "waivers": [
            {"kind": "stray-star", "source_sha256": sha_text(text), "reason": "verified original marker"}]}}
        self.assertEqual(source_review([text], cfg)["status"], "passed")
        self.assertEqual(source_review([text + " changed"], cfg)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
