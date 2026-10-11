# Pitfalls and verification techniques (Pandoc + XeLaTeX, multi-script)

Each item below cost real debugging time on actual builds. Read the relevant one
when a build fails or renders wrong.

## Build-breaking / rendering pitfalls

1. **`---` parsed as YAML.** When several `.md` files are concatenated (or a file
   uses `---` as a thematic break), Pandoc may read it as a YAML metadata block →
   `Error parsing YAML … while scanning an alias`. **Fix:** pass
   `-f markdown-yaml_metadata_block` and supply title/author via `-M`/`-V`, never
   in-file. The bundled `build_pdf.sh` already does this.

2. **Lua `Code → Emph` must not split words.** A filter that splits the code text
   on whitespace (`for w in el.text:gmatch("%S+")`) and re-inserts `pandoc.Space()`
   corrupted the **first Cyrillic letter** of multi-word terms into `U+FFFD` (e.g.
   "Расшифровка" → "<FFFD>асшифровка"). The byte-split interacts badly with
   `pandoc.Inlines`/`:insert`. **Fix:** keep the filter as a single
   `pandoc.Emph({pandoc.Str(el.text)})`. (No-filter = 0 FFFD; word-split = 1 FFFD;
   single-Str = 0 FFFD — confirmed by generating `-t latex` and `grep -c $'�'`.)

3. **Missing glyphs in the chosen font.** Times New Roman lacks some arrows
   (`⇄` U+21C4, `⇒` U+21D2, `⟶` U+27F6) — they appear as blank and the log shows
   `Missing character: There is no … in font Times New Roman`. **Fix:** in the
   preamble, `\usepackage{amssymb}\usepackage{newunicodechar}` then map each:
   `\newunicodechar{⇄}{\ensuremath{\rightleftarrows}}`,
   `\newunicodechar{⇒}{\ensuremath{\Rightarrow}}`,
   `\newunicodechar{⟶}{\ensuremath{\longrightarrow}}`. Times *does* have
   `→ ↔ ≈ ≠ ×`, so map only what the log flags.

4. **Double chapter numbering.** With `documentclass=book/report`, `\chapter`
   prints "Chapter N" / "Глава N" — doubling titles that already carry "I.", "A.".
   **Fix:** `\setcounter{secnumdepth}{-1}` (suppresses the auto number entirely;
   non-starred `\chapter` still adds a ToC entry, so the ToC is unaffected).

## Bookmarks / navigation

5. **Outline depth vs printed ToC.** Keep the printed ToC shallow (`--toc-depth=2`
   → chapters + sections) but make the PDF sidebar deep:
   `\AtBeginDocument{\hypersetup{bookmarksdepth=4,bookmarksopenlevel=1}}`. Use
   `\AtBeginDocument` so it runs *after* hyperref loads regardless of preamble
   order.

6. **Verifying bookmark depth is hard.** The XeTeX backend (xdvipdfmx) writes the
   outline **compressed inside object streams** and produces **no `.out` file**, so
   `grep`/`pdfinfo` see nothing and there may be no qpdf/mutool installed. **Fix:**
   do a one-off uncompressed build and count titles —
   `xelatex --output-driver="xdvipdfmx -z0" file.tex` then
   `grep -aoc '/Title' file.pdf` (should equal the number of headings) and
   `grep -aoc '/Outlines' file.pdf` (= 1).

## Paths / encoding

7. **Manual `xelatex` breaks on awkward paths.** A path containing `~` (a Windows
   8.3 short name like `USERNA~1`), Cyrillic, or spaces makes `xelatex` fail
   (`~` is special; the path gets mangled). **Therefore build through Pandoc** — it
   runs XeLaTeX in its own temp dir and sidesteps this. If you must run `xelatex`
   by hand, copy the `.tex` to a clean ASCII path first (e.g. `D:\work\`).

8. **Locating an invalid UTF-8 byte.** If Pandoc emitted `U+FFFD` from a bad source
   byte (so a literal byte-grep for `EF BF BD` finds nothing), find the offending
   line with a strict decode:
   `perl -ne 'use Encode; eval{Encode::decode("UTF-8",$_,Encode::FB_CROAK)}; print "$ARGV:$.\n" if $@' file.md`.

9. **MiKTeX update nag.** Lines like `major issue: … not checked for updates` are
   harmless. Filter them: `... 2>&1 | grep -viE "checked for updates|major issue"`.

## Style notes

- `parskip` (vertical space between paragraphs, no indent) suits transcript/dialogue
  layouts like `**[hh:mm:ss] Speaker.** …`.
- Mark foreign/technical terms with inline `` `backticks` `` in the source; the
  `code-to-emph.lua` filter turns them into clean italic.
- `geometry: a4paper, margin=2.5cm`, `fontsize: 11pt`, `classoption: oneside` are
  sensible defaults for a readable reference document.

## Fragment mode (pandoc emits body only; you own the preamble)

Use this when pandoc's standalone template itself is the problem (lean TeX
installs without `lmodern.sty`), or when a pipeline needs full preamble control.
Build: `pandoc doc.md --to=latex --no-highlight --top-level-division=section
--wrap=preserve -o body.tex`, then compile your own `main.tex` that `\input`s it.

10. **The fragment contract.** pandoc output assumes template-provided macros —
    provide them yourself or the build explodes:
    `\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}`;
    `\providecommand{\pandocbounded}[1]{#1}` (pandoc ≥3.1.13 wraps every image);
    and for pipe tables `\usepackage{longtable,booktabs,array,calc}` — **calc**
    is the one everyone forgets: without it the emitted column widths
    `p{(\columnwidth - N\tabcolsep) * \real{r}}` and minipage cells produce
    hundreds of "Missing number / Illegal unit" errors (`\real` is calc's own).

11. **Syntax-highlighting macros live in the template.** Fenced code WITH a
    language tag emits `\begin{Shaded}`/`\KeywordTok…` — undefined in fragment
    mode. Pass `--no-highlight` (plain verbatim) or stay standalone.

12. **YAML front matter in fragment mode** is consumed as metadata and silently
    dropped — strip it (`awk 'NR==1&&/^---/{f=1;next} f&&/^---$/{f=0;next} !f'`)
    and hand-build the title page in main.tex.

13. **Long command lines overflow verbatim.** Shrink:
    `\makeatletter\def\verbatim@font{\ttfamily\small}\makeatother` plus
    `\setmonofont[Scale=0.86]{…}`; keep source lines ≲ 100 chars.

14. **Glyph probe before shipping.** Compile a one-liner with the target font
    and grep the log for `Missing character`; if a glyph is absent (e.g. ⟦ ⟧
    U+27E6/7 in DejaVu Sans Mono), substitute in the PDF-source copy only,
    keep the canonical md intact.

15. **Passes and corpses.** THREE xelatex passes right after adding a
    `\tableofcontents` (TOC pagination shifts) and on 100+ page docs; a
    10–15 KB PDF is an aborted corpse — delete `main.pdf/aux/toc` before
    judging a rebuild; fatal audit = `grep -E "^!" main.log`
    (Overfull/Underfull are cosmetics, not fatals). Machine-verify: page count
    + text probes + `len(page.get_links())>3` on the TOC page via PyMuPDF.
