#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a PDF page-region with a labelled coordinate grid, so you can read a
figure's bounding box (in PDF points) directly off the image.

Usage:
    grid_overlay.py PDF PDF_INDEX Y0 Y1 [OUT.png] [SCALE]

    PDF        path to the PDF
    PDF_INDEX  0-based page index (book_page + offset - 1)
    Y0 Y1      vertical band to show, in points (e.g. 50 200)
    OUT.png    output (default _grid.png)
    SCALE      render scale (default 2.4 ; raise for tiny text)

Red horizontal rules every 10 pt are labelled with their y-coordinate; blue
vertical rules every 50 pt are labelled with their x-coordinate. Read the
figure's (x0,y0,x1,y1) off these, then feed them to crop_figure.py.
"""
import sys
import fitz                      # PyMuPDF
from PIL import Image, ImageDraw


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    pdf, idx, y0, y1 = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    out = sys.argv[5] if len(sys.argv) > 5 else "_grid.png"
    s = float(sys.argv[6]) if len(sys.argv) > 6 else 2.4

    doc = fitz.open(pdf)
    page = doc[idx]
    W = page.rect.width
    pm = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(0, y0, W, y1))
    im = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
    dr = ImageDraw.Draw(im)

    y = int(y0) - (int(y0) % 10)
    while y <= y1:
        yp = int((y - y0) * s)
        dr.line([(0, yp), (im.width, yp)], fill=(255, 0, 0), width=1)
        dr.text((2, yp + 1), str(y), fill=(255, 0, 0))
        y += 10
    x = 0
    while x <= W:
        xp = int(x * s)
        dr.line([(xp, 0), (xp, im.height)], fill=(0, 110, 255), width=1)
        dr.text((xp + 1, 1), str(x), fill=(0, 110, 255))
        x += 50

    im.save(out)
    print("page %d  band y[%g,%g]  width=%g pt  ->  %s (%dx%d)"
          % (idx, y0, y1, W, out, im.width, im.height))
    doc.close()


if __name__ == "__main__":
    main()
