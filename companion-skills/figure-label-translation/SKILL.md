---
name: figure-label-translation
description: >-
  Translate worded labels inside raster figures while preserving their imagery, using sampled-background LaTeX overlays or a pixel-edit fallback. Use when captions are translated but axis labels, legends or words inside figures remain in the source language. Do not apply to pure mathematical symbols or figures already being redrawn.
---

# Translating the words inside raster figures

A translated book keeps many figures as raster crops (see hybrid-figure-triage
for why). The pixels are fine — but "unit circle", "sea level", "DISK POISSON"
inside them are not. Redrawing the whole figure to fix three words is waste;
shipping English labels in a Russian book is a defect. This skill closes that
gap: replace only the words, leave the picture alone.

## 0. Triage first (three-way, cheap)

1. **Labels are pure math** (`z`, `w`, `θ`, `f(z)`, `2+i`) — universal
   notation, no translation needed. Raster goes across untouched. Stop here.
2. **Figure is already routed to a TikZ redraw** (hybrid-figure-triage said
   REDRAW) — the redraw retypesets every label anyway; translating the raster
   first would be double work. Stop here.
3. **Worded labels on a figure that stays raster** — this skill.

## 1. Primary strategy: LaTeX overlay (no pixel is harmed)

```latex
\begin{tikzpicture}
  \node[anchor=south west,inner sep=0] (img)
    {\includegraphics[width=\linewidth]{fig.jpg}};
  \begin{scope}[x={(img.south east)},y={(img.north west)}]  % coords 0..1
    \fill[figbg] (0.28,0.66) rectangle (0.44,0.72);  % patch over the original
    \node[anchor=center,fill=figbg,inner sep=1pt,font=\small]
      at (0.36,0.69) {единичная окружность};
  \end{scope}
\end{tikzpicture}
```

Relative 0..1 coordinates (origin bottom-left) make the overlay independent of
DPI and of the printed width — resize the figure later, labels stay put. The
replacement text is **vector**, in the **book's own font**, **searchable** in
the PDF, fixable by a one-line edit without regenerating any image, and the
original raster on disk is untouched. Full recipe, patch rules and the pixel
fallback: `references/placement-recipe.md`.

**The patch colour is never `white` by default.** Extracted/scanned figures
have cream, grey, or shaded backgrounds (one real book gave 253, 193, 192 and
148 across three figures — including a "white" area that was actually a grey
half-plane). Sample the pixels next to the label:

```
py -3 scripts/sample_bg.py fig.jpg --rect 0.28 0.66 0.44 0.72   # band around bbox
py -3 scripts/sample_bg.py fig.jpg --at 0.36 0.69               # point probe
```

— it prints the ready `\definecolor{figbg}{RGB}{...}`. Use `--at` when the
band around a wide bbox would cross ink or shading. Labels on different
backgrounds in one figure need different sampled colours (the `bgcolor`
column).

## 2. Coordinates and reading the labels

- Standalone raster (the usual case): `py -3 scripts/relgrid.py fig.jpg`
  draws a labelled **relative 0..1 grid** over the image — read label centres
  and patch corners straight off it (`--step 0.02` for dense figures).
- Figure still inside a PDF page: measure with extract-pdf-figures'
  `grid_overlay.py` (points grid) and crop first; then overlay the crop.
- **You are the OCR.** Read each label by eye from the (zoomed) image.
  Mechanical OCR on small, rotated, math-mixed figure text fails silently and
  adds a dependency for nothing.

## 3. The label registry: labels.tsv

One row per label, one file per figure batch — the resumable, reviewable
artifact of the job:

```
figure  text_src  text_target  x  y  anchor  rotate  size  status  patch  bgcolor
```

(`patch` = `x0,y0,x1,y1` rectangle to fill before the node; `bgcolor` defaults
to `figbg`; `status`: todo/done/skip.) Generate the LaTeX from it:

```
py -3 scripts/labels_to_tikz.py labels.tsv --width 12cm > overlays.tex
```

Translations of the labels go through the **project glossary**
(translation-glossary-builder) — short in-figure words are exactly the
trap-term territory: image ⇒ образ (не «изображение» in mapping contexts),
source ⇒ источник (гидродинамика), sink ⇒ сток. Decide once in the glossary,
let the registry carry the decision.

## 4. Verify with your eyes (the compiler sees nothing)

Render the compiled figure (PyMuPDF pixmap at ~2.2×) and **look** — then
re-render **each label region at 3–4× zoom**. The trial that produced
`references/worked-example.md` caught three real defects this way, two of
them invisible at page scale:

- a patch sized to the (shorter) replacement let the original's tail show
  («ГРИНN») — patch the ORIGINAL's extent plus 2–3 px;
- a patch crossed the ink boundary it was sampled inside and greyed the white
  region beyond, eating marker squares — ink boundaries are patch boundaries;
- a label placed from a coarse grid reading left the original's ghost peeking
  from below — visible only in the zoom crop.

Fix labels.tsv, regenerate, recompile, re-look. Two-three iterations is
normal; each is seconds. Same doctrine as latex-figure-review.

## 5. Fallback: pixel edit (Pillow)

When the image leaves the LaTeX contour (standalone deliverable, web, DOCX)
or carries dozens of micro-labels, edit the pixels: fill the bbox with the
sampled colour **with 2–3 px margin** (JPEG halos hug the old glyphs), draw
the text with a Cyrillic-capable font (DejaVu), resave **baseline RGB**
(progressive/CMYK JPEGs crash TeX drivers later — pdf-book-extraction owns
that lesson). Details and the code skeleton: `references/placement-recipe.md`
§5. Keep the original under `.orig`; the registry still records the change.

## Worked example

`references/worked-example.md` — three real figures from a translated
book, 10 labels, 4 sampled backgrounds, 3 iterations, and final labels.tsv
coordinates. Book images are intentionally excluded from the public package;
use your own authorized figures to reproduce the method.

## Companion skills

- **hybrid-figure-triage** — decides which figures stay raster; its CROP +
  worded-labels outcome routes here.
- **extract-pdf-figures** — produces the raster crops this skill relabels;
  its `grid_overlay.py` measures figures still inside a PDF.
- **tikz-from-reference-image** — the other route: full redraw (labels come
  free there).
- **translation-glossary-builder** — where the label translations are decided.
- **latex-figure-review** — the render-and-look verification doctrine this
  skill reuses per label.
- **pdf-book-extraction** — upstream extraction and the baseline-RGB resave
  discipline for the pixel fallback.
- **translate-book-to-latex** / **local-mt-batch** — the two translation
  pipelines whose figures this skill finishes.
