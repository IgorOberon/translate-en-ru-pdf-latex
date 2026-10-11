"""Synthetic regressions for complex OCR, unit boundaries and editorial release gates."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_ocr_md as ocr
import agent_exchange as exchange
import assemble_ru_book as assembler
from editorial import ocr_findings, source_review, review_ledger
from provenance import sha_text, write_json, create_manifest, atomic_text
from translate import validate_candidate, ValidationPolicy
from request_plan import plan_fragments
from measure_build import pdf_metrics
from layout_report import scan_log
from accept_fraktur import Report, check_translation_hygiene


class ComplexOCR(unittest.TestCase):
    def test_suspect_ocr_warns_without_rewriting(self):
        source = 'Text == prose =-- prose =“ more [ Sagen wir 3. B. durch sein. Inneres.'
        kinds = {r['kind'] for r in ocr_findings(source)}
        self.assertTrue({'ocr-dash-noise', 'ocr-abbreviation', 'suspect-internal-stop',
                         'unbalanced-square-bracket'} <= kinds)
        self.assertEqual(source_review([source], {'ocr_review': {'strict': True}})['status'], 'failed')
        self.assertIn('3. B.', source)

    def test_math_code_footnotes_not_ocr_garbage(self):
        self.assertFalse(ocr_findings('Equation $a==b$ and `[x == y` and [^n].'))
        self.assertFalse(ocr_findings('A normal [link](https://example.com).'))

    def test_long_quotation_needs_review_not_truncation(self):
        source = 'Intro „' + 'A real or OCR quotation. ' * 60 + '“ End.'
        self.assertIn('long-quoted-span', {r['kind'] for r in ocr_findings(source)})
        planned = plan_fragments(source, 100)
        self.assertEqual(''.join(f['text'] for f in planned), source)
        self.assertTrue(any(f['oversized'] for f in planned))

    def test_ocr_boundaries_kept_together(self):
        for source in ['Sagen wir 3. B. eine Aussage. Noch ein Satz.',
                       'Nur vermittelt durch sein. Inneres. Noch ein Satz.']:
            plan = plan_fragments(source, 12)
            self.assertEqual(''.join(f['text'] for f in plan), source)
            self.assertFalse(any(f['text'].rstrip().endswith(('3.', 'sein.')) for f in plan[:-1]))

    def test_added_ellipsis_rejected_even_with_length_check_off(self):
        p = ValidationPolicy(reject_echo=False)
        self.assertFalse(validate_candidate('A complete sentence.', 'Полная … фраза.', p).ok)
        self.assertFalse(validate_candidate('A complete sentence.', 'Полная ... фраза.', p).ok)
        self.assertTrue(validate_candidate('An original ... pause.', 'Исходная … пауза.', p).ok)
        self.assertTrue(validate_candidate('A complete sentence.', 'Полная фраза.', p).ok)

    def test_unit_anchor_identity_and_nonmerging(self):
        raw = 'Main text without punctuation Remark begins here.'
        rows = [{'kind': 'para', 'page': 9, 'text': raw}]
        rule = {'id': 'remark-1', 'page': 9, 'anchor': 'Remark begins', 'type': 'remark',
                'source_sha256': sha_text(raw), 'reason': 'scan checked'}
        out, journal = ocr.apply_unit_anchors(rows, raw, 9, [rule])
        out = ocr.merge_split_paragraphs(ocr.assign_units(out))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]['unit'], 'remark')
        self.assertEqual(journal[0]['unit_id'], 'remark-1')
        self.assertEqual(' '.join(r['text'] for r in out), raw)
        with self.assertRaises(ValueError):
            ocr.apply_unit_anchors(rows, raw + '!', 9, [rule])

    def test_paragraph_anchor_stops_merge_without_inventing_heading(self):
        raw = 'First unfinished New paragraph.'
        rule = {'id': 'paragraph', 'page': 1, 'anchor': 'New paragraph', 'type': 'paragraph',
                'source_sha256': sha_text(raw), 'reason': 'indentation verified'}
        out, _ = ocr.apply_unit_anchors([{'kind': 'para', 'page': 1, 'text': raw}], raw, 1, [rule])
        self.assertEqual(len(ocr.merge_split_paragraphs(out)), 2)
        self.assertNotIn('unit', out[1])

    def test_page_coverage_does_not_move_to_next_heading(self):
        blocks = ['<!--20-->', 'Previous paragraph.', '<!--21-->', '# Next division', 'New paragraph.']
        layout = {'1': {'pages': [20, 21], 'unit': 'remark'}, '4': {'pages': [22]}}
        md = assembler.to_markdown(blocks, layout=layout)
        self.assertLess(md.index('с.~20--21'), md.index('Previous paragraph'))
        self.assertLess(md.index('Previous paragraph'), md.index('# Next division'))
        self.assertGreater(md.index('с.~22'), md.index('# Next division'))
        self.assertNotIn('с.~21}', md)
        self.assertIn('\\begin{quote}\\small', md)
        self.assertIn('Previous paragraph.', md)

    def test_ledger_rejects_stale_and_unresolved_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = 'A source sentence to verify.'
            manifest = {'manifest_sha256': 'identity'}
            row = {'id': 'r1', 'source_sha256': sha_text(text), 'source_quote': 'source sentence',
                   'status': 'unresolved'}
            ledger = {'schema': 1, **manifest, 'findings': [row]}
            write_json(root / 'editorial.findings.json', ledger)
            self.assertEqual(review_ledger(root, manifest, [text])['status'], 'failed')
            row.update(status='resolved', resolution='scan and rendering checked')
            write_json(root / 'editorial.findings.json', ledger)
            self.assertEqual(review_ledger(root, manifest, [text])['status'], 'passed')
            with self.assertRaises(ValueError):
                review_ledger(root, manifest, [text + ' changed'])
            with self.assertRaises(ValueError):
                review_ledger(root, {'manifest_sha256': 'other'}, [text])

    def test_agent_uncertainty_must_quote_the_claimed_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('book.md', 'book.part1.md'):
                atomic_text(root / name, 'A source sentence.\n\nAnother source paragraph.')
            create_manifest(root)
            bundle = exchange.export_requests(root, model='test')
            key = bundle['requests'][0]['id']
            answers = {'uncertainties': [{'id': key, 'source_quote': 'Another source', 'note': 'bad mapping'}]}
            with self.assertRaises(ValueError):
                exchange.findings_from_answers(root, bundle, answers)
            answers['uncertainties'][0]['source_quote'] = 'source sentence'
            result = exchange.findings_from_answers(root, bundle, answers)
            self.assertEqual(result['findings'][0]['status'], 'unresolved')
            write_json(root / 'editorial.findings.json', result)
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                exchange.export_requests(root, model='test')

    def test_pdf_metrics_returns_actual_page_count(self):
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'two.pdf'
            with fitz.open() as doc:
                doc.new_page()
                doc.new_page()
                doc.save(pdf)
            self.assertEqual(pdf_metrics(pdf)['pages'], 2)

    def test_wrapped_tex_output_page_count(self):
        self.assertEqual(scan_log('Output written on main.pdf\n(6 pages, 10000 bytes).')[0], 6)

    def test_release_hygiene_rejects_old_ellipsis_output(self):
        report = Report()
        check_translation_hygiene([('A full phrase.', 'Полная … фраза.')], report)
        self.assertIn('added ellipses', [name for name, _ in report.gates])

    def test_missing_or_duplicate_unit_anchor_refuses(self):
        raw = 'Repeated phrase. Repeated phrase.'
        rule = {'id': 'bad', 'page': 1, 'anchor': 'Repeated phrase', 'type': 'remark',
                'source_sha256': sha_text(raw), 'reason': 'test ambiguity'}
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            ocr.apply_unit_anchors([{'kind': 'para', 'page': 1, 'text': raw}], raw, 1, [rule])


if __name__ == '__main__':
    unittest.main()
