---
name: hybrid-figure-triage
description: >-
  Choose per figure whether to redraw in TikZ/pgfplots, crop the original, or restore a text box. Use when transferring mixed diagrams, computed plots, photos and scans into a new LaTeX document. Routes the chosen method to figure-specific skills; does not itself translate the book.
---

# Hybrid figure triage: redraw vs crop, per figure

Carrying figures across into a new LaTeX document forces one choice per figure:
**redraw it as code** (TikZ/pgfplots — crisp, recolourable, scales perfectly,
text in the document font) or **crop the original** (a PNG out of the source PDF
— exact, instant, but a fixed-resolution bitmap). Doing all of one is the trap:
redraw-everything burns days on a Mandelbrot set no one should hand-code;
crop-everything litters a vector-text book with fuzzy diagrams. Triage each
figure first, then hand it to the right companion skill.

## The decision rule

**Redraw in TikZ/pgfplots** when the figure is *structural / geometric* — its
content is lines, curves, regions, labels, and arrows you can describe:
- domains and regions with boundary conditions; a region and its image under
  `w = f(z)`; conformal-mapping schematics;
- contours / integration paths, oriented curves, branch cuts;
- geometry: triangles, circles, angles, the unit circle, vectors;
- commutative-style diagrams, axis-and-label plots of a *known elementary*
  function you can express as `pgfplots` `\addplot {expr}`.

A redraw wins here because the result is razor-sharp at any zoom, picks up the
document's fonts and colours, and stays editable (relabel in the target language
for free).

**Crop the original raster** when the figure is *computed pixels* — reproducing
it means re-running someone's numerical code, and the value is in the exact
image:
- fractals (Mandelbrot/Julia, Newton basins, escape-time colourings);
- vector / direction fields, streamlines, equipotentials, isotherms, flow nets;
- density plots, contour/heat maps of a numerically-evaluated field;
- 3-D surface / domain-colouring renders;
- photographs, micrographs, or anything scanned.

Cropping wins because a hand TikZ version would be a days-long, lower-fidelity
imitation of pixels that already exist. Use `extract-pdf-figures` (grid-measure-
crop at 300 DPI) so the crop is pixel-accurate and free of header/caption.

**CROP + worded labels inside the raster → after cropping, apply
figure-label-translation** (patch-and-overlay the translations; math-symbol
labels need nothing).

**The tie-breaker, when a figure could go either way:** estimate the redraw cost.
A handful of `\draw`/`\addplot` lines → redraw. A `\foreach` over thousands of
sample points to fake a field, or hand-placed colour that only approximates a
computed result → crop. If you cannot reproduce the *data*, you are imitating
pixels — crop.

**Text plaques are a separate route.** A shaded definition, postulate or named
principle may be misclassified as an image by OCR. Inspect before redraw/crop:
translate and re-typeset its text while preserving formulas and numbering.
A shaded numbered equation without prose is not a textual plaque. Do not send
all such crops through a second unbounded OCR job or silently discard them.

## Reality checks (these override the rule)

- **No working plotting backend → crop.** If the environment has no usable
  Python/numerics to regenerate a computed plot (and `pgfplots` can't evaluate it
  from a closed form), the computed figure **must** be cropped — there is no
  honest way to redraw data you can't compute. Don't fake it with decorative
  noise.
- **Redraw needs the source legible.** You can only redraw what you can read. If
  the figure's labels/values aren't legible in the source render, either zoom the
  region (extract-pdf-figures' grid) until they are, or crop.
- **Author intent / annotation.** If the figure carries hand annotations or a
  specific look the text discusses, crop so you preserve exactly what's referenced.

## Making crops and redraws coexist

A book that mixes both shouldn't *look* mixed:
- Crop at **300 DPI** so raster figures are sharp next to vector text.
- Match the crop's drawn width to neighbouring TikZ figures (`\includegraphics`
  `width=` ≈ the `\linewidth` fraction your TikZ figures use) so figure sizes
  read as one family.
- Trim the original's caption and re-typeset the caption yourself in the target
  language (российская традиция: "Рис. N.M." with a period, `labelsep=period`),
  so cropped and redrawn figures share one caption style.
- Keep the crop's background white/transparent and exclude the page's running
  head (the #1 bad-crop cause — see extract-pdf-figures).

## scripts/figure_probe.py
A quick heuristic to support the call on a *born-digital* PDF: it reports, for a
page region, how much is raster image vs vector drawing ink. Lots of raster area
≈ a computed/photo figure → lean **crop**; mostly vector strokes with little/no
raster ≈ line art → lean **redraw**. It is a hint, not a verdict — your read of
*what the figure is* (data vs geometry) decides. Needs PyMuPDF (`fitz`), same as
extract-pdf-figures.

## Companion skills
- **tikz-from-reference-image** — execute the redraws (procedural TikZ, render→look→adjust).
- **extract-pdf-figures** — execute the crops (grid-measure bbox, 300 DPI clip, montage-verify).
- **translate-book-to-latex** / **multiagent-latex-production** — the surrounding per-chapter / fanned-out pipeline this triage feeds.
