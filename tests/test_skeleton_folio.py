#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for folio-based chapter location in the skeleton orchestrator:
page_folio, build_folio_map (отсев мусорных номеров), locate_chapter
(дрейф офсета через страницы-разделители, инвариант длины), slice_pdf
(p0<0, контрольный зонд среза, кэшированная нарезка). Exit 1 on failure."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skeleton"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import pymupdf
except ImportError:
    print("SKIP (pymupdf недоступен — тесты folio требуют venv конвейера)")
    sys.exit(0)

import translate_into_skeleton as sk  # noqa: E402

CHECKS = []


def check(name, ok, extra=""):
    print(("PASS" if ok else "FAIL"), name)
    if not ok and extra:
        print("   ", extra)
    CHECKS.append(ok)


class FakePage:
    def __init__(self, text):
        self._t = text

    def get_text(self):
        return self._t


def make_pdf(path, folios):
    """PDF, где страница i несёт печатный номер folios[i] (None = без номера)."""
    doc = pymupdf.open()
    for f in folios:
        page = doc.new_page()
        if f is not None:
            page.insert_text((300, 40), str(f))
            page.insert_text((72, 100), "Обычный текст страницы для объёма.")
    doc.save(path)
    doc.close()


def test_page_folio():
    check("page_folio: одиночное число в первых строках",
          sk.page_folio(FakePage("Заголовок\n33\nтекст")) == 33)
    check("page_folio: таб-формат «RunningHead\\tNNN»",
          sk.page_folio(FakePage("Chapter 1 Newton's Laws \t123 \nтекст")) == 123)
    check("page_folio: страница без номера -> None",
          sk.page_folio(FakePage("просто текст\nбез числа")) is None)


def test_folio_map_and_locate():
    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / "book.pdf"
    # idx:    0   1   2   3(шмуцтитул «8»)  4   5   6
    # часть 1: folio 10-12; разделитель без счёта; часть 2: folio 13-15
    make_pdf(pdf, [10, 11, 12, 8, 13, 14, 15])
    doc = pymupdf.open(pdf)
    fmap = sk.build_folio_map(doc)
    check("folio_map: последовательные номера приняты",
          fmap.get(10) == 0 and fmap.get(12) == 2 and fmap.get(13) == 4,
          str(fmap))
    check("folio_map: одинокое «8» шмуцтитула отброшено", 8 not in fmap,
          str(fmap))

    loc = sk.locate_chapter(fmap, 10, 12, "ch01")
    check("locate: глава до разделителя", loc == (0, 2, -9), str(loc))
    loc2 = sk.locate_chapter(fmap, 13, 15, "ch02")
    check("locate: глава после разделителя (офсет сдвинулся)",
          loc2 == (4, 6, -8), str(loc2))
    check("locate: дрейф офсета виден", loc[2] != loc2[2])
    check("locate: нет folio в диапазоне -> None",
          sk.locate_chapter(fmap, 900, 950) is None)

    try:
        sk.locate_chapter({10: 0, 12: 4}, 10, 12, "chX")
        check("locate: вставные страницы внутри главы -> RuntimeError", False)
    except RuntimeError:
        check("locate: вставные страницы внутри главы -> RuntimeError", True)


def test_slice_pdf():
    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / "book.pdf"
    make_pdf(pdf, [10, 11, 12, 13, 14])

    out = tmp / "ok" / "pages.pdf"
    sk.slice_pdf(pdf, 11, 13, 1, 3, out)
    d = pymupdf.open(out)
    check("slice: нарезано 3 страницы, первая несёт folio 11",
          d.page_count == 3 and sk.page_folio(d[0]) == 11)
    d.close()
    sk.slice_pdf(pdf, 11, 13, 1, 3, out)      # кэш + зонд, не падает
    check("slice: кэшированная нарезка с верными folio принята", True)

    try:
        sk.slice_pdf(pdf, 5, 7, -2, 0, tmp / "neg" / "pages.pdf")
        check("slice: p0 < 0 -> брак", False)
    except SystemExit:
        check("slice: p0 < 0 -> брак", True)

    try:
        sk.slice_pdf(pdf, 50, 52, 0, 2, tmp / "bad" / "pages.pdf")
        check("slice: зонд ловит несоответствие folio", False)
    except SystemExit:
        check("slice: зонд ловит несоответствие folio", True)

    try:
        sk.slice_pdf(pdf, 50, 52, 1, 3, out)   # кэш с чужими folio
        check("slice: кэшированная нарезка с чужими folio бракуется", False)
    except SystemExit:
        check("slice: кэшированная нарезка с чужими folio бракуется", True)

    sk.slice_pdf(pdf, 50, 52, 0, 2, tmp / "off" / "pages.pdf", probe=False)
    check("slice: probe=False (--folio off) не сверяет", True)


def test_no_text_layer():
    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / "scan.pdf"
    make_pdf(pdf, [None, None, None])
    doc = pymupdf.open(pdf)
    check("folio_map: скан без текстового слоя -> пустая карта",
          sk.build_folio_map(doc) == {})
    out = tmp / "s" / "pages.pdf"
    sk.slice_pdf(pdf, 1, 3, 0, 2, out)
    ok, _ = sk.probe_slice(out, 1, 3)
    check("probe_slice: нет folio -> None (не проверить), не брак", ok is None)


def main():
    test_page_folio()
    test_folio_map_and_locate()
    test_slice_pdf()
    test_no_text_layer()
    failed = CHECKS.count(False)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
