#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Есть ли в этом издании геометрический признак яруса — и стоит ли hOCR.

Зачем. В изданиях Гегеля примечание («Anmerkung») и прибавление издателя
идут отдельными ярусами, но словом подписано только прибавление. Напрашивается
мысль поднять ярус примечания по кеглю — для этого нужен второй прогон
Tesseract в hOCR, несколько часов на том плюс весь конвейер ниже. Прежде чем
платить, стоит проверить, есть ли вообще что поднимать.

Проверка бесплатная, потому что эталон уже есть: «Zusatz» ПОДПИСАН, значит
про каждую строку полосы заранее известно, корпус это параграфа или
прибавление. Если разница в кегле видна на нём — она видна и вообще; если
нет — hOCR не поможет, и городить его незачем.

Меряется:
  · x_size из hOCR — оценка кегля строки;
  · шаг строк (разница y соседних строк) — интерлиньяж;
  · РАЗРЯДКА: ширина рамки слова против предсказания «отступ + n*знак».
    Разрядка — авторское выделение немецкого набора, и в переводе она
    теряется целиком (в body.tex тома 6 на 1,5 МБ ровно 6 \\emph).

Что получилось на томе 6 (Encyklopädie I, 1843), полосы 77, 80, 82, 89:
кегль ярусов одинаков (отношение 0,98–1,03), шаг строк одинаков до пикселя
(59 px), а у разрядки сигнал слабее шума — заведомо разряженные «abſtrakten»
и «Allgemeinheit» дали 1,12 и 1,01 при шумовом поле около 1,25. Для этого
издания hOCR не окупается. Другое издание может быть набрано иначе —
запустите зонд, прежде чем решать.

Использование:
    python scripts/probe_tiers.py <work_dir> --pages p0077,p0080,p0082
        [--marker "Zu[sſf]{1,2}a[tßz]{1,2}"] [--tesseract ...]
"""
import argparse
import io
import os
import re
import subprocess
import sys
from statistics import median

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LINE = re.compile(
    r'<span class=[\'"]ocr_line[\'"][^>]*title=[\'"]([^\'"]*)[\'"][^>]*>(.*?)</span>',
    re.S)
WORD = re.compile(
    r'<span class=[\'"]ocrx_word[\'"][^>]*title=[\'"]([^\'"]*)[\'"][^>]*>(.*?)</span>',
    re.S)
TAG = re.compile(r"<[^>]+>")
MIN_LETTERS = 4
SPERR_MIN = 1.22        # во сколько раз шире предсказания — кандидат в разрядку


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import tesseract  # noqa: E402


def bbox(title):
    m = re.search(r"bbox (\d+) (\d+) (\d+) (\d+)", title)
    return tuple(int(g) for g in m.groups()) if m else None


def x_size(title):
    m = re.search(r"x_size\s+([\d.]+)", title)
    return float(m.group(1)) if m else None


def run_hocr(tess, png, base, lang, psm):
    r = subprocess.run([tess, png, base, "-l", lang, "--psm", str(psm), "hocr"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"tesseract rc={r.returncode}: {r.stderr[:200]}")
    # hOCR Tesseract пишет не в чистом UTF-8, если распознавание дало
    # битые байты — читаем снисходительно, нам нужны координаты
    return io.open(base + ".hocr", encoding="utf-8", errors="replace").read()


def lines_of(html):
    out = []
    for m in LINE.finditer(html):
        t = re.sub(r"\s+", " ", TAG.sub("", m.group(2))).strip()
        b = bbox(m.group(1))
        if t and b:
            out.append({"t": t, "x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3],
                        "size": x_size(m.group(1))})
    out.sort(key=lambda r: r["y0"])
    return out


def words_of(html):
    out = []
    for m in WORD.finditer(html):
        t = TAG.sub("", m.group(2)).strip()
        b = bbox(m.group(1))
        if not b:
            continue
        core = re.sub(r"[^A-Za-zÄÖÜäöüßſ-]", "", t)
        if len(core) < MIN_LETTERS:
            continue
        out.append({"t": t, "n": len(core), "w": b[2] - b[0]})
    return out


def fit_line(xs, ys):
    """Наименьшие квадраты: ширина рамки = a + b*число_знаков."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0
    return my - b * mx, b


def pitch(rows):
    d = [rows[i + 1]["y0"] - rows[i]["y0"] for i in range(len(rows) - 1)]
    d = [x for x in d if 0 < x < 300]
    return median(d) if d else 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir")
    ap.add_argument("--pages", required=True,
                    help="через запятую: p0077,p0080 — полосы, где ярус "
                         "начинается в СЕРЕДИНЕ, а не с первой строки")
    ap.add_argument("--marker", default=r"Zu[sſf]{1,2}a[tßz]{1,2}",
                    help="регэксп подписи яруса-эталона (по умолчанию Zusatz "
                         "во всех вариантах распознавания фрактуры)")
    ap.add_argument("--lang", default="deu_latf")
    ap.add_argument("--psm", type=int, default=3)
    ap.add_argument("--tesseract", default=tesseract())
    ap.add_argument("--out", default=None, help="куда класть .hocr")
    a = ap.parse_args()

    pages_dir = os.path.join(a.work_dir, "pages")
    out_dir = a.out or os.path.join(a.work_dir, "hocr")
    os.makedirs(out_dir, exist_ok=True)
    marker = re.compile(a.marker)
    ratios, pitches = [], []

    for page in [p.strip() for p in a.pages.split(",") if p.strip()]:
        png = os.path.join(pages_dir, page + ".png")
        if not os.path.exists(png):
            print(f"!! нет {png}")
            continue
        html = run_hocr(a.tesseract, png, os.path.join(out_dir, page),
                        a.lang, a.psm)
        rows = lines_of(html)
        cut = next((i for i, r in enumerate(rows) if marker.search(r["t"])),
                   None)
        print(f"\n===== {page}: строк {len(rows)}, "
              + (f"подпись яруса на строке {cut}" if cut is not None
                 else "ПОДПИСИ ЯРУСА НЕТ — возьмите другую полосу"))
        if cut is None or cut < 3 or cut > len(rows) - 4:
            continue
        upper, lower = rows[:cut], rows[cut:]
        for name, g in (("корпус ", upper), ("ярус   ", lower)):
            sz = [r["size"] for r in g if r["size"]]
            print(f"   {name} строк {len(g):3d}  кегль {median(sz):6.2f}"
                  f"  шаг строк {pitch(g):5.1f}")
        su = median(r["size"] for r in upper if r["size"])
        sl = median(r["size"] for r in lower if r["size"])
        ratios.append(su / sl)
        pu, pl = pitch(upper), pitch(lower)
        if pu and pl:
            pitches.append(pu / pl)
        print(f"   отношение корпус/ярус: кегль {su / sl:.3f}, "
              f"шаг {pu / max(1, pl):.3f}")

        ws = words_of(html)
        if len(ws) >= 30:
            k0, k1 = fit_line([w["n"] for w in ws], [w["w"] for w in ws])
            for w in ws:
                w["r"] = w["w"] / max(1.0, k0 + k1 * w["n"])
            wide = sorted((w for w in ws if w["r"] > SPERR_MIN),
                          key=lambda w: -w["r"])
            print(f"   разрядка: ширина = {k0:.0f} + {k1:.1f}*n px, "
                  f"кандидатов {len(wide)} из {len(ws)}")
            for w in wide[:6]:
                print(f"      x{w['r']:.2f}  {w['t']}")

    print("\n== ВЕРДИКТ ==")
    if not ratios:
        print("  нечего сравнивать: подпись яруса не нашлась в середине полос")
        return 2
    rs, ps = median(ratios), (median(pitches) if pitches else 1.0)
    print(f"  кегль корпус/ярус: {rs:.3f} по {len(ratios)} полосам")
    print(f"  шаг строк:         {ps:.3f}")
    if abs(rs - 1) < 0.06 and abs(ps - 1) < 0.06:
        print("  Ярусы набраны ОДНИМ кеглем и одним интерлиньяжем. Поднять\n"
              "  неподписанный ярус (Anmerkung) по геометрии НЕЛЬЗЯ, и второй\n"
              "  прогон Tesseract в hOCR ради этого не окупается.")
        return 1
    print("  Разница есть — hOCR имеет смысл: решение о ярусе можно принимать\n"
          "  по кеглю строки в build_ocr_md.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
