# -*- coding: utf-8 -*-
"""Вырезка геометрических чертежей со страниц готического скана.

Метод без визуализации: на странице находятся связные тёмные компоненты
(бинаризация Отсу), крупные и не излишне плотные (штриховые линии чертежа,
а не заливка), определяется охватывающая область, близкие области сливаются.
Вырез сохраняется как images/p%04d_f%02d.png. Приёмка вырезов — глазами.

Примечание о текстовой маске: буквы-метки A/B/C внутри чертежей сканер
распознаёт как «строки текста», поэтому сливяние по тексту ТОПИЛО чертёж;
текст-маски здесь нет — защита от жирных пин — фильтры по размеру и
плотности.

Использование:
    python scripts/cut_figures.py <work_dir> --pages 37-66
"""
import argparse
import os
import re
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8),
                        cv2.IMREAD_GRAYSCALE)


def overlap_ratio(a, b):
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ox = max(0, min(ax2, bx2) - max(ax1, bx1))
    oy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ox * oy
    area = max((ax2 - ax1) * (ay2 - ay1), 1)
    return inter / area


def boxes_for_page(im, min_area, min_side, max_density):
    h, w = im.shape
    thr = cv2.threshold(im, 0, 255,
                        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    comps = cv2.connectedComponentsWithStats(thr, 8, cv2.CV_32S)
    boxes = []
    for c in comps[2][1:]:
        x, y, cw, ch, ca = [int(c[k]) for k in range(5)]
        if ca < min_area or cw < 10 or ch < 10:
            continue
        if ch > 0.5 * h or cw > 0.9 * w:
            continue
        if ca / (cw * ch) > max_density:
            continue
        boxes.append((x, y, x + cw, y + ch, ca))
    merged = True
    while merged:
        merged = False
        nb, used = [], [False] * len(boxes)
        for i in range(len(boxes)):
            if used[i]:
                continue
            x1, y1, x2, y2, a1 = boxes[i]
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                if overlap_ratio(boxes[i], boxes[j]) > 0.0:
                    x1, y1 = min(x1, boxes[j][0]), min(y1, boxes[j][1])
                    x2, y2 = max(x2, boxes[j][2]), max(y2, boxes[j][3])
                    a1 += boxes[j][4]
                    used[j] = True
                    merged = True
            boxes[i] = (x1, y1, x2, y2, a1)
        boxes = [b for k, b in enumerate(boxes) if not used[k]]
    return [b for b in boxes
            if (b[2] - b[0]) >= min_side and (b[3] - b[1]) >= min_side]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--pages", default="40-50")
    ap.add_argument("--min-area", type=int, default=250)
    ap.add_argument("--min-side", type=int, default=110)
    ap.add_argument("--max-density", type=float, default=0.45,
                    help="плотность чёрного в боксе выше которой компонент "
                         "считается текстом/заливкой")
    ap.add_argument("--pad", type=int, default=18)
    a = ap.parse_args()

    pages = []
    for part in a.pages.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            pages += list(range(int(m.group(1)), int(m.group(2)) + 1))
        else:
            pages.append(int(part))

    images_dir = os.path.join(a.work_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    total = 0
    for pg in pages:
        png = os.path.join(a.work_dir, "pages", f"p{pg:04d}.png")
        if not os.path.exists(png):
            continue
        im = load(png)
        h, w = im.shape
        boxes = boxes_for_page(im, a.min_area, a.min_side, a.max_density)
        n = 0
        for x1, y1, x2, y2, area in boxes:
            xi, yi = max(x1 - a.pad, 0), max(y1 - a.pad, 0)
            xj, yj = min(x2 + a.pad, w), min(y2 + a.pad, h)
            crop = im[yi:yj, xi:xj]
            dark = float(np.count_nonzero(crop < 128)) / crop.size
            if dark > 0.35:
                print(f"полоса {pg}: пропущено (плотное) "
                      f"{xj - xi}x{yj - yi} чёрное {dark:.2%}")
                continue
            name = f"p{pg:04d}_{n + 1:02d}.png"
            cv2.imencode(".png", crop)[1].tofile(
                os.path.join(images_dir, name))
            print(f"полоса {pg}: {name} {xj - xi}x{yj - yi} "
                  f"чёрное {dark:.2%}")
            n += 1
        total += n
    print(f"всего вырезано: {total}")


if __name__ == "__main__":
    main()