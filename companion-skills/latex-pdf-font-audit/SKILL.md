---
name: latex-pdf-font-audit
description: >-
  Check embedded fonts and diagnose bitmap or missing-glyph problems in LaTeX-built PDFs, including Cyrillic and Greek text mixed with mathematics. Use for fuzzy fonts, Type3 warnings and non-Latin font setup. Not for ordinary font preferences, figure extraction or margin overflow.
---

# LaTeX PDF font audit & non-Latin setup

Type3 fonts are **bitmaps**: they look fuzzy on screen and in print and some
publishers reject them outright. The target is simple — `pdffonts` reports every
font as `Type 1` (or `TrueType`/`CID`), and **zero** `Type 3`.

## Always run the check after building

```bash
pdffonts main.pdf                       # inspect the "type" column
pdffonts main.pdf | grep -c "Type 3"    # must print 0
```

If any font is Type3, the rest of this skill explains why and how to fix it.

## Non-Latin setup that works with pdfLaTeX and keeps math rendering

Use this preamble core (example: Russian; swap the babel language for others):

```latex
\usepackage[T1,T2A]{fontenc}      % T2A = Cyrillic; keep T1 for Latin
\usepackage[utf8]{inputenc}       % modern LaTeX defaults to utf8 anyway
\usepackage[english,russian]{babel}   % last language listed = main
\usepackage{amsmath,amssymb}      % math
```

**The critical font choice:** use **cm-super** (Type1 Computer Modern with full
T2A coverage). Do **not** rely on `lmodern` for Cyrillic — `lmodern` lacks T2A
*italic* and silently falls back to **Type3 bitmaps** for Cyrillic italics, so
your `pdffonts` count won't be zero and italic Cyrillic looks fuzzy. cm-super
keeps the familiar Computer Modern look and is fully vector. (For a different
look you can instead use a complete OpenType family via lualatex/xelatex +
fontspec + Polyglossia, but if you're on pdfLaTeX, cm-super is the reliable
path.)

If you still get PK/Type3 bitmaps after choosing cm-super, regenerate the font
maps once, then rebuild:

```bash
initexmf --mkmaps        # MiKTeX
# updmap-sys  (or updmap-user)   # TeX Live
```

## Traps specific to non-Latin documents

- **Non-Latin letters inside math mode are dropped or mangled.** Keep
  translated words in *text* mode; only symbols belong in `$…$`. If a label or
  operator name needs words, use `\text{…}` (amsmath) or `\mbox{…}`.

- **`\TeX` / `\LaTeX` eat the following space**: `\LaTeX слово` →
  "LaTeXслово". Fix globally with xspace and write normally afterwards:

  ```latex
  \usepackage{xspace}
  \let\TeXlogo\TeX   \renewcommand{\TeX}{\TeXlogo\xspace}
  \let\LaTeXlogo\LaTeX \renewcommand{\LaTeX}{\LaTeXlogo\xspace}
  ```

- **Stray combining accents are fatal.** A U+0301 combining acute (easy to
  introduce when typing Cyrillic stress marks like «бо́льшую») crashes the build
  under T2A+inputenc. Strip them after editing:

  ```bash
  perl -CSD -i -pe 's/\x{0301}//g' file.tex
  ```

  (That regex is safe through the Bash tool — it has no literal backslash-pairs
  to mangle.)

## Optional but recommended: print-quality justification

```latex
\usepackage[protrusion=true,expansion=true]{microtype}
```

Works with pdfLaTeX + cm-super (Type1). It does not change font *type* but is
part of "print quality": character protrusion + font expansion markedly reduce
over/underfull lines. (For deeper overfull/running-head fixes, see the
`latex-running-heads-overfull` skill.)

## Verify

Build → `pdffonts` shows 0 Type3 → rasterize a representative page and confirm
crisp glyphs:

```bash
pdftoppm -png -r 200 -f 1 -l 1 main.pdf check
```

## Tooling note (Windows / PowerShell)
The Bash tool mangles backslashes and `$` even inside single quotes, so
backslash-heavy `perl`/`grep` one-liners are unreliable — make LaTeX-source
edits with the Edit tool or PowerShell. The accent-strip command above is the
safe exception.
