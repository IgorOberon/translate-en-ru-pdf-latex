---
name: markdown-to-pdf-multiscript
description: >-
  Build PDFs from Markdown through Pandoc and XeLaTeX for Cyrillic, Greek and other mixed-script text. Use for missing glyphs, damaged bookmarks, duplicate heading numbers or YAML-block parsing failures in this workflow. Includes templates and a build helper; verify fonts and rendered output.
---

# Markdown → print-quality PDF for multi-script text (Pandoc + XeLaTeX)

The default `pandoc file.md -o out.pdf` quietly mishandles mixed Cyrillic / Greek /
German text: it picks a Latin-only font (missing glyphs → blank boxes), renders
inline `` `code` `` as typewriter (ugly in prose and gappy for Greek/Cyrillic),
gives a shallow navigation tree, and chokes when several files are concatenated.
This skill encodes a recipe that has been debugged on real 300-page Russian books
and shorter mixed-script documents.

## When to use

- Turning Markdown (one file, or many that become chapters) into a **printable**
  PDF, when the text is Russian/Cyrillic, Greek, or otherwise non-Latin.
- Fixing a failed/ugly Pandoc→XeLaTeX build of such text (see the symptoms in the
  description and the catalog in `references/gotchas.md`).

## Quick start

Use the bundled script — it wires every flag and points XeLaTeX at the bundled
preamble and filter:

```bash
scripts/build_pdf.sh -o "OUT.pdf" -t "Title" [-s "Subtitle"] [-a "Author"] file1.md [file2.md ...]
```

Each input `.md` whose first heading is `# Heading` becomes a **chapter**; `## `
becomes a section. The printed table of contents stops at sections
(`--toc-depth=2`), while the PDF outline (sidebar bookmarks) goes deep to every
sub-heading — so a long reference document stays navigable without a bloated ToC.

If you prefer to call Pandoc directly (e.g. to tweak options), the script body is
the canonical command to copy from. Always keep `-f markdown-yaml_metadata_block`.

## What the pieces do (and why)

- **`scripts/build_pdf.sh`** — the generalized entry point (`-o/-t/-s/-a` + a list
  of `.md`). Copy it next to a project, or run from the skill.
- **`assets/header.tex`** — LaTeX preamble passed via `-H`. It: picks
  `newunicodechar` math-arrow fallbacks for glyphs Times lacks (`⇄ ⇒ ⟶`); uses
  `parskip` (vertical gaps instead of indents — reads well for dialogue/transcripts);
  sets `\setcounter{secnumdepth}{-1}` so LaTeX does not print "Chapter N" on top of
  titles that already carry their own numbering ("I.", "A."); and decouples the
  deep PDF bookmarks from the shallow printed ToC via
  `\AtBeginDocument{\hypersetup{bookmarksdepth=4,bookmarksopenlevel=1}}`.
- **`assets/code-to-emph.lua`** — a Pandoc Lua filter that renders inline
  `` `code` `` as *italic* instead of monospace. This suits prose (foreign terms
  read better in italic) and, crucially, avoids monospace fonts that lack
  Greek/Cyrillic. **Keep it as a single `pandoc.Str(el.text)`** — an earlier
  word-splitting version corrupted the first Cyrillic letter of multi-word terms
  into U+FFFD.

## Fonts

XeLaTeX uses system fonts by name. The defaults in the script give full coverage
on a typical Windows/Office install:

- **main: Times New Roman** — covers Cyrillic + polytonic Greek + Latin + umlauts;
  compact and conventional for Russian academic text.
- **mono: DejaVu Sans Mono** — broad coverage if any `\texttt` survives.

To check what's installed: `fc-list : family | sort -u`. Other full-coverage serif
options if Times is unavailable: DejaVu Serif, or (with care for Greek) Cambria.
If you only need pdfLaTeX with T2A/cm-super instead of XeLaTeX, that is a different
recipe — see the separate `latex-pdf-font-audit` skill.

## Verify the result

PDFs from mixed-script builds fail silently, so always confirm:

1. **Read the PDF pages** (the Read tool renders them as images) — check the title
   page, the ToC, and a page that actually contains Greek/umlauts/italic terms. No
   empty boxes.
2. **Scan the XeLaTeX run** for `Missing character` warnings (filter MiKTeX's
   harmless "checked for updates / major issue" nag: `grep -viE "checked for updates|major issue"`).
3. If a glyph is missing, add a `\newunicodechar{X}{…}` mapping in `header.tex`
   (math arrows → `\rightleftarrows`, `\Rightarrow`, `\longrightarrow`; etc.).

## Pitfalls

The full catalog — the YAML/`---` trap, the Lua FFFD bug, missing-glyph mapping,
how to verify bookmark depth on a compressed XeTeX PDF, the manual-`xelatex`
path traps (`~`/Cyrillic/spaces), and how to locate an invalid UTF-8 byte — lives
in **`references/gotchas.md`**. Read it whenever a build misbehaves; each item is a
lesson that otherwise costs real debugging time.

## Fragment mode (advanced)

When the pandoc standalone template itself fails (lean TeX without `lmodern.sty`)
or a pipeline needs full preamble control, switch to fragment mode: pandoc emits
the body only, you own `main.tex`. The contract (tightlist/pandocbounded/**calc**
provisions, `--no-highlight`, YAML stripping, glyph probing, the three-pass TOC
rule, machine verification) is items 10–15 of `references/gotchas.md`.
