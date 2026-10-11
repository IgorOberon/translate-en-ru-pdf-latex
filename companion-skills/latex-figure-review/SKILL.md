---
name: latex-figure-review
description: >-
  Visually review and fix LaTeX/TikZ figures (diagrams, plots, commutative
  squares, block diagrams) by rendering each one to an image and actually
  looking at it. Use this whenever a user reports that figures "overlap",
  "collide", "look cramped", "are too faint/transparent", "too small", "ugly",
  "labels run into each other", or asks to review/clean up/polish the figures in
  a LaTeX document, book, paper, or course — even if they only point at one
  figure. Compilation succeeding (0 errors) does NOT mean a figure looks right:
  overlaps, buried labels, and bad contrast are invisible to the compiler, so
  always render-and-inspect rather than trusting the build. Also use to audit a
  whole figure set for layout problems.
  Russian phrasings that must trigger it too — «рисунки наезжают друг на
  друга», «подписи слиплись с линиями», «фигуры бледные/тесные — приведи в
  порядок», «проверь все рисунки книги глазами».
---

# LaTeX / TikZ figure visual review

## Why this exists

A LaTeX project can compile with **zero errors** and still have figures where the
title overlaps a box, two labels sit on top of each other, an arrow is buried in
text, a fill is so faint it's invisible, or a panel is cramped. The compiler
cannot see any of this. The only reliable way to find and fix these problems is
to **render each figure to an image and look at it**, fix, then **re-render to
confirm**. This skill is that loop.

It works for any TikZ/PGF figures: vector diagrams, plots, commutative diagrams,
block/matrix diagrams, multi-panel comparisons, etc.

## The loop

1. **Generate** a cropped, one-figure-per-page preview of all (or selected) figures.
2. **Render** the pages to PNG.
3. **Inspect** each image — look for the problems catalogued below.
4. **Fix** the offending `.tex` figure source.
5. **Re-render** the changed figures and confirm the fix visually.

Steps 1–2 use `scripts/gen_figcrop.py` + `pdftoppm`. Steps 3–5 are you, reading
the PNGs with your vision and editing the source.

### 1–2. Generate and render

`scripts/gen_figcrop.py` builds a `standalone` document with
`multi=tikzpicture,crop`, so **each `tikzpicture` becomes its own tightly-cropped
page** (no page whitespace — far more token-efficient to view than full A4 pages,
and the figure fills the frame).

```bash
# From the project root. --preamble points to a file with the setup lines the
# figures need (the project's \input{preamble}, macros, and any \def the figures
# assume — see note below). --glob selects the figure files.
python /path/to/skill/scripts/gen_figcrop.py \
    --root . \
    --glob "figures/**/*.tex" \
    --preamble figcrop_preamble.tex \
    --out _figcrop.tex

# Compile from the project root (so relative \input paths resolve), then crop-render:
xelatex -interaction=nonstopmode -output-directory=build _figcrop.tex
pdftoppm -png -r 110 build/_figcrop.pdf build/fc      # -> build/fc-001.png ...
```

The script writes `build/figcrop_map.txt` mapping **page number → figure file**, so
when you view `fc-NNN.png` you know which source to edit. Read it first.

**The preamble file** must reproduce what the figures rely on at the point they're
`\input`. Typically: the project preamble, the macro file, and any flag the
figures assume is set when included in the main document. Example contents:

```latex
\input{00_preamble}
\input{00_macros}
\def\incourse{1}   % if figures are normally \input'd inside the book with this set
```

If a project uses a non-standard build (custom class, fonts via fontspec, biber),
just mirror the master document's preamble. If `gen_figcrop.py` fails to compile,
fix the preamble file first — the figures themselves are usually fine.

> Engine: use the engine the project uses (`xelatex`/`lualatex` for fontspec/Unicode,
> else `pdflatex`). `pdftoppm` ships with poppler; `pdftocairo`, ImageMagick
> `magick`, or `mutool draw` also work.

### 3. Inspect — what to look for

Read the PNGs (your vision tool). For each figure check:

- **Overlaps / collisions** — title over a box; two labels on the same spot;
  a legend/caption box riding over content above it; arrow labels colliding.
- **Buried elements** — an arrow or marker drawn *under* a filled node; a label
  hidden behind a box with no white background.
- **Low contrast / "too faint"** — fills like `X!3`–`X!8`, dashed strokes at
  `!30`–`!40`, `opacity=0.3–0.5` on important marks. They read as invisible.
- **Cramped / too small** — labels packed into a tiny sub-panel; a figure that's
  much smaller than its neighbours.
- **Draft leftovers** — stray `\draw` with no path, debug comments, half-finished
  alternative versions, "TODO"/"FIXME"/"VERIFY" text that renders.
- **Scrambled data** — labels placed at the wrong coordinates (e.g. row labels
  off-by-one). These are real *bugs* the compiler won't catch — watch for them.

To triage a **large** figure set efficiently, rank by overlap risk first
(`scripts/score_figures.py`): figures with many `text width` nodes, multiple
`\begin{scope}`, bold "title" nodes, and faint fills are the likely offenders.
Inspect those first; simple single-vector diagrams are almost always clean.

### 4. Fix

See `references/fix-patterns.md` for the concrete, repeatable fixes (move title
clear, raise opacity, spread labels, give labels a white background, remove buried
arrows, enlarge via `scale`). Apply the **minimal** repositioning that resolves
the collision; don't redesign a clean figure.

### 5. Re-render and confirm

Re-run `gen_figcrop.py` (or a small wrapper with just the changed figures) and
view the PNGs again. **Do not consider a figure done until you've seen the fixed
render** — a coordinate nudge can create a new overlap elsewhere.

## Output / reporting

When reviewing a set, report: how many figures inspected, which were changed and
what the problem was, and confirm each fix was verified by render. Keep a one-line
note per fixed figure (figure id → problem → fix).

## Cleanup

The `_figcrop.tex`, `figcrop_preamble.tex`, and `build/fc-*.png` are scratch —
remove them when done (the generator regenerates on demand).
