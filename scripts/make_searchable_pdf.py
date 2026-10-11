# -*- coding: utf-8 -*-
"""Скан без текстового слоя -> тот же скан, но с распознанным слоем.

Изображения оригинала не трогаются: под них подкладывается невидимый
(render mode 3) текст по словам, взятый из Tesseract. Внешний вид страницы
остаётся прежним, но по книге работают поиск, выделение и копирование.

Почему не `tesseract -c textonly_pdf=1`, который умеет то же самое: он кладёт
в слой СЫРОЕ распознавание. Во фрактуре это значит длинное «ſ» — и поиск по
«Wissenschaft» не находит «Wiſſenſchaft», то есть слой почти бесполезен. Здесь
слово перед укладкой прогоняется через нормализацию build_ocr_md (ſ, лигатуры
ch/ck, I/J) и через частотный фикс длинного s, поэтому искать можно так, как
слово пишется сегодня. Координаты при этом берутся из того же Tesseract
(TSV с рамками слов), так что выделение попадает по месту.

Использование:
    python scripts/make_searchable_pdf.py <вход.pdf> <выход.pdf>
        [--png-dir DIR] [--lang deu_latf] [--jobs 4] [--dpi 300]
        [--no-normalize] [--keep-tsv DIR]
"""
import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ocr_md as B  # noqa: E402  (нормализация фрактуры живёт там)

# Невидимый слой набирается базовым Helvetica: он не встраивается и ничего не
# весит, но покрывает только Latin-1. Типографику приводим к нему, остальное
# выбрасываем — на поиск это не влияет.
SANITIZE = {
    "„": '"', "“": '"', "”": '"', "‟": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "–": "-", "—": "-", "‐": "-", "‑": "-", "‒": "-", "⸗": "-",
    "•": ".", "·": ".", "…": "...", "ſ": "s",
}


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import tesseract  # noqa: E402


def to_latin1(word):
    out = []
    for ch in word:
        ch = SANITIZE.get(ch, ch)
        if ch == "":
            continue
        if ord(ch) < 256:
            out.append(ch)
    return "".join(out)


# Словарь правок построен по ЧИСТЫМ словоформам (WORD_RE без пунктуации),
# а в слое слово приходит с точкой/запятой. Срежем пунктуационный хвост,
# найдём правку и вернём хвост на место.
PUNCT_TAIL = re.compile(r"([.,;:!?…–—\-()\[\]\"'«»„”“]+)$")


def apply_mapping(text, mappings):
    """Две карты каскадом: сначала длинное s (f->s), потом лигатура tz (ß->tz).
    «Zufaß.» -> «Zusaß» (первая) -> «Zusatz» (вторая)."""
    for mapping in mappings:
        m = PUNCT_TAIL.search(text)
        if m:
            text = mapping.get(text[:m.start()], text[:m.start()]) + m.group(1)
        else:
            text = mapping.get(text, text)
    return text


def run_tsv(tesseract, png, stem, lang, psm):
    r = subprocess.run([tesseract, png, stem, "-l", lang, "--psm", str(psm),
                        "tsv"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"tesseract rc={r.returncode}: {r.stderr[:200]}")
    return stem + ".tsv"


def read_words(tsv_path, min_conf=0):
    """[(left, top, width, height, text)] — только уровень слова."""
    words = []
    with open(tsv_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            try:
                if int(row["level"]) != 5:
                    continue
                conf = float(row["conf"])
            except (KeyError, TypeError, ValueError):
                continue
            text = (row.get("text") or "").strip()
            if conf < min_conf or not text:
                continue
            try:
                words.append((int(row["left"]), int(row["top"]),
                              int(row["width"]), int(row["height"]), text))
            except (TypeError, ValueError):
                continue
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_pdf")
    ap.add_argument("out_pdf")
    ap.add_argument("--png-dir", default=None,
                    help="готовые pNNNN.png; иначе страницы рендерятся сами")
    ap.add_argument("--lang", default="deu_latf")
    ap.add_argument("--psm", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--tesseract", default=tesseract())
    ap.add_argument("--min-conf", type=float, default=0)
    ap.add_argument("--no-normalize", action="store_true",
                    help="класть сырое распознавание (с «ſ»), как есть")
    ap.add_argument("--keep-tsv", default=None,
                    help="куда сложить .tsv (по умолчанию временная папка)")
    a = ap.parse_args()

    doc = fitz.open(a.src_pdf)
    n = doc.page_count

    # Входной PDF бывает НЕ чистым сканом, а уже с чужим текстовым слоем
    # (Google Books OCR с «ſ»). Слой невидим, но копируется и ломает поиск:
    # его слова живут рядом с нашими, при копировании текст двоится.
    # Признак — извлекаемый текст: у чистого скана страницы пусты.
    #
    # Снимаем чужой слой РЕДАКТИРОВАНИЕМ: текст удаляется, изображения и
    # штриховая графика остаются нетронутыми. Пересобирать страницы из
    # отрисованных PNG нельзя — это теряет разрешение оригинала: на
    # Энциклопедии II полоса 3062x5150 превращалась в 377x634 (shrink(2)
    # делит не вдвое, а вчетверо) плюс JPEG, и файл при этом РОС с 19 до
    # 43 МБ. Чистка даёт 15.6 МБ при исходном разрешении, за 4 секунды.
    if any(page.get_text().strip() for page in doc):
        print(f"{os.path.basename(a.src_pdf)}: есть чужой текстовый слой — "
              f"снимаю его, изображения не трогаю", flush=True)
        for page in doc:
            page.add_redact_annot(page.rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
        left = sum(len(doc[i].get_text().strip())
                   for i in range(0, n, max(1, n // 20)))
        if left:
            print(f"!! после чистки остался текст ({left} знаков в выборке) — "
                  f"поиск будет двоиться, разберитесь", flush=True)
        else:
            print("   чужой слой снят полностью", flush=True)

    work = a.keep_tsv or tempfile.mkdtemp(prefix="searchable_")
    os.makedirs(work, exist_ok=True)
    png_work = os.path.join(work, "_png")
    if not a.png_dir:
        os.makedirs(png_work, exist_ok=True)

    print(f"{os.path.basename(a.src_pdf)}: {n} стр., OCR в TSV "
          f"(модель {a.lang}, jobs {a.jobs})", flush=True)

    def one(i):
        stem = os.path.join(work, f"p{i+1:04d}")
        tsv = stem + ".tsv"
        if os.path.exists(tsv) and os.path.getsize(tsv) > 0:
            return i, tsv
        if a.png_dir:
            png = os.path.join(a.png_dir, f"p{i+1:04d}.png")
            if not os.path.exists(png):
                raise FileNotFoundError(png)
        else:
            png = os.path.join(png_work, f"p{i+1:04d}.png")
            if not os.path.exists(png):
                doc[i].get_pixmap(dpi=a.dpi).save(png)
        return i, run_tsv(a.tesseract, png, stem, a.lang, a.psm)

    tsvs = {}
    done = 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(one, i) for i in range(n)]
        for fut in as_completed(futs):
            i, tsv = fut.result()
            tsvs[i] = tsv
            done += 1
            if done % 50 == 0 or done == n:
                print(f"  TSV {done}/{n}", flush=True)

    pages = {i: read_words(tsvs[i], a.min_conf) for i in range(n)}
    total_words = sum(len(w) for w in pages.values())
    print(f"распознано слов: {total_words}", flush=True)

    # Карта правок длинного s строится по ВСЕЙ книге: одиночное слово о своих
    # частотах ничего не знает, а именно они отличают «fich» -> «sich» от
    # настоящего немецкого слова на f.
    mapping = {}
    if not a.no_normalize:
        corpus = " ".join(B.normalize(w[4]) for ws in pages.values() for w in ws)
        _, _, mapping = B.fix_long_s(corpus)
        print(f"частотных правок длинного s в карте: {len(mapping)}", flush=True)
        # tz-карту строим по УЖЕ исправленному корпусу: «Zufaß.» (f вместо ſ)
        # после s-карты станет «Zusaß», и только тогда tz-карта его увидит.
        corpus_s, _, _ = B.fix_long_s(corpus)
        _, _, tz_mapping = B.fix_tz_ligature(corpus_s)
        print(f"правок лигатуры tz в карте: {len(tz_mapping)}", flush=True)

    placed, skipped, empty_pages = 0, 0, 0
    font = fitz.Font("helv")
    for i in range(n):
        page = doc[i]
        words = pages[i]
        if not words:
            empty_pages += 1
            continue
        # пиксель растра -> пункт страницы; повороты у этих сканов нулевые
        # (проверено), иначе пришлось бы разворачивать координаты
        sx = sy = 72.0 / a.dpi
        # TextWriter копит всю страницу и пишет её ОДНИМ потоком. Через
        # page.insert_text() на слово выходило 105 тысяч отдельных дописок в
        # содержимое: сохранение ползло минутами, а файл раздувался вдвое.
        tw = fitz.TextWriter(page.rect)
        page_has_text = False
        for left, top, w, h, text in words:
            if not a.no_normalize:
                text = B.normalize(text)
                text = apply_mapping(text, [mapping, tz_mapping])
            text = to_latin1(text).strip()
            if not text:
                skipped += 1
                continue
            x0, y0 = left * sx, top * sy
            bw, bh = w * sx, h * sy
            unit = font.text_length(text, fontsize=1)
            if unit <= 0 or bw <= 0 or bh <= 0:
                skipped += 1
                continue
            # кегль подбираем по ширине рамки: тогда выделение слова в
            # читалке совпадает с самим словом на скане
            fs = max(1.0, min(bw / unit, bh * 1.6))
            try:
                # пробел в конце — чтобы при копировании слова не слипались
                # («die Größeist zuerst»): извлекатель ставит пробел по
                # геометрии, а рамки здесь стоят вплотную
                tw.append((x0, y0 + bh * 0.82), text + " ",
                          font=font, fontsize=fs)
                placed += 1
                page_has_text = True
            except Exception:
                skipped += 1
        if page_has_text:
            tw.write_text(page, render_mode=3, overlay=True)

    doc.set_metadata({
        "title": os.path.splitext(os.path.basename(a.out_pdf))[0],
        "creator": "make_searchable_pdf.py (Tesseract %s + PyMuPDF)" % a.lang,
        "producer": "PyMuPDF",
    })
    os.makedirs(os.path.dirname(os.path.abspath(a.out_pdf)), exist_ok=True)
    doc.save(a.out_pdf, garbage=3, deflate=True)
    doc.close()

    print(f"уложено слов: {placed}, пропущено: {skipped}, "
          f"страниц без текста: {empty_pages}", flush=True)
    print(f"готово: {a.out_pdf} "
          f"({os.path.getsize(a.out_pdf) / 1024 / 1024:.1f} МБ)", flush=True)
    if not a.keep_tsv:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
