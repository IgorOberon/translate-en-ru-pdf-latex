# -*- coding: utf-8 -*-
"""Отсев вырезов, которые на деле куски текста, а не чертежи.

cut_figures.py судит по геометрии пятна (размер, плотность), и иногда крупная
строка фрактуры проходит за рисунок: в книге появляется увеличенный обрывок
«FC, Jn AF = der Wi folglich» вместо схемы. Отличить надёжнее всего
распознаванием самого выреза: у чертежа Tesseract видит одиночные буквы-метки
(A, B, C, D), у текста — слова.

Критерий: вырез бракуется, если в нём найдено >= --max-words «слов» длиной
от --word-len букв. Метки чертежей этот порог не берут.

Использование:
    python scripts/filter_text_crops.py <work_dir> [--max-words 4]
        [--word-len 4] [--apply]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Слово считаем только со строчными буквами: метки чертежей набраны
# прописными (A, B, C, ABC), и по ним нельзя отличить схему от текста —
# порог по всем буквам подряд браковал настоящие чертежи («WAX BGE», «ZOR
# LZZ»). Строчные же встречаются только в наборном тексте.
WORD = re.compile(r"[A-ZÄÖÜ]?[a-zäöüßſ]{2,}")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import tesseract  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--word-len", type=int, default=4)
    ap.add_argument("--tesseract", default=tesseract())
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--apply", action="store_true",
                    help="переписать figures.json без забракованных вырезов")
    a = ap.parse_args()

    img_dir = os.path.join(a.work_dir, "images")
    work = tempfile.mkdtemp(prefix="figfilt_")
    files = sorted(f for f in os.listdir(img_dir) if f.endswith(".png"))
    print(f"вырезов: {len(files)}")

    def judge(f):
        stem = os.path.join(work, f[:-4])
        subprocess.run([a.tesseract, os.path.join(img_dir, f), stem,
                        "-l", "deu_latf", "--psm", "6"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        try:
            t = open(stem + ".txt", encoding="utf-8", errors="replace").read()
        except FileNotFoundError:
            return f, 0, ""
        words = [w for w in WORD.findall(t) if len(w) >= a.word_len]
        return f, len(words), " ".join(words[:6])

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        rows = list(ex.map(judge, files))

    bad = [(f, n, s) for f, n, s in rows if n >= a.max_words]
    print(f"похожи на текст, а не на чертёж: {len(bad)}")
    for f, n, s in bad[:25]:
        print(f"  {f}: слов {n} — «{s}»")

    if not a.apply:
        print("\n(пробный прогон; чтобы вычистить, добавьте --apply)")
        return 0

    badset = {f for f, _, _ in bad}
    fp = os.path.join(a.work_dir, "figures.json")
    figs = json.load(open(fp, encoding="utf-8"))
    kept = {}
    for page, items in figs.items():
        left = [it for it in items if it["file"] not in badset]
        if left:
            kept[page] = left
    before = sum(len(v) for v in figs.values())
    after = sum(len(v) for v in kept.values())
    json.dump(kept, open(fp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n{fp}: было {before} чертежей, осталось {after}")
    print("пересоберите book.md с --figures и соберите книгу заново")
    return 0


if __name__ == "__main__":
    sys.exit(main())
