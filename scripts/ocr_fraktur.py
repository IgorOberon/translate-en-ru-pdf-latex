r"""OCR пайплайн для немецкой фрактуры (XIX век).

Рендер страниц PDF в 300 dpi -> Tesseract -> постраничные .txt.
Параллельный, возобновляемый.

ВАЖНО о модели. По умолчанию берётся deu_latf — современная LSTM-модель
Tesseract 4/5 для фрактуры. Старая deu_frak (наследие Tesseract 3) на этом
материале заметно хуже: на выборке из 22 страниц Гегеля 1812 г. она
восстановила 316 терминов книги против 400 у deu_latf, путая целые слова
("Continuität" -> "Epntinuität"). Не ставьте deu_frak без замера.

Сборкой book.md занимается scripts/build_ocr_md.py: нормализация длинного s,
склейка переносов и абзацев через границы страниц, распознавание заголовков.
Разделение сделано намеренно — OCR медленный и одноразовый, а сборку
приходится переигрывать.

Использование:
    # обычный путь: PDF -> PNG -> текст
    python scripts/ocr_fraktur.py <input.pdf> <out_dir> [--dpi 300] [--jobs 4]
        [--pages 5-20] [--tesseract D:\Tesseract-OCR\tesseract.exe]

    # перераспознать уже отрисованные страницы другой моделью (рендер пропускается)
    python scripts/ocr_fraktur.py <input.pdf> <out_dir> --png-dir <старый>/pages

Выход:
    out_dir/pages/pNNNN.txt    постраничный текст (как есть, без чистки)
"""
import argparse
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz


def render_page(doc, idx, dpi, out_png):
    pix = doc[idx].get_pixmap(dpi=dpi)
    pix.save(out_png)
    return out_png


def ocr_page(tesseract, png, out_txt, lang="deu_latf", psm=3):
    r = subprocess.run(
        [tesseract, png, out_txt, "-l", lang, "--psm", str(psm)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"tesseract rc={r.returncode}: {r.stderr[:200]}")
    with open(out_txt + ".txt", encoding="utf-8") as f:
        return f.read()


def clean_page(text, page_no):
    """Чистка: склеить строки внутри абзаца (и переносы слов), сохранить абзацы.

    Tesseract даёт одну строку на печатную строку, абзацы — пустыми строками.
    Для перевода важна абзацная структура (translate.py дробит по пустым строкам),
    поэтому склеиваем строки абзаца в одну, дефисные переносы убираем.
    """
    paras = text.split("\n\n")
    out_paras = []
    for p in paras:
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        if not lines:
            continue
        joined = " ".join(lines)
        joined = re.sub(r"-\s+", "-", joined)  # переносы "Au?er- einander"
        joined = re.sub(r"[ \t]{2,}", " ", joined)
        out_paras.append(joined)
    return "\n\n".join(out_paras)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_pdf")
    ap.add_argument("out_dir")
    ap.add_argument("--dpi", default="auto",
                    help="300 работает, только если полоса объявлена в "
                         "обычных типографских пунктах. У сканов, где "
                         "страница — одна картинка, размер полосы равен её "
                         "пикселям (у Евклида 1371 pt), и 300 dpi раздувает "
                         "её вчетверо без всякой пользы. auto подбирает dpi "
                         "так, чтобы ширина вышла ~--target-px")
    ap.add_argument("--target-px", type=int, default=1500,
                    help="желаемая ширина растра в пикселях для --dpi auto")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--pages", default=None, help="напр. 5-20 (1-индексировано)")
    ap.add_argument("--lang", default="deu_latf",
                    help="deu_latf — LSTM-фрактура (по умолчанию, точнее); "
                         "deu_frak — устаревшая модель Tesseract 3")
    ap.add_argument("--png-dir", default=None,
                    help="брать готовые pNNNN.png отсюда вместо рендеринга PDF")
    ap.add_argument("--psm", type=int, default=3,
                    help="3 — с анализом вёрстки (годится для сплошного "
                         "текста). Если в полосу вклиниваются чертежи и текст "
                         "их обтекает (Евклид), psm 3 принимает обтекание за "
                         "колонки и ПЕРЕМЕШИВАЕТ строки — тогда только psm 6")
    ap.add_argument("--tesseract", default=tesseract(),
                    help="по умолчанию ищется в PATH и обычных "
                         "местах установки; можно задать "
                         "переменной TESSERACT_EXE")
    ap.add_argument("--offset", type=int, default=0,
                    help="сдвиг: печатная страница = страница PDF + offset (для томов без текстового слоя)")
    ap.add_argument("--resume", action="store_true",
                    help="пропускать страницы, для которых уже есть pNNNN.txt")
    a = ap.parse_args()

    os.makedirs(os.path.join(a.out_dir, "pages"), exist_ok=True)
    doc = fitz.open(a.input_pdf)
    n = doc.page_count

    if str(a.dpi).lower() == "auto":
        widths = sorted(doc[i].rect.width for i in range(min(n, 20)))
        med = widths[len(widths) // 2]
        a.dpi = max(72, min(400, round(72.0 * a.target_px / med)))
        print(f"dpi auto: полоса {med:.0f} pt -> dpi {a.dpi} "
              f"(растр ~{med * a.dpi / 72:.0f} px)", flush=True)
    else:
        a.dpi = int(a.dpi)
    if a.pages:
        lo, hi = (int(x) for x in a.pages.split("-"))
        idxs = list(range(lo - 1, min(hi, n)))
    else:
        idxs = list(range(n))
    if a.resume:
        skip = []
        keep = []
        for i in idxs:
            tpath = os.path.join(a.out_dir, "pages", f"p{i+1:04d}.txt")
            if os.path.exists(tpath) and os.path.getsize(tpath) > 0:
                skip.append(i)
            else:
                keep.append(i)
        idxs = keep
        if skip:
            print(f"resume: {len(skip)} стр. уже готовы, осталось {len(idxs)}", flush=True)
    print(f"{os.path.basename(a.input_pdf)}: {n} стр., OCR {len(idxs)} стр., "
          f"jobs={a.jobs}, dpi={a.dpi}", flush=True)

    t0 = time.time()
    done = 0
    fail = []

    def one(i):
        """Рендер (если нужен) и OCR одной страницы.

        fitz.Document не потокобезопасен, поэтому рендерим под общим замком;
        сам OCR — отдельный процесс, он и занимает почти всё время.
        """
        txt = os.path.join(a.out_dir, "pages", f"p{i+1:04d}")
        if a.png_dir:
            png = os.path.join(a.png_dir, f"p{i+1:04d}.png")
            if not os.path.exists(png):
                raise FileNotFoundError(png)
        else:
            png = os.path.join(a.out_dir, "pages", f"p{i+1:04d}.png")
            with render_lock:
                render_page(doc, i, a.dpi, png)
        ocr_page(a.tesseract, png, txt, a.lang, a.psm)
        return i

    render_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one, i): i for i in idxs}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                fut.result()
                done += 1
                if done % 25 == 0 or done == len(idxs):
                    el = time.time() - t0
                    print(f"  {done}/{len(idxs)}  ({el/done:.1f} с/стр, "
                          f"осталось ~{el/done*(len(idxs)-done)/60:.0f} мин)", flush=True)
            except Exception as e:
                fail.append((i, str(e)))
                print(f"  FAIL стр.{i+1}: {e}", flush=True)

    print(f"OCR: {done} ok, {len(fail)} fail, {time.time()-t0:.0f} с", flush=True)
    print(f"дальше: python scripts/build_ocr_md.py {a.out_dir} "
          f"--offset {a.offset}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
