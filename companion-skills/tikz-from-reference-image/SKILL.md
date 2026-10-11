---
name: tikz-from-reference-image
description: >-
  Recreate a supplied reference image as a procedural TikZ/PGF illustration, including organic texture and detailed subjects, through render-and-compare iterations. Use when a user explicitly wants an image reproduced in TikZ. Not for reviewing an existing figure, extracting PDF images or ordinary technical diagrams.
---

# Recreating a reference image as procedural TikZ

The goal is **minimal commands, maximal detail** — a faithful *stylized* vector
recreation, not a pixel trace. A few `\foreach` loops with random variation
produce thousands of strokes, so you get fur/spines/foliage texture from ~10
lines of code. Hand-place only the few details that carry recognizability
(eyes, nose, lettering).

## The one rule that matters most: render, look, adjust

You **cannot** tell whether the drawing matches by reading the code. Compile,
rasterize a page to PNG, and actually view it next to the reference. Then fix
what's wrong and repeat. Expect 4–8 iterations. Most early mistakes are
geometry (a feature in the wrong place), and they are invisible until you look.

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error fig.tex
pdftoppm -png -r 220 fig.pdf out      # then open out-1.png and compare
```

## Workflow

### 1. Measure the reference before drawing anything
Open the image. Estimate the position of every important landmark as a
**fraction of the frame** (x from the left 0→1, y from the top 0→1), then map
those fractions onto a fixed TikZ canvas (e.g. 0–10 in both axes, y up so
`y_tikz = (1 − y_frac)·10`). Write the landmark coordinates down *first*.

Skipping this and placing features "by eye" is the #1 cause of a result that's
"far from a likeness — the eyes aren't even in the right place." For a face,
pin the eye, the nose, and the head/body silhouette explicitly. Note which side
of the eye the catchlight is on, where the nose sits *relative to* the eye
(e.g. "down and to the right"), and the head tilt.

### 2. Block in form with shadings
Lay down the big masses with `\shade` (radial or axis) for base tone and
volume, and a soft radial ellipse for a ground/contact shadow. Pick **one light
direction** (e.g. upper-left) and commit to it — model every later tone by
position relative to that light.

### 3. Texture with `\foreach` (this is where the detail comes from)
Set `\pgfmathsetseed{N}` first so the texture is stable across recompiles
(change `N` to reroll). Useful patterns:

- **Radial strokes** (fur, spines, petals radiating from a body):
  root = `C + f·(a·cosθ, b·sinθ)`, tip = root + `L·(dir)`. Sample θ over the
  arc you want covered, `f` = radius factor (use `sqrt(rnd)` to bias roots to
  the edge), random `L`, width, and gray.
- **Flow strokes** (combed hair, directional fur): set each stroke's direction
  to point *away from an origin point* — `dir = atan2(ry−Oy, rx−Ox)` — so the
  whole coat fans out from one place (e.g. the face).
- **Surface fill texture**: `\clip` to a shape, then scatter short strokes over
  its bounding box. Clipping keeps only what's inside, so you can scatter
  freely without computing the boundary.
- **Layer in passes** for depth: dark underfur → main coat → light tips /
  highlights → a few long strays. A **wide tonal range** (`black!10`…`black!95`)
  is what reads as texture; low contrast looks like a smooth balloon.

### 4. Hand-draw the focal details
Eyes, nose, mouth, whiskers, text — draw these with explicit commands, not
randomness, because they carry the likeness. A convincing glossy eye = dark
radial shade, a dark upper-lid arc, a thin rim, and a **crisp catchlight
cluster** (2–4 small white dots) placed exactly where the reference has its
reflection. Match the reference's eye *shape* (often a tilted almond, not a
circle) and *placement* (usually near the optical center of the face).

### 5. Set expectations honestly
Procedural TikZ gives a clean, stylized recreation. Matching a polished photo
or graphite drawing exactly is not achievable with few commands — say so, then
iterate on whatever the user cares about most (usually the face/eyes).

## pgfmath / TikZ gotchas that waste time

- `($(x,y)+(ang:len)$)` coordinate arithmetic needs `\usetikzlibrary{calc}`.
- A macro immediately before `and` swallows the trailing space:
  `ellipse (\ax and \by)` expands to `ellipse (3.9and 2.9)` → "Unknown
  operator" error. Brace it: `ellipse ({\ax} and {\by})`.
- pgfmath has **no ternary / `ifthenelse`** by default. Use `max()`/`min()` to
  clamp (e.g. keep a gray in range: `max(6,min(95, expr))`), or put rare special
  cases in their own small loop.
- `rnd` = uniform [0,1]; `rand` = uniform [−1,1]; `atan2(y,x)` is in degrees and
  handles angles outside 0–360.
- Bias a value short: `rnd*rnd`. Bias roots to an edge: `sqrt(rnd)`.
- Keep stroke widths thin (≈0.2–0.6pt) and varied per stroke for fine texture.
- A few hundred strokes per loop compile in seconds; a few thousand total is
  fine.

## Minimal scaffold

```latex
\documentclass[border=10pt]{standalone}
\usepackage{tikz}
\usetikzlibrary{calc}
\begin{document}
\begin{tikzpicture}
\pgfmathsetseed{20240622}
% 1. shadings for form + shadow
% 2. \foreach texture passes (dark → main → highlights → strays)
% 3. hand-drawn eye / nose / details
\end{tikzpicture}
\end{document}
```

Then: compile → `pdftoppm -png -r 220` → **look** → adjust → repeat.
