---
name: extract-pdf-figures
description: >-
  Extract individual figures (diagrams, plots, photos, 3D renders) out of a PDF
  page as clean cropped PNGs, with pixel-accurate bounding boxes. Use this
  whenever you need to pull figures from a book/paper/scan to re-insert them into
  a new document (e.g. a translation, a rebuild, a slide deck), or whenever a
  blind bbox guess keeps grabbing the page header, the figure caption, or
  neighbouring body text. Works for both born-digital PDFs (vector + raster) and
  scanned PDFs where the whole page is one raster image. The core trick is to
  render the page with a labelled coordinate grid, read the figure's exact
  point-coordinates off the grid, then clip at high DPI — instead of guessing and
  re-cropping over and over. Always verify each crop by building a montage and
  looking at it.
  Russian phrasings that must trigger it too — «вырежи рисунки из PDF»,
  «вытащи картинку со страницы N», «достань иллюстрации из книги в PNG», «кроп
  всё время цепляет подпись/колонтитул».
---

# Extracting figures from a PDF

## Why this exists

Re-using a figure from a PDF (a scan, a book, a paper) means cropping a precise
rectangle out of a page. Guessing the rectangle by eye is slow and unreliable:
the crop ends up including the **page header**, the **"Figure N" caption**, a
slice of **body text**, or it **clips the figure**. Each wrong guess costs a
re-render. This skill replaces guessing with **measuring**: overlay a coordinate
grid on the page, read the figure's bounding box in PDF points directly off the
grid, clip once, and confirm with a montage.

It assumes [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) and Pillow (`PIL`)
are installed. On Windows invoke Python via the `py` launcher (e.g. `py -3.9`);
elsewhere `python3`.

## Key facts about PDF coordinates

- A PDF page has a coordinate system in **points** (1/72 inch). `page.rect`
  gives `(0, 0, width, height)`. A typical 6×9 book page is ~`392 × 652` pt; A4
  is `595 × 842` pt. The origin is **top-left**, y increases **downward**.
- To render at N DPI use `matrix=fitz.Matrix(N/72, N/72)`. To crop, pass
  `clip=fitz.Rect(x0, y0, x1, y1)` in **points**.
- **Book page ≠ PDF page.** Front matter shifts them. Find the offset once: open
  a known content page, read its printed page number, subtract. Then
  `pdf_index = book_page + offset` (0-based index = that minus 1).

## The loop

1. **Locate** the figure's page (`pdf_index`) and roughly which band it's in
   (top / middle / bottom). For scanned pages, render the page and look.
2. **Grid** that band: `scripts/grid_overlay.py` renders it with red horizontal
   rules every 10 pt (labelled) and blue verticals every 50 pt.
3. **Read** the figure's bounding box `(x0, y0, x1, y1)` directly off the grid —
   the outermost figure ink, *excluding* the page header above and the
   `Figure N` caption below.
4. **Crop** at 300 DPI: `scripts/crop_figure.py`.
5. **Verify**: `scripts/montage.py` tiles all crops into one image; open it with
   the Read tool and look. Re-grid + re-crop any that are wrong.

For **born-digital** pages you can often skip the grid: `get_image_rects()`
gives raster bboxes directly, and clustering `get_drawings()` rects gives vector
bboxes (see `references/digital-bbox.md`). But scans have no such metadata — the
grid is the only reliable method, and it also rescues digital figures whose
vector union is polluted by large integral signs / matrix delimiters / tcolorbox
rules.

## What to cut, and common traps

- **Page header / running head** (top ~y 30–58 on a 6×9 book): always exclude.
  It is the #1 cause of a "why is there text at the top of my figure" crop.
- **`Figure N` caption** (just below the figure): exclude — you typeset the
  caption yourself in the target document.
- **Body text beside a wrapfigure**: a figure that the text flows around lives in
  one column. Clip `x` to that column (e.g. right half only) or the opposite
  column's prose bleeds in.
- **Multi-panel figures** ([a]/[b]/[c]): grab the whole group in one crop; don't
  split panels unless the target layout needs it.
- **Labels that overhang** (an arrow tip, an axis label, a brace) extend the true
  bbox a few pt past the obvious figure body — include them.
- A figure can be **taller than one render band**; if the band shows it cut at an
  edge, grid the adjacent band and extend.

## Scripts

- `scripts/grid_overlay.py PDF PDF_INDEX Y0 Y1 [OUT.png]` — render page-region
  `[Y0,Y1]` (points) with a labelled coordinate grid. Read bboxes off it.
- `scripts/crop_figure.py PDF PDF_INDEX X0 Y0 X1 Y1 OUT.png [DPI]` — clip and
  save one figure (default 300 DPI).
- `scripts/montage.py OUT.png IMG1 IMG2 ...` — tile crops into one montage for
  visual verification.

All three are tiny and dependency-light; read them before first use.

See `references/digital-bbox.md` for the born-digital shortcut (vector/raster
bbox detection and how to filter out the pollution that makes it fail).
