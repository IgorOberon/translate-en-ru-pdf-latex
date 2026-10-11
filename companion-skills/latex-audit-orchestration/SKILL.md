---
name: latex-audit-orchestration
description: >-
  Organize a resumable multi-agent, read-only audit of a large LaTeX book, course or document collection. Use for reviewing mathematics, cross-document consistency, prose and figures across many files and producing severity-ranked findings. Applying fixes is a separate authorized task.
---

# Multi-agent LaTeX audit orchestration

## When and why

A 15-lecture course (lectures + problems + solutions + handouts + cheatsheets + faq +
indices + 100+ figures) is far too much for a single review pass — and different
defects need different expertise. This skill fans the work out to four specialized
reviewer subagents, has each **write findings to disk and return only a short
summary** (so the orchestrator's context stays small and the audit scales), and then
aggregates everything into severity-ranked reports. It is designed to be **resumable**:
progress is journaled after every wave, so a fresh session continues from the first
open item.

This is the *audit* (strictly read-only — propose, don't change). Applying the fixes
is a separate stage (see "Handing off to the fixing stage").

## Setup

Create an `audit/` work area (the only place the audit writes) and four reviewer agent
definitions. `references/agent-roles.md` has ready-to-use role briefs for:

- **math-reviewer** — definitions, theorems, proofs, derivations, numeric examples
  (verify numbers by actually computing them — e.g. a quick numpy check — don't eyeball).
- **consistency-checker** — notation, terminology, numbering, cross-references across files.
- **proofreader** — language, typography, LaTeX-markup correctness, draft leftovers.
- **figure-auditor** — figure correctness, readability, agreement with the text, style.

If the harness supports custom subagent types, register these as agents; otherwise
spawn general subagents and paste the role brief into each prompt.

## The dispatch loop (waves)

Work in **waves of a handful of subagents**, not all at once — this keeps the
orchestrator's context bounded and lets you checkpoint.

1. **Batch the files.** Group by lecture/chapter and by role. A typical batch = one
   chapter's core file reviewed by math + consistency + proofreader; figures get one
   figure-auditor per chapter; support files (handouts/cheatsheets/faq…) batched 2/wave.
2. **Spawn the wave.** Each subagent prompt contains **only**: its role brief, its exact
   file list, the finding format, and where to write its findings file
   (`audit/findings/<batch>_<role>.md`). It must **not** read the whole repo — only its
   files plus the shared canon/macros/notation references.
3. **Each subagent writes findings to disk and returns a 3–5 line summary** (counts by
   severity + headline issues). The orchestrator never ingests full findings into context
   during the audit — it reads them only at aggregation.
4. **After each wave, update `audit/progress.md`** (which batches/roles are done) so the
   audit is resumable. Re-run any findings file that's suspiciously tiny (<~2 KB).

## Finding format (every subagent uses this)

Consistency here is what makes aggregation possible. See `references/finding-format.md`.

```
### [CRITICAL|MAJOR|MINOR] One-line headline
- File: path, place: line / environment / label
- Type: math | notation | reference | typo | figure | markup
- What's wrong: …
- How to fix: …
- Confidence: high | medium | low
```

Severity: **CRITICAL** = mathematically wrong / breaks the build / misleads the reader;
**MAJOR** = wrong cross-refs, notation conflicts, incorrect figures, draft text that
renders; **MINOR** = typography, language, style.

## Aggregation (Phase 3)

Once all findings exist, read them and produce (templates in
`references/aggregation-docs.md`):

- **`audit/ERRORS.md`** — all findings, grouped by severity then chapter, as `- [ ]`
  checkboxes with `file:line` so they're directly actionable.
- **`audit/NOTATION.md`** — the cross-cutting notation table: concept → variants seen →
  proposed canonical form (this surfaces the systemic conflicts).
- **`audit/IMAGES_PLAN.md`** — every figure + its issues + a shared style guide.
- **`audit/SUMMARY.md`** — one page: statistics, top-10 issues, the main systemic
  problems. Output this to the user and ask whether to start the fixing stage.

De-duplicate (the same issue found by two roles), and promote anything found in many
places to a "systemic" entry.

## Handing off to the fixing stage

The audit is read-only. When the user approves fixing, the related skills take over:
`latex-typography-normalizer` for the MINOR typography/notation sweep, and
`latex-figure-review` for the figure issues in `IMAGES_PLAN.md`. Fix CRITICAL/MAJOR
first, verify each by compilation (per-chapter test build, then a full build), and keep
journaling progress so the fixing stage is resumable too.

## Discipline that makes this work

- **Context conservation is the whole game**: subagents write to disk, return tiny
  summaries; the orchestrator stays light and can run many waves.
- **Resumability**: `progress.md` after every wave; never lose work to a context limit.
- **Verify numbers, don't trust them**: math-reviewer recomputes; figure-auditor checks
  a figure's claim against coordinates.
- **Read-only during audit**: findings propose fixes; nothing is edited until the
  explicit fixing stage.
