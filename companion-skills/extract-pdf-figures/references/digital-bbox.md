# Born-digital shortcut: detecting figure bboxes from PDF metadata

For PDFs that are **not** flat scans (they have real vector/raster objects), you
can often get a figure's bbox without the grid. Two sources:

## Raster images
```python
import fitz
page = doc[idx]
for im in page.get_images(full=True):
    for r in page.get_image_rects(im[0]):
        print(round(r.x0), round(r.y0), round(r.x1), round(r.y1))
```
Photos, 3D renders, and scanned insets show up here directly.

## Vector drawings (line art)
Cluster the rectangles returned by `page.get_drawings()`:
```python
W = page.rect.width
rects = [d['rect'] for d in page.get_drawings()
         if d['rect'].width > 1 and d['rect'].height > 1]
X0 = min(r.x0 for r in rects); Y0 = min(r.y0 for r in rects)
X1 = max(r.x1 for r in rects); Y1 = max(r.y1 for r in rects)
```

## Why the vector union often LIES — and the filters that fix it

The naive union is frequently polluted, giving a bbox far bigger than the figure:

- **Footnote rules / horizontal lines**: very wide, ~1 pt tall. Drop with
  `r.width < 0.7 * W`.
- **Large math delimiters**: integral signs, big braces/parens, matrix brackets,
  and `\left…\right` are drawn as **tall thin vector glyphs**. Drop with
  `not (r.height > 22 and r.width < 11)`.
- **tcolorbox / framed-result borders**: a boxed equation elsewhere on the page
  contributes a big rectangle. Constrain to the figure's band:
  `r.y0 > Y_top and r.y1 < Y_bot`.
- **Wrapfigure pollution**: text-column rules. Constrain `x` to the figure's
  column.

A robust recipe — cluster the figure as the group of rects nearest the caption:

```python
caps = page.search_for("[%s]" % figure_label)   # e.g. "[3.5]" or "Figure 7"
anchor = caps[0]                                 # caption sits next to the figure
R = [...]                                        # filtered rects (see above)
seed = min(R, key=lambda r: abs((r[1]+r[3])/2 - anchor.y0))
cluster = [seed]
changed = True
while changed:                                   # grow by proximity (gap < ~18pt)
    changed = False
    for r in R:
        if r in cluster: continue
        if any(_near(r, c, 18) for c in cluster):
            cluster.append(r); changed = True
bbox = union(cluster)
```

## When in doubt, grid it
If the metadata bbox looks even slightly wrong in the montage, **abandon it and
use `grid_overlay.py`** — measuring beats filtering. Scans give you no choice:
the whole page is one image, so `get_drawings()`/`get_images()` return nothing
useful and the grid is mandatory.

## Locating the caption / page offset
- `page.search_for("[3.5]")` (or `"Figure 7"`) returns the caption-label rects;
  the figure is the band directly above (or, for some books, below) it. Beware:
  the same label often also appears inline in body text — the **caption** is the
  occurrence with figure ink adjacent to it, usually the left-margin / centered
  one just under the figure.
- Find the **book-page to pdf-index offset** once: render a known content page,
  read its printed number, then `pdf_index = book_page - offset - 1`.
