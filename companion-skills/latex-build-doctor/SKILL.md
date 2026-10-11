---
name: latex-build-doctor
description: Diagnose and fix LaTeX/XeLaTeX/MiKTeX compilation failures fast. Use this skill whenever a LaTeX build fails, produces a tiny/corrupt PDF, dies silently, spams "Undefined control sequence", cannot find fonts or .sty packages, when latexmk errors about perl, when pandoc-generated .tex does not compile, or when the user mentions main.log, Overfull hbox, MiKTeX, XeLaTeX, or "PDF не собирается". Also use it proactively before assembling any pandoc to LaTeX to PDF pipeline to apply the known-good preamble fixes.
---

# LaTeX Build Doctor

Battle-tested triage for XeLaTeX/MiKTeX builds (Windows-first, applies to TeX Live too).

## Triage workflow (always start here)

1. Get the REAL error, not the symptom:
   ```powershell
   Select-String -Path .\main.log -Pattern "^!" | Select-Object -First 8
   ```
   Lines starting with `!` are fatal. The FIRST one is the killer; the rest are often cascade.
   With `-file-line-error` flag, errors read `file.tex:LINE: message` — use it:
   ```
   xelatex -interaction=nonstopmode -file-line-error main.tex
   ```
2. If main.log has no `!` lines but the run died before typesetting: the ENGINE failed,
   not TeX. Look at the MiKTeX engine log instead:
   `%LOCALAPPDATA%\MiKTeX\miktex\log\xelatex.log` (tail 25). Beware: this log is SHARED
   by all projects on the machine — check the working directory in its lines matches
   your project before trusting it.
3. A "successful" PDF of 10–15 KB is a corpse from an aborted run. Never trust
   file-exists as success. Delete stale artifacts before rebuilding:
   ```powershell
   del main.pdf, main.aux, main.toc -ErrorAction SilentlyContinue
   ```
4. TeX gives up after 100 errors ("That makes 100 errors; please try again").
   One systematic per-instance error (e.g., an undefined macro wrapping every image)
   kills the whole build early. Fix the class of error, not instances.

## Failure catalog (symptom -> cause -> fix)

| Symptom | Cause | Fix |
|---|---|---|
| `latexmk ... could not find the script engine 'perl'` | MiKTeX ships latexmk wrapper without Perl | run `xelatex` directly, twice (or thrice with TOC); Strawberry Perl optional |
| Silent death, tiny PDF, `File 'X.sty' not found` + `Emergency stop` | MiKTeX cannot auto-install packages in nonstopmode | MiKTeX Console **as normal user, NOT admin** (two separate modes!) -> Settings -> install missing packages on-the-fly: **Always**; then one interactive `xelatex main.tex` to let it download |
| `Undefined control sequence \pandocbounded` (x hundreds) | pandoc 3.x wraps every image in its template macro; you compiled a fragment without the template | add `\providecommand{\pandocbounded}[1]{#1}` |
| `Missing number, treated as zero` + `Illegal unit` at table cells `\begin{minipage}[b]{\linewidth}` or `p{(\columnwidth - N\tabcolsep) * \real{r}}` | pandoc table column arithmetic needs the **calc** package | `\usepackage{calc}` (then `\real` is calc's own; a `\providecommand{\real}[1]{#1}` fallback is harmless AFTER calc) |
| `Environment Shaded undefined` / `Highlighting` / `\KeywordTok` | pandoc syntax-highlighting macros live in its standalone template | pandoc `--no-highlight` for fragments, or emit with `-s` |
| `Undefined control sequence \mathscr` | script math alphabet not loaded | `\usepackage{mathrsfs}` |
| `fontspec Error: The font "CMU Serif" cannot be found` | font not installed (Windows has no Computer Modern Unicode) | swap to installed fonts: `\setmainfont{Times New Roman}` `\setsansfont{Arial}` `\setmonofont{Consolas}` |
| `Missing $ inserted` inside a filename/path being typeset | `_` `%` `&` in text mode | wrap with `\detokenize{...}` (prints verbatim, catcode-safe) |
| `Extra alignment tab has been changed to \cr` | a row has more `&` than the array/table colspec | fix that row (often OCR noise in a formula: replace stray `&` with `\;`) |
| `Unable to load picture or PDF file` on an EXISTING .jpg; log says "type bmp" / "not recognized" | exotic JPEG (CMYK or progressive) — viewers open it, xdvipdfmx refuses | re-encode to baseline RGB (Pillow: `Image.open(p).convert("RGB").save(p,"JPEG",progressive=False)`) |
| Figures overflow page (`Overfull \hbox (500+pt)` at image lines) | images inserted at natural size | fit-to-page wrapper, see snippet below |
| Missing figure kills the build | `\includegraphics` on absent file is fatal | safe wrapper below turns it into a framed note instead |
| Overfull/Underfull hbox, a few pt | cosmetic line-breaking complaints | ignore; not errors |
| `! LaTeX Error: File 'lmodern.sty' not found` from pandoc `-s` | pandoc default template wants lmodern | install it, or bypass template: compile fragment with your own preamble |
| engine dies pre-typesetting on a machine where it USED to work | corrupted MiKTeX format/filename database | `initexmf --update-fndb` then `initexmf --dump=xelatex` |

## Known-good preamble block (Russian docs with math, XeLaTeX)

Paste-ready fixes distilled from real builds; safe to include always. The full
block lives in **`assets/preamble-ru-fixes.tex`** — copy it into the preamble or
`\input` it. It bundles: system fonts (Times New Roman / Arial / Consolas),
polyglossia russian+english, `amsmath`+`mathrsfs`, the pandoc-fragment
provisions (`\tightlist`, `\pandocbounded`, **calc** + `\real`), and an
`\includegraphics` wrapper that shrinks oversized figures to the page and turns
MISSING figures into a framed searchable note instead of a fatal error.

## Compile protocol

- Two passes minimum (cross-refs); **three** passes when a `\tableofcontents` was just
  added or the document is 100+ pages (TOC shifts page numbers).
- Success criteria: `Output written on main.pdf (N pages)` with plausible N, and file
  size plausible for the content (images => megabytes). Verify page count, not existence.
- Post-build image audit when figures matter: extract `\includegraphics{...}` refs from
  the .tex, diff against the images folder; missing files under the safe wrapper appear
  as framed notes in the PDF (searchable), not as build failures.

## Companion skills (route non-fatal problems there)

This skill is for FATAL build failures. Route by symptom:
- Overfull/Underfull boxes, margin spills, long running heads, rivers ->
  **latex-running-heads-overfull** (typography polish, not errors).
- Blurry/bitmap text, Type3 fonts, print-quality embedding, pdfLaTeX+T2A route ->
  **latex-pdf-font-audit**.
- LuaLaTeX transient `memory exhausted`, mismatched `\begin/\end` pairing,
  non-Latin text inside math mode -> **translate-book-to-latex**
  `references/pitfalls.md` (+ `scripts/compile_retry.py`, `fix_env_pairing.py`).
- Back-of-book index build (upmendex, Cyrillic collation) -> **latex-book-index**.
- pandoc-driven multiscript builds and their gotchas -> **markdown-to-pdf-multiscript**.
