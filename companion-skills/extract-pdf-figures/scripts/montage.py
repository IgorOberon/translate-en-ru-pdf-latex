#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tile several figure crops into one labelled montage, for visual verification.

Usage:
    montage.py OUT.png IMG1 [IMG2 ...]

Each crop is shrunk to fit a cell and labelled with its filename so you can tell
at a glance which crops grabbed a header / caption / body text or clipped the
figure. Open OUT.png with the Read tool and look.
"""
import os
import sys
import math
from PIL import Image, ImageDraw


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[1]
    paths = sys.argv[2:]
    n = len(paths)
    cols = min(4, n)
    rows = math.ceil(n / cols)
    cell = 320
    pad = 6
    lab = 16
    canvas = Image.new("RGB", (cols * cell + pad, rows * cell + pad), "white")
    dr = ImageDraw.Draw(canvas)
    for i, p in enumerate(paths):
        r, c = divmod(i, cols)
        x = pad + c * cell
        y = pad + r * cell
        try:
            im = Image.open(p).convert("RGB")
        except Exception as e:
            dr.text((x + 2, y + 2), "MISSING %s" % os.path.basename(p), fill="red")
            continue
        im.thumbnail((cell - 8, cell - lab - 8))
        canvas.paste(im, (x + (cell - im.width) // 2, y + lab))
        dr.text((x + 2, y + 2), os.path.basename(p), fill="red")
    canvas.save(out)
    print("montage %s  (%d crops, %dx%d grid)" % (out, n, cols, rows))


if __name__ == "__main__":
    main()
