#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clip one figure out of a PDF page and save it as a high-DPI PNG.

Usage:
    crop_figure.py PDF PDF_INDEX X0 Y0 X1 Y1 OUT.png [DPI]

Coordinates are in PDF points (read them off grid_overlay.py). DPI defaults to
300. Use the same crop_figure call to re-extract after adjusting the bbox.
"""
import sys
import fitz


def main():
    if len(sys.argv) < 8:
        print(__doc__)
        sys.exit(1)
    pdf = sys.argv[1]
    idx = int(sys.argv[2])
    x0, y0, x1, y1 = (float(sys.argv[i]) for i in (3, 4, 5, 6))
    out = sys.argv[7]
    dpi = float(sys.argv[8]) if len(sys.argv) > 8 else 300.0

    doc = fitz.open(pdf)
    pm = doc[idx].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                             clip=fitz.Rect(x0, y0, x1, y1))
    pm.save(out)
    print("saved %s  (%dx%d px  @ %g dpi  from clip %g,%g,%g,%g)"
          % (out, pm.width, pm.height, dpi, x0, y0, x1, y1))
    doc.close()


if __name__ == "__main__":
    main()
