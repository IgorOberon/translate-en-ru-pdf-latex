---
name: latex-running-heads-overfull
description: >-
  Diagnose and fix typography defects in built LaTeX documents: Overfull/Underfull boxes, running heads colliding with page numbers, and loose word spacing. Use logs and rendered pages to verify repairs. Not for designing new page styles, changing margins by preference or normalizing punctuation.
---

# Fixing overfull boxes and over-long running heads

A clean compile (0 errors) does **not** mean the page looks right. Overfull
text past the margin, a header colliding with the page number, and loose gappy
lines are all invisible to a successful build — you find them in the `.log` and
by looking at rendered pages.

## Step 1 — read the log, not just the PDF

```bash
grep -n "Overfull \\hbox"  main.log
grep -c "Underfull \\hbox" main.log
```

Interpreting an Overfull line:
- `Overfull \hbox (NNpt too wide) in paragraph at lines A--B` — body text. `NN`
  is severity; under ~5pt is usually invisible, tens of pt are obvious.
- `Overfull \hbox (NNpt too wide) has occurred while \output is active` — **not
  body text**. This fires during page shipout, so it's a **running head/footer**
  or a float. A constant `NN` repeating on many pages = one running head (e.g. a
  chapter title) overflowing across a whole chapter. The following log line
  shows the slanted header text and the page number jammed against it.

## Step 2 — fix over-long running heads (the common, high-impact bug)

When a chapter/section title (uppercased in the header) is wider than the text
block, the page number collides with it. Fix it with the **optional argument**:

```latex
\chapter[Short head]{Full chapter title that is too long for a header}
\section[Short head]{Full section title that is too long for a header}
```

The optional argument feeds `\chaptermark`/`\sectionmark`, so the header uses
the short form on **every** page of that unit, including the first.

**The firstmark trap — explain it, it wastes hours.** A natural-looking fix is
to wrap the heading in manual marks:

```latex
\markright{SHORT}
\section{LONG}      % <-- still overflows on the section's FIRST page
\markright{SHORT}
```

This does **not** fix the section's first page. `\rightmark` expands from
`\firstmark` (the *first* mark on the page). `\section` internally calls
`\sectionmark{LONG}`, which becomes that first mark; your `\markright{SHORT}`
*before* the heading ends up on the previous page, and the one *after* isn't the
first mark. So the opening page of the section shows the long title and
overflows. The optional argument is robust because the section's *own* mark is
already short. Use manual `\markboth` only for the chapter-level (left) head —
that one reads from `\botmark` and isn't subject to the firstmark issue.

## Step 3 — fix loose lines and small overfulls

- **Add microtype** — this is the single biggest quality win:

  ```latex
  \usepackage[protrusion=true,expansion=true]{microtype}
  ```

  Character protrusion + font expansion let TeX fit lines far better; it
  typically cuts Underfull counts by more than half and clears small overfulls.
  Works with pdfLaTeX and Type1 fonts (including cm-super).

- **`\emergencystretch`** as a last resort for a few stubborn unbreakable tokens
  (a long URL, a long foreign word in a narrow index column): `2em`–`3em`.
  Lower = tighter (may reintroduce a couple of overfulls); higher = absorbs more
  but slightly looser. Tune against the log counts.

- **Foreign words not hyphenating** in an otherwise non-English document cause
  loose lines — wrap them so their language's hyphenation applies:
  `\foreignlanguage{english}{Text and Academic Authors Association}`.

- **Long URLs**: `\usepackage{url}` + `\url{...}` (breaks at `/` and `.`).
  Note `\verb` **fails inside `\footnote`** ("Missing } inserted") — use
  `\texttt{...}` there.

## Step 4 — verify by looking

The compiler can't see a collision. Rasterize the affected pages and inspect:

```bash
pdftoppm -png -r 110 -f PAGE -l PAGE main.pdf check    # then open check-*.png
```

Confirm the header no longer touches the page number and lines aren't gappy.

## Workflow summary

build → `grep` log for `Overfull \hbox` (flag the "output is active" ones) →
shorten over-long heads via `\section[short]{full}` / `\chapter[short]{full}` →
add `microtype` → tune `\emergencystretch` → rebuild → re-grep (counts should
drop, 0 visible overfull) → render a couple of pages to confirm.
