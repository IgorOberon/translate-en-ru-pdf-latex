# -*- coding: utf-8 -*-
"""Вставить чертежи в переведённую книгу на места Satz.

Позиция фигуры: первый блок, у которого печатная страница (маркер <!--P-->)
совпадает с печатной страницей полосы фигуры (полоса − 36) ИЛИ близка к ней
(±2 — печать документа местами прыгает / маркер пропускается), и текст
блока содержит «Der N. …» с номером Satz фигуры.

Строка-вставка "![](images/FILE)" кладётся в КОНЕЦ соответствующего блока
ПЕРЕВОДА (блоки исходника и перевода идут 1:1). Повторно не дублирует.

Использование:
    python scripts/insert_figures.py <work_dir> [--dry-run]
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BLOCK = re.compile(r"\n\s*\n")
PAGE_MARK = re.compile(r"<!--(-?\d+)-->")
IMG_IN = re.compile(r"!\[\]\(images/")
OFF = 36


def blocks_of(text):
    return [b for b in BLOCK.split(text.strip()) if b.strip()]


def page_index(src_blocks):
    """индекс блока -> печатная страница (маркер <!--P-->), поставленная
    перед ним. Блоки без маркера наследуют последний маркер."""
    out, cur = {}, None
    for i, b in enumerate(src_blocks):
        m = PAGE_MARK.match(b.strip())
        if m:
            cur = int(m.group(1))
        else:
            out[i] = cur
    return out


def page_span(pages, n):
    """интервал печатных страниц блоков с маркером n — [n, next_marker)."""
    marks = sorted({v for v in pages.values() if v is not None})
    pos = marks.index(n)
    nxt = marks[pos + 1] if pos + 1 < len(marks) else n + 100
    return n, nxt - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.work_dir

    data = json.load(open(os.path.join(root, "figures.json"),
                          encoding="utf-8"))
    items = [(int(pg), it["satz"], it["file"])
             for pg, lst in data.items() for it in lst]

    src = []
    for n in range(1, 100):
        p = os.path.join(root, f"book.part{n}.md")
        if not os.path.exists(p):
            break
        src += blocks_of(open(p, encoding="utf-8").read())
    pages = page_index(src)
    print(f"исходных блоков: {len(src)}")

    plan = {}
    for page, satz, f in sorted(items):
        printed = page - OFF      # печатная страница = полоса − 36
        hit = -1
        WIN = 2
        best = []                 # (satz_ok?, dist, блок)
        for i, b in enumerate(src):
            p = pages.get(i)
            if p is None:
                continue
            m0, m1 = page_span(pages, p)
            d = 0
            if printed < m0:
                d = m0 - printed
            elif printed > m1:
                d = printed - m1
            if d > WIN:
                continue
            if satz is not None and re.search(
                    r"Der\s*\S{0,4}" + re.escape(str(satz)) + r"\b", b):
                best.append((0, d, i))
            else:
                best.append((1, d, i))
        if best:
            best.sort(key=lambda t: (t[0], t[1], t[2]))
            hit = best[0][2]
        if hit == -1:
            marks = sorted({v for v in pages.values() if v is not None})
            if marks and printed < marks[0]:
                # полосы до первого распознанного печатного маркера (печ 1..7
                # оригинала не распознаны OCR, но их текст есть в первых
                # блоках) — прикрепляем к первому НЕ маркерному блоку
                for j, b in enumerate(src):
                    if not PAGE_MARK.match(b.strip()):
                        hit = j
                        break
        if hit == -1:
            print(f"не найдено: полоса {page} (печ ~{printed}) "
                  f"Satz {satz} «{f}»")
            continue
        plan.setdefault(hit, []).append(f)
    print(f"точек: {len(plan)}, фигур: {sum(len(v) for v in plan.values())}")

    for n in range(1, 100):
        p = os.path.join(root, f"book.ru.part{n}.md")
        if not os.path.exists(p):
            break
        blocks = blocks_of(open(p, encoding="utf-8").read())
        base = (n - 1) * 300

        changed_here = 0
        changed = False
        for i, files in sorted(plan.items()):
            li = i - base
            if not (0 <= li < len(blocks)):
                continue
            b = blocks[li]
            add = [f for f in files
                   if not re.search(rf"!\[\]\(images/{re.escape(f)}\)", b)]
            if not add:
                continue
            blocks[li] = b + "\n" + "\n".join(
                f"![](images/{f})" for f in add)
            changed = True
            changed_here += 1
        if changed and not a.dry_run:
            open(p, "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
            print(f"часть {n}: обновлена")
        elif changed:
            print(f"часть {n}: изменений было бы {changed_here} (dry-run)")
    print("готово")


if __name__ == "__main__":
    main()