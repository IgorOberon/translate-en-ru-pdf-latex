# -*- coding: utf-8 -*-
"""Привязка вырезанных чертежей к номерам Satz/Aufgabe на той же полосе.

Номера заголовков берутся из OCR-текста полосы (pages/p%04d.txt): все строки
вида «Der N. Saß./Aufgabe/Lehrsatz», числа выстраиваются в сквозную
последовательность (допускается сбой OCR: разрыв ≤3 дополняется +1). Порядок
совпадает с порядком текста на полосе, то есть сверху вниз.

Каждая фигура полосы (отсортированная по Y) получает номер из этой
последовательности по своему порядковому номеру; лишние фигуры достаются
последнему заголовку полосы.

Выход: figures.json:
    {"41": [{"file": "p0041_01.png", "y": 100, "satz": 3}, ...], ...}

Использование:
    python scripts/attach_figures.py <work_dir> [37-66]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cut_figures as CF  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SATZ_RE = re.compile(r"(\d{1,2})\s*[.,:;]?\s*"
                     r"(?:Sa[?ßsz]{1,3}|Lehr[sa]?[?ßsz]{1,3}|Auf[gG]abe)\b",
                     re.IGNORECASE)


def satz_nums_from_page(txt):
    """Номера Satz в порядке текста (сверху вниз), сквозная нумерация."""
    nums = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln or len(ln) > 100:
            continue
        m = SATZ_RE.search(ln)
        if not m:
            continue
        num = int(m.group(1))
        # цепочка может начаться где угодно; пропуск >3 считаем высоким
        if nums and num - nums[-1] not in (1, 2, 3):
            num = nums[-1] + 1
        nums.append(num)
    return nums


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("pages", nargs="?", default="37-66")
    a = ap.parse_args()

    pages = []
    for part in a.pages.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            pages += list(range(int(m.group(1)), int(m.group(2)) + 1))
        else:
            pages.append(int(part))

    out = {}
    for pg in pages:
        png = os.path.join(a.work_dir, "pages", f"p{pg:04d}.png")
        if not os.path.exists(png):
            continue
        figs = sorted(
            [f for f in os.listdir(os.path.join(a.work_dir, "images"))
             if f.startswith(f"p{pg:04d}_")],
            key=lambda f: int(f.split("_")[1].split(".")[0]))
        if not figs:
            continue
        ys = {}
        for f in figs:
            crop = CF.load(os.path.join(a.work_dir, "images", f))
            ys[f] = crop.shape[0] // 2
        txt = open(os.path.join(a.work_dir, "pages", f"p{pg:04d}.txt"),
                   encoding="utf-8", errors="replace").read()
        nums = satz_nums_from_page(txt)
        if not nums:
            print(f"полоса {pg}: фигур {len(figs)} — заголовков не найдено")
            for f in figs:
                out.setdefault(str(pg), []).append(
                    {"file": f, "y": ys[f], "satz": None})
            continue
        print(f"полоса {pg}: фигур {len(figs)}, Satz {nums}")
        entry = []
        for i, f in enumerate(figs):
            satz = nums[min(i, len(nums) - 1)]
            entry.append({"file": f, "y": ys[f], "satz": satz})
        out[str(pg)] = entry
    path = os.path.join(a.work_dir, "figures.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{path}: полос {len(out)}, фигур "
          f"{sum(len(v) for v in out.values())}")


if __name__ == "__main__":
    main()