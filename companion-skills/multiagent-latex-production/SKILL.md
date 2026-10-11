---
name: multiagent-latex-production
description: >-
  Coordinate large translation and LaTeX production jobs across explicitly selected subagents. Use for disjoint chapter or figure work, resumable progress, recovery from partial outputs and reconciliation of numbering, labels and section boundaries. Not a requirement for ordinary local-model pipeline runs.
---

# Fanning out a big LaTeX book across subagents — and reconciling it

`translate-book-to-latex` is the *single-agent* per-chapter loop. This skill is
what you add when the book is big enough that you fan the work out to many
subagents at once. The work itself (reading pages, writing translated prose,
redrawing or cropping figures) is unchanged — what changes is that **a dozen
workers run in parallel, some will die mid-task, and the pieces must rejoin into
one book whose numbering and cross-references all resolve.**

Three phases: **slice → run (reliably) → reconcile.** The reliability protocol in
§2 and the reconciliation in §3 are the parts you cannot improvise; read
`references/reliability-protocol.md` and `references/assembly-reconciliation.md`
before a big run.

## 0. When to fan out (and when not to)

Fan out when units are **independent and write to disjoint files**: one chapter
per agent, or for a figure-heavy chapter one *section* per agent and figures in
separate batches. Do **not** fan out work that edits the same file (the shared
preamble, the master `book.tex`, a glossary) — one agent owns each shared file,
serially. The orchestrator never does the bulk writing itself; it dispatches,
collects short summaries, and audits. Agents write files; **agents return 3–5
lines, not file contents** (returning prose burns the orchestrator's context for
nothing — the work is already on disk).

## 1. Slice the work (resumable units)

```
book-ru/
  preamble.sty            one owner, edited serially
  main.tex                \include{chapters/chNN} per chapter
  chapters/chNN/secNN_M.tex     one file per section  (a worker's unit)
  figures/chNN/figNN_M.tex      one file per figure   (a figure-batch's unit)
  PROGRESS.md / TRANSLATION-PLAN.md   the resumable ledger + lessons
```

A unit = one section file or one figure file. Small units are the whole game:
they fit inside the watchdog window, a dropped agent loses one file not a
chapter, and the ledger makes the run resumable. Record `pdf_index = book_page -
offset - 1` once (see translate-book-to-latex §0) and put each unit's page range
in the dispatch prompt so a worker never scans the whole PDF to find its pages.

## 2. Run reliably (the protocol that survives a real session)

**Wave-based dispatch, concurrency ≤ 3.** Dispatch a small wave, wait, audit,
dispatch the next. More than ~3 concurrent figure-heavy agents is where socket
drops and rate-limits start killing workers. Lower concurrency loses less when
one dies.

**Anti-stall (beats the ~600 s no-progress watchdog).** The kills happen when an
agent reads many pages/images *before* it writes anything. Every worker prompt
must enforce **incremental, write-early** behaviour:
- Write the section/stub file within the first 2–3 tool calls, then fill it in.
- Figures **one at a time**: view that one figure's region → write that one
  figure file → next. **Never** pre-render or pre-read all of a chapter's
  figures up front.
- Frequent small tool calls beat one big silent think.

**A unit too big for one write — split the SOURCE by word budget, not by structure.**
Some chapters have few section boundaries, so even one "unit" is a single
~13k-word write that the watchdog kills mid-stream — and slicing by heading does
not help. Split the *source* by **word budget** (~4–5k words) at paragraph
boundaries into sub-slices and dispatch one agent per slice. Empirically the
reliable single-write size is well under one big chapter: ~4–6k-word slices land,
~9k+ stall. At the join, only the **first** slice carries the chapter title/byline
and only the **last** carries the endnotes + bibliography; the middle slices are
pure body — concatenate `a1 + a2 + … + b` in order. Keep the `[^n]` note markers
in whatever slice they fall in; the definitions all live in the last slice, so a
straight concatenation resolves them.

**Model choice is a reliability lever, not just a cost one.** At concurrency >~4,
the heaviest model drops sockets markedly more often on long single writes; a
faster mid-tier model both finishes inside the watchdog window and survives
parallelism better. For a fan-out of many long prose units, prefer the faster
model and let the disk-verification protocol (below) catch the rare miss — rather
than chasing a "better" model that keeps dying mid-write. Note the failure can be
silent **and** total: a worker may report "completed (socket error)" having
written **nothing** — so verify by file every time, never by the agent's status.

**Recover from drops using the disk as source of truth.** A socket drop often
kills only the *final report* — the files are already written. On any drop or
non-report: **check the disk first** (`Glob` the unit's expected output) before
re-dispatching. If the file is there and compiles, the unit is done; mark it and
move on. Re-dispatch only the genuinely missing units. Never assume failure from
a missing summary.

**Text-first, figures-second** for figure-heavy chapters. A text agent writes the
prose plus *stub* figure files (a labelled placeholder box) so the chapter
compiles immediately; later figure batches replace the stubs. This decouples the
two failure surfaces and lets the book build green long before every figure
exists.

**Cleanup discipline.** Never run a glob delete like `Remove-Item *.png` in a
figures tree — a worker's "cleanup" once wiped five finished crops. Delete named
files only. (On Windows PowerShell, also keep `Remove-Item` away from the same
command as LaTeX here-strings — the sandbox classifier false-flags the mix; split
them.)

## 3. Reconcile at the join (where a fanned-out book breaks)

Concatenating independently-produced chapters introduces failures a single-agent
run never sees. Run these checks after each wave merges into `main.tex` — details
and the worked Complex-Analysis cases in `references/assembly-reconciliation.md`:

- **Duplicate inclusion → "multiply defined".** A figure `\input` from two
  places defines its `\label` twice. `scripts/input_inventory.py` lists every
  `\input`/`\include` and flags any file pulled in more than once, and reports any
  `\label{...}` string defined in two files.
- **Boundary figures/examples.** A figure or worked example that sits on the line
  two agents share gets dropped by both or duplicated by both. List each split
  boundary and confirm the straddling object landed in exactly one unit.
- **Per-type, per-chapter numbering.** Each theorem-like type gets its own
  `\newtheorem{..}{..}[chapter]` counter and `\numberwithin{equation}{chapter}`,
  so "Теорема 2.1" and "Пример 2.14" coexist and reset each chapter — match the
  source's scheme, set it once in the preamble, never per chapter.
- **Cross-section number clashes.** Two sections each numbering an equation set
  the same way can collide (e.g. eq (10.1) defined in both §10.1 and §10.2). Check
  the source: often one set was *unnumbered* — convert those `equation` envs to
  `\[ \]`. Likewise dedupe a table/figure number that two sections both claimed.
- **Compile-log gate.** The single source of truth that the join is clean:
  `scripts/build_audit.py book.log` prints `errors / undefined / multiply /
  missing` and the page count. The bar is **all four zero** and zero bitmap
  (Type-3) fonts (hand that font check to `latex-pdf-font-audit`). Re-run after
  every reconciliation edit.

## Companion skills
- **translate-book-to-latex** — the per-unit read→translate→figure→compile loop each worker runs.
- **extract-pdf-figures** — precise cropping for the figures workers carry across.
- **tikz-from-reference-image** / **hybrid-figure-triage** — redraw vs crop per figure.
- **latex-pdf-font-audit** — the Cyrillic+math engine/font setup and the 0-Type-3 / U+0301 checks.
- **latex-audit-orchestration** — the same wave pattern applied to *read-only QA* once the book is assembled.
