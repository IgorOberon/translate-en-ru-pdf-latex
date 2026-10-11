# Worked example: three Needham figures, ten labels, three iterations

Live trial of the overlay method on real extracted figures from the Visual
Complex Analysis translation project (MinerU-extracted JPEGs,
`needham_ocr_ru\build\images`, hash-named). Every number below is real.
The book-derived before/after image is not redistributed in this public package.
The measurements below document the method; use your own authorized figures.

## The figures

| Trial name | Source (hash prefix) | Size px | Verbal labels |
|---|---|---|---|
| fig_panel.jpg | 28b1931f… | 909×823 | Simple Crosspoint, Vortex, Sink, Double Crosspoint, Dipole |
| fig_poisson.jpg | 4a979346… | 909×773 | DISK POISSON, GAUSS, GREEN, HALF PLANE POISSON |
| fig_equalphi.jpg | aee61c27… | 901×854 | equal Φ (word + math, on a grey disk) |

Triage note: a fourth candidate (7bd8a79f…, streamlines with `2+i`, `2−i`, `0`)
was **rejected** — labels are pure math symbols, no translation needed, raster
goes across untouched.

## Background colours (scripts/sample_bg.py, median over band)

```
fig_panel.jpg    near-white panel   figbg    RGB 253,253,253   (NOT 255!)
fig_poisson.jpg  top grey band      pgrey    RGB 193,193,193
fig_poisson.jpg  bottom half-plane  pbot     RGB 192,192,192
fig_equalphi.jpg grey disk          diskgrey RGB 148,148,148
```

Four different backgrounds in three figures — this is why the `bgcolor`
column exists and why "just use white" fails.

## The registry (final labels.tsv, after iteration 3)

```
figure	text_src	text_target	x	y	anchor	rotate	size	status	patch	bgcolor
fig_panel.jpg	Simple Crosspoint	Простое пересечение	0.23	0.955	center	0	small	done	0.10,0.935,0.36,0.975	figbg
fig_panel.jpg	Vortex	Вихрь	0.55	0.955	center	0	small	done	0.50,0.935,0.60,0.975	figbg
fig_panel.jpg	Sink	Сток	0.83	0.955	center	0	small	done	0.79,0.935,0.875,0.975	figbg
fig_panel.jpg	Double Crosspoint	Двойное пересечение	0.22	0.038	center	0	small	done	0.09,0.015,0.35,0.065	figbg
fig_panel.jpg	Dipole	Диполь	0.715	0.038	center	0	small	done	0.655,0.015,0.78,0.065	figbg
fig_poisson.jpg	DISK POISSON	ПУАССОН: КРУГ	0.16	0.555	center	0	small	done	0.045,0.53,0.275,0.582	pgrey
fig_poisson.jpg	GAUSS	ГАУСС	0.50	0.555	center	0	small	done	0.445,0.53,0.555,0.582	pgrey
fig_poisson.jpg	GREEN	ГРИН	0.83	0.555	center	0	small	done	0.78,0.53,0.895,0.582	pgrey
fig_poisson.jpg	HALF PLANE POISSON	ПУАССОН: ПОЛУПЛОСКОСТЬ	0.50	0.035	center	0	small	done	0.32,0.012,0.685,0.058	pbot
fig_equalphi.jpg	equal Φ	равные \(\Phi\)	0.53	0.716	center	0	small	done	0.462,0.698,0.598,0.737	diskgrey
```

(Term choices like «Простое пересечение» are the *project glossary's* call —
fix them there first, the registry only carries them.)

## Build

`labels_to_tikz.py labels.tsv --width 12cm > overlays.tex`, then a minimal
XeLaTeX document (fontspec + Times New Roman + polyglossia russian + tikz +
the four `\definecolor` lines) that `\input`s it. Two xelatex passes are NOT
needed — overlays have no cross-references. Render check via PyMuPDF at 2.2×.

## What the three iterations caught (the actual value of render→look)

1. **Iteration 1, «ГРИНN»**: the RU text «ГРИН» is *narrower* than "GREEN",
   the patch was sized to the new text — the original's trailing "N" peeked
   out. Rule: the patch must cover the **original** label's extent (plus
   2–3 px), not the replacement's.
2. **Iteration 1, half-plane label**: the patch's top edge (y1=0.068) crossed
   the ground line into the white region and greyed out the right-angle
   markers sitting on the line. Rule: keep patches inside the background
   region they were sampled from; ink boundaries are patch boundaries.
   (Bonus find: the "white" lower half-plane is actually grey RGB≈192 — the
   figure *depicts* solid ground — so the assumed-white patch would have been
   wrong twice.)
3. **Iteration 2, «равные Φ» ghost**: the label was placed at y=0.729 from a
   0.02-grid reading; the original sat at ≈0.716, and a faint "equal Φ" ghost
   stayed visible *below* the new text. A whole-page render hides this — it
   surfaced only in a **3.5× zoom crop of the label region**. Rule: verify
   every label at zoom, not at page scale.

After the three fixes: all 10 labels clean — patches invisible on their
backgrounds, marker squares and the dashed ellipse intact, «равные Φ» sits on
the chord line exactly where "equal Φ" was.

## Environment facts (this machine)

- xelatex (MiKTeX) + Times New Roman covers the Cyrillic labels; compile time
  ~8 s for 2 pages of overlays.
- PyMuPDF (`fitz`) renders the check images; Pillow does grids and sampling —
  both present in `py -3` and in the pipeline venv.
