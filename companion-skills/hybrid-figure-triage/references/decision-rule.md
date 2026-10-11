# Worked triage: a complex-analysis textbook, figure by figure

Concrete precedent for the redraw-vs-crop call, from carrying ~370 figures of a
complex-analysis text into a Russian LaTeX rebuild. Use it to calibrate: the same
*kinds* of figure recur across math/physics/engineering books.

## Went to TikZ / pgfplots (redraw)

| Figure kind | Why redraw |
|---|---|
| A region `D` and its image `f(D)` under `w = f(z)` | Two labelled blobs + arrow; pure geometry, relabels into Russian for free |
| Conformal-mapping schematics (z-plane ↔ w-plane grids) | Lines and a transformed grid you can describe; crisp at any zoom |
| Contours / integration paths, oriented with arrowheads | `\draw` + `decorations.markings`; a few strokes |
| Branch cuts, the unit circle, sectors, annuli | Circles, arcs, hatched regions — `patterns`, `angles` |
| Triangle-inequality / geometry diagrams | Points, segments, an angle mark |
| Plots of a *known elementary* function (`sin`, `e^x`, a Möbius image) | `pgfplots \addplot {expr}` evaluates the closed form exactly |
| Pole/zero diagrams, labelled axis figures | Marks + labels on axes |

## Went to cropped original (raster)

| Figure kind | Why crop |
|---|---|
| Mandelbrot / Julia sets, Newton-basin colourings | Escape-time pixels; no closed form to redraw, only the image |
| Vector / direction fields, streamlines | Hundreds of computed arrows; a TikZ `\foreach` fake is slower *and* worse |
| Equipotentials, isotherms, flow nets (fluid/heat chapters) | Numerically-solved field; the value is the exact computed curve set |
| Density / contour / domain-colouring plots | Per-pixel colour from a numeric evaluation |
| 3-D surface renders | Rasterized render; recreating the camera + shading isn't worth it |
| Any photo / scan | Nothing to redraw |

## The line that decided the hard cases

> Can I reproduce the **data**, or only the **pixels**?

A figure you could redraw "if you had the numbers" but you *don't have the
numbers and can't compute them here* is a CROP — imitating the pixels with
decorative noise is dishonest and looks worse. A figure whose content is fully
described by geometry you can write down is a REDRAW.

## Practical notes from the run

- **No numerics backend = forced crop.** When the environment had no working
  Python/plotting to regenerate field plots and fractals, every computed figure
  was cropped at 300 DPI — there was no honest redraw path. Don't pretend.
- **Crop the whole computed figure, axes included.** A fractal framed by vector
  axis lines is still one CROP — don't redraw the axes and try to inset the
  raster; you'll get a seam. `figure_probe.py` leans CROP whenever a real raster
  covers ≥15% of the region precisely so the surrounding vector clutter doesn't
  pull you toward a redraw.
- **Match sizes so the page reads as one family.** Set cropped
  `\includegraphics[width=...]` to the same `\linewidth` fraction the TikZ
  figures use, and re-typeset every caption yourself (российская традиция:
  "Рис. N.M." with a trailing period) so redrawn and cropped figures share one
  look. See extract-pdf-figures for header/caption-free cropping and
  tikz-from-reference-image for the redraws.
