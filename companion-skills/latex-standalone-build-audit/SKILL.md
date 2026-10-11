---
name: latex-standalone-build-audit
description: >-
  Check standalone and master build paths in multi-document LaTeX projects. Use when chapters compile in the book but not independently, or when auditing handouts, solutions and other separately buildable files for package clashes, preamble errors and stale auxiliary files.
---

# Standalone build audit for multi-document LaTeX projects

## Why this exists

Course/book repos commonly have two build modes for the same `.tex` file:

- **Standalone**: the file has its own `\documentclass … \begin{document} … \end{document}`, usually guarded by a flag like `\ifnum\incourse=0 … \fi`.
- **Aggregated**: a master document sets `\def\incourse{1}` and `\input`s the file, so the guarded preamble is skipped and only the body is included.

A green master build only exercises the aggregated path. **Per-file preamble bugs
(double-loaded packages, wrong bibliography commands, missing guards) are invisible
to it** and only surface when a user — or a teacher printing one handout — compiles
that file by itself. This skill finds those by compiling every standalone file, and
applies the fixes for the recurring causes.

## Procedure

### 1. Enumerate and batch-compile every standalone document

Compile each candidate `.tex` from **its own directory** (so its relative
`\input{../preamble}` resolves), capturing logs, and report only the failures.

```bash
# Adjust dirs/engine to the project. TEXINPUTS lets the preamble's own \input
# (e.g. \input{theorem_styles}) resolve from the parent when compiling in a subdir.
export TEXINPUTS="..;.;"          # Windows uses ';'  | POSIX: "..:.:"
ENGINE="xelatex"                  # or pdflatex / lualatex — match the project
for d in solutions problems cheatsheets handouts faq prelecture postlecture lecture_plans; do
  for f in "$d"/*.tex; do
    base=$(basename "$f" .tex)
    ( cd "$d" && "$ENGINE" -interaction=nonstopmode -halt-on-error=1 "$base.tex" \
        > "../build/sa_$base.log" 2>&1 )
    err=$(grep -ac '^! ' "build/sa_$base.log")
    [ "$err" != "0" ] && echo "ERR $d/$base: $(grep -aE '^! ' build/sa_$base.log | head -1)"
  done
done
# Root-level index docs compile in place (no TEXINPUTS needed):
for f in GLOSSARY NOTATION_GUIDE THEOREM_INDEX *_INDEX STUDENT_PACK TEACHER_GUIDE COURSE_MAP; do
  [ -f "$f.tex" ] && "$ENGINE" -interaction=nonstopmode "$f.tex" > "build/sa_$f.log" 2>&1 \
    && echo "$f: $(grep -ac '^! ' build/sa_$f.log) err"
done
```

`-halt-on-error=1` stops at the first error so the log ends at the culprit. Big
aggregator docs (a "student pack" that `\input`s everything) may need **two passes**
and may trip `-halt-on-error` on a transient first-pass label issue — re-run without
it and count `^! ` in the final pass to judge truthfully.

### 2. Diagnose and fix

Match each failing log to a bug class in `references/common-bugs.md` and apply the
fix there. The five recurring classes (with one-line tells):

| Error message | Cause | Fix |
|---|---|---|
| `Option clash for package geometry` | file re-`\usepackage[..]{geometry}` after the preamble already loaded it | `\geometry{..}` instead (and place it *after* the preamble) |
| `\bibliographystyle invalid for 'biblatex'` | old BibTeX commands under biblatex | `\printbibliography` |
| `Can be used only in preamble` | an `\input`-ed file's `\documentclass`/`\usepackage` runs inside the master body | add an `\incourse`-style guard to that file |
| `Not in outer par mode` | a `\marginpar`/float/`\section` invoked inside a `tabular`/box/math | show a static representation instead of invoking it |
| `File ended while scanning use of \@newl@bel` | truncated/stale `.aux` from an interrupted run | delete the `.aux` and recompile |

### 3. Re-verify

Recompile each fixed file standalone (0 errors) **and** the master/aggregator
(confirm the fix didn't regress the aggregated build, and that an aggregator error
like "Can be used only in preamble" is gone). For files that are both standalone
and `\input`-able, confirm **both** modes.

## Report

List every file audited, each error found with its bug class, the fix applied, and
the re-verification result (standalone 0 errors; aggregator clean). Note any
non-fatal warnings you deliberately left (e.g. an invalid `\documentclass[9pt]`
that silently falls back to 10pt — cosmetic, risky to "fix" by changing the class).

## Notes on the build engine

- Match the project's engine; fontspec/Unicode ⇒ `xelatex`/`lualatex`.
- `biber` can be flaky in scripts (sometimes no `.bbl` ⇒ spurious "undefined
  citation/reference"); if a master report shows undefined refs/cites but
  `errors=0`, re-run biber + one pass before believing it.
- Full-course master builds can hang environmentally; if a build log stops growing
  for minutes, kill the engine processes and rely on per-file/per-chapter compiles,
  which are fast and reliable.
