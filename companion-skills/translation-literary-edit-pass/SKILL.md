---
name: translation-literary-edit-pass
description: >-
  Apply a separately requested conservative style pass to an already accurate translation: reduce calques, awkward syntax and officialese without changing meaning, fixed terminology, citations, numbers or notes. Not for initial translation, correcting mistranslations or mechanical layout repair.
---

# The second pass: make an accurate translation read like it was written, not translated

A faithful first-pass translation is often **accurate but wooden**: calques
("specific" → «специфический» everywhere), English word order, towers of genitives
(«понимания сложности его проекта»), pile-ups of passives, dead rhythm. None of
that is a *consistency* defect, so `translation-consistency-audit`'s mechanical
sweep won't catch it; and you must NOT fix it by re-translating, which re-opens
every accuracy and terminology decision you already settled. The fix is a **third
phase** with one job: **style only**. This skill carries the *process and the
safety contract*, not any book's text.

Phase order: **draft translation → consistency audit → THIS style pass → final
typographic QA.** Run it last among the text phases, after terminology is locked.

## 1. The preservation contract (the whole game)

A style edit is dangerous precisely because the editor is touching sentences full
of load-bearing apparatus. Put this contract verbatim in **every** editor prompt;
it is the difference between polish and silent corruption. The editor MUST NOT
change:

- **Meaning.** It is a translation — fidelity outranks beauty. *When unsure whether
  a rewrite shifts the sense, leave it.*
- **Terminology.** Glossary terms are fixed; never swap a canonical term for a
  "nicer" synonym (снятие, наличное бытие, рассудок/разум stay put). Read the
  glossary first.
- **Every citation / siglum / digit, character-for-character.** `(Enc. §87)`,
  `(GW 21:17)`, `(Pippin 2008, с. 14)`, years, `§`, page ranges — untouched.
- **Footnote markers and definitions.** `[^n]` in the body and `[^n]:` at the end:
  none added, removed, renumbered, or re-attached. Count and set must be identical
  before and after.
- **Structural markup.** `\index{}`, `\chapterauthor{}`, headings, `*italics*`,
  «ёлочки», block quotes, and any author notation (e.g. `<being>` concept brackets).
- **The title/byline block** (first lines) — never.

What it MAY (and should) improve: calques and translationese; tangled word order;
genitive/of-chains; tautology and officialese; rhythm and paragraph flow. And a
documented **side-benefit**: a careful style editor reliably *catches real grammar
errors the translator left* — broken gender/number agreement, dangling
gerunds/participles, antecedents that lost their noun, even a non-word coinage.
Those are worth the pass on their own.

## 2. The self-check that makes it safe

Editing in place is one wrong Edit away from dropping a footnote or mangling a
citation. Two cheap gates catch it:

- **Per-unit, in the editor:** before editing, count `[^n]:` definitions and the
  marker set; after editing, count again — they must match. Spot-check that no
  digit or siglum changed (grep a few).
- **Across all units, by the orchestrator** after the wave: one parity sweep over
  every file, and a recompile whose error/overfull counts are unchanged:

```bash
# footnote-marker parity across all translation files (markdown [^n] convention)
for f in 02_translation/*.ru.md; do
  d=$(grep -cE '^\[\^[0-9]+\]:' "$f")
  t=$(grep -oE '\[\^[0-9]+\]' "$f" | wc -l)
  [ "$t" -ne $((2*d)) ] && echo "IMBALANCE $f defs=$d total=$t"
done   # silence == every footnote still has exactly its marker + definition
```

(If the pipeline routes prose through pandoc, the `[WARNING] Note ... defined ...
but not used` message is a *second* free parity gate — a dropped marker surfaces
there at convert time. See translation-consistency-audit for the term/quote sweep.)

## 3. Fan-out and recovery

The style pass is a fan-out like any other (see **multiagent-latex-production**):
one **unit per agent** (one section/half-chapter file), **waves ≤ 3–4**, agents
**edit in place** and return 3–5 lines, not the text. Two things specific to a
style pass:

- It is **lighter than translation** — no vision, no page reading — so it drops
  less often; but the model can **over-edit**, so the prompt must stress *conservative,
  leave-good-prose-alone*. A second pass over an already-polished file is safe (the
  editor leaves what already reads well), which is exactly how you **resume a dropped
  editor**: Edits are atomic, so a killed editor leaves the file valid-but-partially-
  polished with parity intact — just re-dispatch the same prompt to finish it.
- **Re-run the consistency audit AFTER**, not just before: a style edit can
  reintroduce a term variant or a stray straight-quote. Style pass and consistency
  sweep are not substitutes — they bracket each other.

## 4. The dispatch-prompt template (reusable)

```
You are a conservative literary editor of an already-accurate <target-language>
scholarly translation. STYLE POLISH ONLY — do not re-translate.

FILE: <path>  — edit in place (small, targeted edits).
FIRST: read <glossary> and <style-guide>; count [^n]: definitions in the file.
MAY IMPROVE: calques, word order, genitive chains, tautology, officialese, rhythm
  — only where it does NOT change meaning.
NEVER CHANGE: meaning (when unsure, leave it); glossary terms; every
  citation/siglum/digit character-for-character; [^n] markers/definitions (same
  count & set); \index{}, headings, *italics*, «quotes», block quotes, special
  notation; the title/byline (first N lines).
SELF-CHECK after: [^n]: count unchanged; spot-check digits/sigla unchanged.
RETURN 3–5 lines: #edits, parity before/after, kinds of improvements. Not the text.
```

## Companion skills
- **translation-consistency-audit** — the mechanical sweep you run *before and
  after* this pass (term/name uniformity, quote balance, dashes, double spaces).
- **multiagent-latex-production** — the wave dispatch / watchdog / disk-recovery
  protocol this pass reuses; resume a dropped editor the same way.
- **scholarly-translation-apparatus** / **translate-book-to-latex** — the upstream
  draft-translation phases whose output this pass polishes.
- **latex-running-heads-overfull** — the *typographic* final pass; this one is text,
  that one is layout.
