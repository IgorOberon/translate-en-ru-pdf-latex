---
name: translate-book-to-latex
description: >-
  Translate and re-typeset a user-provided technical book into LaTeX/PDF chapter by chapter, carrying figures, numbering and references across. Use for the agent-authored translation workflow, engine/font setup and resumable per-chapter builds. For a cheap local-model run, use the separate translate-pdf-latex dispatcher.
---

# Translating a book into a LaTeX/PDF, chapter by chapter

You write the translation yourself (your own prose in the target language); this
skill is the surrounding machinery so the result compiles cleanly, the figures
come across, and you don't re-learn the same five lessons mid-project.

> Scope note: this is for material the user is entitled to translate (e.g. their
> own licensed copy, for personal study). Keep the deliverable in the user's own
> files; the user owns decisions about distribution.

## 0. Assess the source (do this first)

1. **Scanned vs born-digital.** `len(doc[p].get_text().strip())` on a content
   page: `0` ⇒ scanned (no text layer) ⇒ you must **read each page by vision**.
   Non-zero ⇒ a real text layer you can extract and translate from directly.
2. **Page offset.** Printed book page ≠ PDF page index (front matter). Read one
   known page's printed number once and record `pdf_index = book_page - offset - 1`.
3. **Figures.** Photos/3D-renders/scans → keep as extracted images. Pure line art
   → image now, optional TikZ redraw later. Use the **extract-pdf-figures** skill.
4. **Figure numbering style.** Per-chapter `[1],[2]…` (restarts each chapter) or
   global `[3.5]`? Match the source — it drives `\thefigure` (see §2).

## 1. Engine and fonts (the make-or-break choice)

Use **LuaLaTeX** + `fontspec` + `unicode-math`. The trap: many classic TeX fonts
**do not cover non-Latin scripts and maths together**.

- For a **Cyrillic** target, a reliable pairing is **`STIX Two Text`** (main) +
  **`STIX Two Math`** (math): full Cyrillic, a matched math font, and it even has
  **bold math** (so `\boldsymbol`/`\symbf` works without warnings). `CMU Serif`
  has Cyrillic but can silently disappear from a system; `Latin Modern Math`
  lacks bold and Cyrillic.
- **Verify the font exists before committing:**
  `luaotfload-tool --find="STIX Two Text"`. If a font "cannot be found" mid-build,
  run `luaotfload-tool --update --force` first. Swapping the whole book's look is
  then a two-line change to the preamble.

`assets/preamble-template.tex` is a working shared preamble (LuaLaTeX, STIX Two,
babel, a robust `\figincl`, a `axiombox` for boxed results). Adapt the babel
languages and fonts to the target.

## 2. Project layout (resumable, incremental)

```
book/
  preamble.tex            shared preamble (assets/preamble-template.tex)
  book.tex                master: \input{preamble}, then \input each chapter
  chapters/chNN.tex       one file per chapter
figures/<book>/           extracted figure PNGs
transcripts/<book>/       (scans) per-chapter OCR'd source text you transcribe
PROGRESS.md               resumable ledger: per-chapter status + lessons learned
```

`\thefigure`: for per-chapter `[N]` numbering use
`\renewcommand{\thefigure}{\arabic{figure}}` (book class still resets the counter
each `\chapter`); for `[C.N]` keep `\thechapter.\arabic{figure}`. Make the
caption label format and your `\figref` **agree** with this, or captions and
references will disagree (`[1.5]` vs `[5]`).

## 3. The per-chapter loop

For each chapter, in order, smallest-resumable-unit at a time (a section):

1. **Read the source.** Scanned: render the page **in halves at ~235 DPI** (small
   book pages are illegible whole) and read by vision; zoom the right margin to
   read **equation numbers** exactly. Digital: read the extracted text layer.
2. **Translate** into your own target-language prose — faithful, fluent, your
   wording. Preserve every numbered equation and its number.
3. **Figures.** Extract with the extract-pdf-figures skill; reference via the
   robust `\figincl{file.png}` (degrades to a labelled placeholder if the file
   isn't there yet, so text compiles before figures exist).
4. **Standalone-compile** the chapter (a tiny wrapper that `\input`s preamble +
   the one chapter) to catch errors locally.
5. **Add to master**, rebuild with the retry wrapper, confirm `Output written`,
   `0` errors, `0` "Missing character", `0` placeholders.
6. **Verify visually**: render the new pages, montage, **look** (the compiler
   can't see overlaps, header-bleed in figures, or a wrong crop).
7. **Update PROGRESS.md**: mark the chapter done, record page count + any lesson.

`scripts/compile_retry.py` builds the master, retrying transient
`memory exhausted` failures (LuaTeX can hit them under system RAM pressure).

## 4. The five lessons that cost hours (read references/pitfalls.md)

1. **NEVER put non-Latin text inside math mode** (`\begin{equation}`, `$…$`). The
   math font has no Cyrillic glyphs → a flood of `Missing character`. A numbered
   *textual* result goes in a **text box**, e.g.
   `\begin{axiombox}…\hfill(N)\end{axiombox}`, not an `equation`.
2. **Never "fix" LaTeX structure with a greedy/lazy regex over the whole file.**
   A `re.DOTALL` `.*?` from one `\begin{equation}` to a far-away `\tag{}` spans
   *everything in between* and corrupts every equation. To repair mismatched
   `\begin/\end{equation|axiombox}`, use **stack-based pairing**
   (`scripts/fix_env_pairing.py`): pair each `\end` with the nearest open
   `\begin`, then set the begin's environment to match its end.
3. **Compile with a retry loop** for transient out-of-memory builds.
4. **`\figincl` degrades to a placeholder** so a chapter compiles before its
   figures are extracted — write text first, drop figures in after.
5. **Figure numbering must match the source** and be consistent between captions
   and `\figref` (see §2).

## Companion skills
- **extract-pdf-figures** — pull the figures out precisely.
- **latex-figure-review** — render-and-look QA on figures.
- **latex-standalone-build-audit** — confirm every chapter builds on its own.
- **latex-typography-normalizer** — final dash/quote/notation pass.
