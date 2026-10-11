# Placement recipe: LaTeX overlay (primary) and pixel edit (fallback)

## 1. The overlay skeleton

```latex
% preamble: \usepackage{graphicx,tikz,xcolor}
% colours come from scripts/sample_bg.py — one per distinct background:
\definecolor{figbg}{RGB}{253,253,253}

\begin{tikzpicture}
  \node[anchor=south west,inner sep=0] (img)
    {\includegraphics[width=\linewidth]{fig.jpg}};
  \begin{scope}[x={(img.south east)},y={(img.north west)}]
    % patch first (covers the ORIGINAL label + 2–3 px), then the node:
    \fill[figbg] (0.28,0.66) rectangle (0.44,0.72);
    \node[anchor=center,fill=figbg,inner sep=1pt,font=\small]
      at (0.36,0.69) {единичная окружность};
  \end{scope}
\end{tikzpicture}
```

Inside the scope, `(x,y)` are **relative 0..1 coordinates, origin
bottom-left**: `x` multiplies the vector to `img.south east`, `y` the vector
to `img.north west`. Consequences worth having:

- DPI- and width-independent: change `width=12cm` to `0.8\linewidth` later —
  every label stays put.
- The same numbers flow verbatim between `relgrid.py` (where you read them),
  `labels.tsv` (where they live) and the emitted TikZ.

Why the overlay is the default:

- the replacement text is **vector**, typeset in the **book's own font**, and
  **searchable/selectable** in the PDF;
- a wording fix is a one-line edit + recompile — no image regeneration;
- the original raster is untouched on disk (reversible, re-reviewable);
- rotation (`rotate=90` for y-axis labels) and math (`\(\Phi\)`) come free.

## 2. Taking coordinates

- **Standalone raster** (the usual case — extracted book figures):
  `py -3 scripts/relgrid.py fig.jpg [--step 0.02]` overlays a labelled
  relative grid; read label centres and patch corners off it.
- **Figure still inside a PDF page**: extract-pdf-figures'
  `grid_overlay.py` (grid in PDF points) + `crop_figure.py` first; overlay
  the extracted raster.
- Read the label TEXT by eye from the (zoomed) image — at figure resolutions
  and rotations, your vision beats mechanical OCR; there is nothing to
  install and nothing to mis-recognise silently.

## 3. Patches: the four rules the trial paid for

1. Size the patch to the **original** label (+2–3 px), not to the replacement
   — a shorter Russian word leaves the original's tail visible («ГРИНN»).
2. **Never assume white.** Sample with `scripts/sample_bg.py` (`--rect` band
   for a tight bbox, `--at` point probe next to the text when the
   neighbourhood is busy). Real values from one book: 253, 193, 192, 148.
3. A patch must stay **inside the background region it was sampled from** —
   crossing an ink boundary (a ground line, a curve) erases it and shows a
   wrong-colour plate on the other side.
4. Keep patches minimal: scan backgrounds have JPEG gradients, and a large
   flat plate becomes faintly visible even at the right median colour. If a
   thin curve must cross the label area, let it — the original looked that
   way too.

One figure can need **several** colours (grey band + white body + grey disk):
that is what the `bgcolor` column in labels.tsv is for.

## 4. Verification (non-negotiable)

Render the compiled page (PyMuPDF: `page.get_pixmap(matrix=fitz.Matrix(2.2,
2.2))`) and **look**; then re-render each label region at **3–4× zoom**. The
whole-page view catches layout; only the zoom catches a ghost of the original
text peeking from under a mis-placed patch (found in the trial at page scale:
invisible; at 3.5×: obvious). Same doctrine as latex-figure-review: the
compiler sees none of this.

## 5. Fallback: pixel edit (Pillow)

When the image *leaves* the LaTeX contour (delivered as standalone PNG/JPG,
web export, DOCX insert) or carries **dozens of micro-labels** where one
overlay per label is unmanageable, edit pixels instead:

```python
from PIL import Image, ImageDraw, ImageFont
im = Image.open("fig.jpg").convert("RGB")
d = ImageDraw.Draw(im)
d.rectangle([x0-3, y0-3, x1+3, y1+3], fill=(193,193,193))   # sampled bg, +margin
font = ImageFont.truetype("DejaVuSans.ttf", 22)              # has Cyrillic
d.text(((x0+x1)//2, (y0+y1)//2), "единичная окружность",
       font=font, fill=(20,20,20), anchor="mm")
im.save("fig.jpg", "JPEG", quality=95, progressive=False)    # baseline RGB!
```

Traps (all real):

- **JPEG halos**: compression ringing hugs the old glyphs — fill the bbox
  with a 2–3 px margin or the ghost outline survives.
- **Font**: pick one with Cyrillic coverage (DejaVu Sans/Serif); the default
  PIL bitmap font has none.
- **Resave discipline**: baseline RGB JPEG (`progressive=False`, no CMYK),
  or the TeX driver that consumes the image later will reject it
  (see pdf-book-extraction / reencode_images.py).
- The edit is destructive — keep the original under a `.orig` name; the
  labels.tsv registry still records what was changed and where.

## 6. Scale discipline

Pick the overlay `font=` size so the replacement is optically the same size
as neighbouring in-figure text at the FINAL printed width (compare in the
render, not in the source pixels). If the book renders the figure at
`0.8\linewidth`, verify at that width — a label that looks right at 12 cm can
crowd at 9 cm.
