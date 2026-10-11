#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Heuristic: is a figure region mostly raster (crop it) or vector (redraw it)?

Usage:
    figure_probe.py PDF PDF_INDEX [Y0 Y1]

PDF_INDEX is the 0-based page index (book page minus front-matter offset minus 1;
see extract-pdf-figures). Optional Y0 Y1 (points, top-left origin, y down) limit
the probe to a horizontal band so a header/caption/other figure on the same page
don't skew the reading; omit them to probe the whole page.

It reports, within the region:
  - raster image coverage   = (image bbox area inside region) / region area
  - vector path count + their bbox coverage
and prints a LEAN: crop / redraw. This is only a hint from born-digital metadata
(PyMuPDF get_image_info + get_drawings); a scanned page is 100% raster by
construction, and the real decision is "is this computed data or is it geometry"
(see SKILL.md). Use it to support the call, not to make it.

Requires PyMuPDF (fitz). On Windows invoke via the py launcher, e.g. py -3.9.
"""
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.stderr.write("PyMuPDF (fitz) not installed: pip install pymupdf\n")
    sys.exit(2)


def area(r):
    return max(0.0, r.width) * max(0.0, r.height)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    idx = int(sys.argv[2])
    doc = fitz.open(path)
    page = doc[idx]

    if len(sys.argv) >= 5:
        y0, y1 = float(sys.argv[3]), float(sys.argv[4])
        region = fitz.Rect(0, y0, page.rect.width, y1)
    else:
        region = fitz.Rect(page.rect)
    reg_area = area(region) or 1.0

    # raster images intersecting the region
    raster_area = 0.0
    n_images = 0
    for info in page.get_image_info(xrefs=True):
        bbox = fitz.Rect(info["bbox"])
        inter = bbox & region
        if not inter.is_empty:
            n_images += 1
            raster_area += area(inter)
    raster_cov = raster_area / reg_area

    # vector drawing paths intersecting the region
    n_paths = 0
    vector_area = 0.0
    for d in page.get_drawings():
        bbox = fitz.Rect(d["rect"])
        inter = bbox & region
        if not inter.is_empty:
            n_paths += 1
            vector_area += area(inter)
    vector_cov = vector_area / reg_area

    print("region: %.0f x %.0f pt" % (region.width, region.height))
    # raster coverage can exceed 100% when image tiles overlap (a fractal is
    # often hundreds of stacked tiles); vector coverage sums path bboxes and
    # double-counts overlaps, so it is only a rough "is there vector ink" signal
    # and the path COUNT is the more honest number.
    print("raster: %d image(s), coverage %.1f%%" % (n_images, 100 * raster_cov))
    print("vector: %d path(s), bbox coverage ~%.1f%% (approx; bboxes overlap)"
          % (n_paths, 100 * vector_cov))

    # A substantial real raster image => CROP, regardless of how much vector
    # clutter (axes, labels, frame) sits around it: you crop the whole figure.
    # Only when raster is negligible and there is genuine vector ink => REDRAW.
    if raster_cov >= 0.15:
        lean = "CROP (computed/photo raster present) -> extract-pdf-figures"
    elif n_images > 0 and n_paths == 0:
        lean = "CROP (raster-only region) -> extract-pdf-figures"
    elif n_paths > 0 and raster_cov < 0.05:
        lean = "REDRAW (vector line art) -> tikz-from-reference-image"
    elif n_images == 0 and n_paths == 0:
        lean = "UNKNOWN (no image/vector metadata -> likely a scan; CROP)"
    else:
        lean = "MIXED -> decide by content: data=CROP, geometry=REDRAW"
    print("lean:   %s" % lean)


if __name__ == "__main__":
    main()
