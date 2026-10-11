# Reconciling a fanned-out book at the join

When chapters/sections are produced by independent agents and then concatenated,
a class of bugs appears that a single-agent run never hits: the same label
defined twice, an object lost on a boundary two agents shared, and numbering that
only collides once everything is in one document. These are the real cases from
the Complex-Analysis translation and how each was found and fixed.

## 1. Duplicate inclusion → "multiply defined"

**Symptom.** `LaTeX Warning: Label `fig:11.3' multiply defined.`

**Cause.** A figure file got `\input` from two places — e.g. once where the text
references it and once in a leftover block from an earlier draft — so its
`\label` runs twice.

**Find it.** `scripts/input_inventory.py main.tex` walks the include tree and
prints any file pulled in more than once, plus any `\label{...}` string that
appears in two different files. Fix by deleting the duplicate `\input`, not the
label.

## 2. Boundary figures and examples

**Symptom.** A figure (10.3) or a worked Example (10.3) is missing entirely, or
appears twice; or figures 10.84–10.86 vanish at the end of a section.

**Cause.** The object sits exactly on the line between two agents' units. Each
agent assumes the other took it → both drop it (gap) or both include it
(duplicate).

**Find it.** Enumerate every split boundary you created (which section/page each
worker started and ended on). For each boundary, confirm the straddling figure /
example / equation landed in **exactly one** unit. A quick count of "Рис. N.M" /
"Пример N.M" against the source's figure/example list per chapter surfaces both
gaps and duplicates. Add the missing object to the correct unit; remove the extra
copy from the other.

## 3. Per-type, per-chapter numbering set once

The source numbers each theorem-like *type* independently and within the chapter:
"Теорема 2.1", "Определение 2.3", "Пример 2.14" coexist. Reproduce with one
counter per type, scoped to chapter, in the **shared preamble** (never per
chapter, or the counters diverge between agents):

```latex
\newtheorem{theorem}{Теорема}[chapter]
\newtheorem{definition}{Определение}[chapter]
\newtheorem{example}{Пример}[chapter]
...
\numberwithin{equation}{chapter}     % equations as (chapter.n)
```

Because every worker `\usepackage{preamble}`, they all share these counters and
the numbers line up automatically once concatenated.

## 4. Cross-section number clashes

**Symptom.** Equation (10.1) is `\label`-ed in **both** §10.1 and §10.2; Table
10.1 defined in both §10.4 and §10.5.

**Cause.** Two adjacent sections each numbered an equation/table set the same way.
Often the source actually left one set **unnumbered** and an agent numbered it.

**Find it / fix it.** Check the *source page* for whether those equations carry
printed numbers. Where the source shows them unnumbered, convert that section's
`\begin{equation}...\end{equation}` to display math `\[ ... \]` (no number, no
label). Where a table/figure number is genuinely duplicated, keep one and delete
the other. Then re-run `build_audit.py` until `multiply == 0`.

## 5. Dangling cross-references

**Symptom.** `LaTeX Warning: Reference `sec:10.1' on page ... undefined.`

**Cause.** A `\ref{sec:10.N}` written by one agent points at a `\label` another
agent was supposed to place after `\section{...}` but didn't.

**Fix.** Add the missing `\label{sec:10.N}` immediately after each `\section`
(a regex pass over the chapter files is safe here because the target is a single
well-defined line, unlike the equation-spanning regexes that corrupt files — see
translate-book-to-latex pitfalls). Re-audit.

## The gate

After every reconciliation edit, the join is clean only when
`build_audit.py book.log` reports:

```
errors: 0  undefined: 0  multiply: 0  missing: 0
Pages: <N>
```

and `latex-pdf-font-audit` confirms zero Type-3 (bitmap) fonts. Anything nonzero
names the remaining defect; fix and re-run.
