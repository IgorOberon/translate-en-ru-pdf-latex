# -*- coding: utf-8 -*-
"""Карта «страница скана -> печатный номер» по колонтитулам.

Зачем. Единый --offset верен только если скан идеально ложится на книгу. На
практике смещение гуляет: в томе есть шмуцтитулы и вклейки без номера (скан
обгоняет книгу), а в сканах Google встречаются пропущенные развороты (книга
обгоняет скан). На Logik 1812 замер дал 47 в начале, 45 в середине и снова
другое ближе к концу — то есть номера на полях перевода были бы неправдой,
причём правдоподобной.

Метод. Колонтитул каждой полосы распознаётся отдельно, узкой полоской и в
режиме одной строки — так цифры читаются гораздо надёжнее, чем в общем OCR
страницы. Дальше сырые показания чинятся последовательностью: истинный номер
почти всегда равен «предыдущий + 1», поэтому берётся не отдельное показание,
а самая длинная согласованная цепочка, а выбросы («455» вместо «155»)
отбрасываются.

Выход — JSON {скан: печатный номер} + отчёт о разрывах, который стоит
проверить глазами (scripts/../head_strips по этим страницам).

Использование:
    python scripts/page_number_map.py <work_dir> --pdf <src.pdf>
        [--out pagemap.json] [--jobs 4] [--first 49]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BAND = (0.045, 0.14)      # пояс полосы, где стоит колонтитул
ZOOM = 4.0
D_MIN, D_MAX = 35, 70     # правдоподобные смещения «скан - печатная»
JUMP_COST = 4.0           # цена разрыва: разрывов мало, промахов OCR много
OUTLIER_D = 4             # на сколько смещение опоры может отличаться от
                          # локальной медианы, прежде чем счесть её выбросом


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import tesseract  # noqa: E402


def ocr_head(tesseract, pdf_path, idx, work, lang):
    """Распознать колонтитул одной полосы -> строка.

    psm 6, а не 7: пояс несёт не одну строку, а колонтитул плюс крапины скана,
    и в режиме одной строки Tesseract отдаёт пустоту почти всегда (проверено:
    345 полос, подтвердилось 7). Читаем ДВУМЯ движками — фрактурным и
    латинским: арабские цифры набраны обычной антиквой, и eng берёт их там,
    где deu_latf путает («105» -> «co5»). Кандидаты потом отбирает Витерби.
    """
    doc = fitz.open(pdf_path)
    page = doc[idx]
    r = page.rect
    clip = fitz.Rect(r.x0, r.y0 + r.height * BAND[0],
                     r.x1, r.y0 + r.height * BAND[1])
    png = os.path.join(work, f"h{idx+1:04d}.png")
    page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip).save(png)
    doc.close()
    texts = []
    for lng in (lang, "eng"):
        stem = os.path.join(work, f"h{idx+1:04d}_{lng}")
        subprocess.run([tesseract, png, stem, "-l", lng, "--psm", "6"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        try:
            with open(stem + ".txt", encoding="utf-8", errors="replace") as f:
                texts.append(f.read().strip())
        except FileNotFoundError:
            texts.append("")
    return texts


def numbers_in(text):
    """Кандидаты в номер страницы: 1-3 цифры по краям колонтитула."""
    return [int(x) for x in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", text)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--lang", default="deu_latf")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--first", type=int, default=1,
                    help="с какой страницы скана начинается нумерованный текст")
    ap.add_argument("--skip", default="",
                    help="полосы вне счёта: дубли пересъёмки, «43-44,319-328» "
                         "(их находит scripts/find_dup_scans.py)")
    ap.add_argument("--jump-cost", type=float, default=JUMP_COST,
                    help="цена разрыва смещения; ниже — больше разрывов")
    ap.add_argument("--dmin", type=int, default=D_MIN,
                    help="минимальное правдоподобное «скан - печатная»")
    ap.add_argument("--dmax", type=int, default=D_MAX,
                    help="максимальное; при выброшенных дублях смещение "
                         "растёт на каждую пропущенную полосу")
    ap.add_argument("--tesseract", default=tesseract())
    a = ap.parse_args()

    doc = fitz.open(a.pdf)
    n = doc.page_count
    doc.close()
    work = tempfile.mkdtemp(prefix="pagemap_")

    skip = set()
    for part in a.skip.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            skip.update(range(lo, hi + 1))
        else:
            skip.add(int(part))
    todo = [i for i in range(a.first - 1, n) if (i + 1) not in skip]

    print(f"колонтитулы: {len(todo)} полос (исключено {len(skip)}), "
          f"jobs {a.jobs}", flush=True)
    raw = {}
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(ocr_head, a.tesseract, a.pdf, i, work, a.lang): i
                for i in todo}
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            raw[i + 1] = fut.result()
            done += 1
            if done % 100 == 0 or done == len(futs):
                print(f"  {done}/{len(futs)}", flush=True)

    # Сырое показание доверия не заслуживает: «155» читается как «455», а в
    # колонтитуле есть и посторонние цифры («III. Abschnitt»). Зато соседи
    # связаны: печатный номер растёт на 1 на полосу, а смещение постоянно
    # длинными кусками. Поэтому ищем кусочно-постоянное смещение
    # динамическим программированием: платим 1 за полосу, чьё показание не
    # совпало, и JUMP_COST за каждый разрыв. Голосование по окну здесь не
    # годится — один мусорный кандидат утаскивает всё окно.
    pages = sorted(raw)

    # ПОДТВЕРЖДЁННЫЕ номера: оба движка независимо прочли на этой полосе один
    # и тот же правдоподобный номер. Только они идут на поля перевода —
    # выдуманный номер страницы хуже, чем его отсутствие, а нумерация этого
    # скана слишком испорчена (дубли пересъёмки, пропуски), чтобы достраивать
    # её счётом от опорных точек.
    # Третий читатель — постраничный OCR, уже лежащий в work_dir: его верхние
    # строки содержат тот же колонтитул, распознанный с другими параметрами.
    # Голосование двух источников из трёх поднимает покрытие, не жертвуя
    # строгостью: случайная цифра совпадает у двух читателей редко.
    page_ocr = {}
    pages_dir = os.path.join(a.work_dir, "pages")
    if os.path.isdir(pages_dir):
        for f in sorted(os.listdir(pages_dir)):
            m = re.fullmatch(r"p(\d{4})\.txt", f)
            if not m:
                continue
            lines = [l for l in open(os.path.join(pages_dir, f),
                                     encoding="utf-8",
                                     errors="replace").read().splitlines()
                     if l.strip()]
            page_ocr[int(m.group(1))] = " ".join(lines[:2])

    confirmed = {}
    for p, texts in raw.items():
        readers = list(texts)
        if p in page_ocr:
            readers.append(page_ocr[p])
        sets = [{v for v in numbers_in(t)
                 if 1 <= v <= n and a.dmin <= p - v <= a.dmax}
                for t in readers]
        votes = Counter(v for s in sets for v in s)
        agreed = [v for v, c in votes.items() if c >= 2]
        if len(agreed) == 1:
            confirmed[p] = agreed[0]
    print(f"номеров, подтверждённых обоими движками: {len(confirmed)}"
          f"/{len(pages)}", flush=True)

    # Совпадение двух движков ещё не гарантия: оба одинаково ловят постороннюю
    # цифру («III. Abschnitt» -> 3), и получается опора «полоса 71 = страница
    # 1». Такие видно по смещению: оно резко выпадает из локального тренда.
    if confirmed:
        anchors0 = sorted(confirmed)
        ds = {p: p - confirmed[p] for p in anchors0}
        kept = {}
        for p in anchors0:
            near = sorted(anchors0, key=lambda q: abs(q - p))[:21]
            med = sorted(ds[q] for q in near)[len(near) // 2]
            if abs(ds[p] - med) <= OUTLIER_D:
                kept[p] = confirmed[p]
        dropped = len(confirmed) - len(kept)
        confirmed = kept
        print(f"опор отброшено как выбросы: {dropped}, осталось "
              f"{len(confirmed)}", flush=True)

    # Между двумя подтверждёнными опорами номера достраиваем — но только если
    # арифметика сходится точно: сколько полос между опорами, столько и
    # печатных страниц. Если не сошлось, внутри промежутка что-то не так
    # (пересъёмка, пропуск, вклейка) — тогда промежуток остаётся БЕЗ номеров,
    # а не заполняется правдоподобной выдумкой.
    idx = {p: i for i, p in enumerate(pages)}
    anchors = sorted(confirmed)
    filled, gaps = dict(confirmed), []
    for p1, p2 in zip(anchors, anchors[1:]):
        span = idx[p2] - idx[p1]
        if confirmed[p2] - confirmed[p1] == span:
            for k in range(1, span):
                filled[pages[idx[p1] + k]] = confirmed[p1] + k
        else:
            gaps.append((p1, p2, confirmed[p1], confirmed[p2], span))
    confirmed = filled
    print(f"после сверки опор: номеров {len(confirmed)}/{len(pages)}, "
          f"несходящихся промежутков {len(gaps)}", flush=True)
    for p1, p2, v1, v2, span in gaps[:12]:
        print(f"   полосы {p1}..{p2}: с.{v1} -> с.{v2} при {span} полосах "
              f"(расхождение {v2 - v1 - span:+d}) — номера не ставим")

    cands = {}
    for p, texts in raw.items():
        good = set()
        for v in numbers_in(" ".join(texts)):
            if 1 <= v <= n and a.dmin <= p - v <= a.dmax:
                good.add(p - v)
        cands[p] = good

    states = list(range(a.dmin, a.dmax + 1))
    prev_cost = {d: (0.0 if d in cands[pages[0]] else 1.0) for d in states}
    back = []
    for p in pages[1:]:
        cur_cost, cur_back = {}, {}
        best_prev_d = min(prev_cost, key=prev_cost.get)
        best_prev = prev_cost[best_prev_d]
        for d in states:
            stay = prev_cost[d]
            jump = best_prev + a.jump_cost
            if stay <= jump:
                cur_cost[d], cur_back[d] = stay, d
            else:
                cur_cost[d], cur_back[d] = jump, best_prev_d
            cur_cost[d] += 0.0 if d in cands[p] else 1.0
        prev_cost = cur_cost
        back.append(cur_back)

    d_at = {pages[-1]: min(prev_cost, key=prev_cost.get)}
    for k in range(len(pages) - 2, -1, -1):
        d_at[pages[k]] = back[k][d_at[pages[k + 1]]]

    pagemap = {p: p - d_at[p] for p in pages}
    offsets = dict(d_at)
    agree = sum(1 for p in pages if d_at[p] in cands[p])
    print(f"полос, где OCR подтверждает смещение: {agree}/{len(pages)}",
          flush=True)

    # где смещение меняется — это либо шмуцтитул/вклейка, либо пропуск в скане
    jumps = []
    prev = None
    for p in pages:
        d = offsets.get(p)
        if d is None:
            continue
        if prev is not None and d != prev:
            jumps.append((p, prev, d))
        prev = d

    out_path = a.out or os.path.join(a.work_dir, "pagemap.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"_смысл": "скан -> печатный номер, по колонтитулам",
                   "_map": "подтверждено двумя движками — это и берут поля",
                   "_dp": "достроено сглаживанием, только для диагностики",
                   "pdf": a.pdf,
                   "jumps": [{"с_полосы": p, "было": b, "стало": d}
                             for p, b, d in jumps],
                   "map": {str(k): v for k, v in sorted(confirmed.items())},
                   "dp": {str(k): v for k, v in sorted(pagemap.items())}},
                  f, ensure_ascii=False, indent=1)

    print(f"\n{out_path}: сопоставлено полос {len(pagemap)}")
    print(f"разрывов смещения: {len(jumps)}")
    for p, b, d in jumps:
        kind = "пропуск в скане" if d < b else "полосы без номера"
        print(f"  с полосы {p}: смещение {b} -> {d}  ({kind}); "
              f"печатная там {pagemap.get(p)}")
    print("\nПРОВЕРЬТЕ разрывы глазами, прежде чем верить карте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
