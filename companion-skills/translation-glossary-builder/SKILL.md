---
name: translation-glossary-builder
description: >-
  Build and maintain the terminology GLOSSARY for a book translation BEFORE and
  DURING the translation — the artifact that translation-consistency-audit later
  audits against. Use whenever a user starts translating a book/course and needs
  a term base, says «составь глоссарий», "extract the terminology", wants names
  transliterated consistently (Schwarz, Möbius, Houlgate), has a publisher's or
  editor's term list to adapt, asks why a machine translation renders the same
  term two ways, or plans a multi-book series that must share terminology. Also
  use when an auto-generated glossary contains junk (exercise verbs like Show/
  Prove as "terms", surnames translated by meaning, Schwarz rendered as Черный) and needs
  editorial cleanup.
---

# Translation glossary: build, curate, feed, maintain

A glossary is the spine of a consistent translation. This skill covers creating
one (by hand, from a publisher's list, or auto-extracted), curating it, feeding
it to whatever does the translating (human, agent, or a local MT model), and the
lifecycle rules that keep it from silently corrupting a long run.

## Two canonical formats — keep both in the project

For the `translate-pdf-latex` dispatcher, terminology preparation is an optional,
explicit task, not an automatic cloud/paid stage. Review the compact UTF-8
`glossary.md` beside the source BEFORE `pipeline.py init`; init snapshots it.
Keep a richer editorial TSV only if useful; convert it to the Markdown feed
before init (TSV is not automatically consumed by this route). Freeze the feed
during a run. To change it, create a new input/job; do not edit `JOB/input` or
clear caches. Glossary instructions guide the model, not enforce literal
substitution. Check a short translation sample for ambiguous terms.
See the main pipeline README's glossary section for the runnable commands.

- **`glossary.tsv`** — the editorial spine (`source<TAB>target<TAB>note`), used
  by scholarly-translation-apparatus and translation-consistency-audit.
- **`glossary.md`** — the machine-feed form, one rule per line:
  `Alan Turing => Алан Тьюринг`. Trivial to inject into prompts; blank lines OK.
  A worked sample (names, trap terms, editorial calls, comments) ships as
  `assets/glossary.example.md`.

Generate one from the other; treat the TSV as source of truth.

## What belongs in a glossary (and what must NOT)

INCLUDE:
1. **Proper names** — the highest-yield class; transliteration drifts the most
   (Хоулгейт/Хаулгейт). One row per recurring person, plus the book's own author.
2. **Author's neologisms / signature terms** (e.g. amplitwist => амплитвист) —
   often lowercase, so auto-extractors MISS them; add by hand first.
3. **Trap terms** whose obvious cognate is WRONG in-domain:
   translation => перенос (не «перевод»), mapping => отображение (не
   «картографирование»), power series => степенной ряд (не «мощность»),
   similarity => подобие (не «сходство»), residue => вычет.
4. **Rare/decision terms** a model may not know or where editors made a call:
   loxodromic => локсодромический, cross-ratio => двойное отношение.
5. **Editorial conventions**: zero => нуль (if the house style says so),
   canonical abbreviations (SL => «НЛ»).

EXCLUDE (each line costs prompt tokens on EVERY block and dilutes adherence):
- Trivia the translator/model gets right from context (complex number, radius).
- **Collision-prone words**: `identity => тождественное преобразование` breaks
  "Euler's identity"; `degree => степень` breaks angle degrees. If a word has a
  common second meaning in the book, either scope it as a multiword entry
  ("degree of the map => степень отображения") or leave it out.
- Whole definition sentences. Rules, not prose.

Size budget: 30–130 lines is the sweet spot. For a local MT model every line
rides along with every paragraph (~10 tokens/line); 130 lines ≈ +1.3k prompt
tokens per request — measurable but fine. 500 lines is not a glossary, it's a
dictionary, and small models start ignoring it.

## Auto-extraction: what heuristics can and cannot do

A capitalized-recurring-word extractor (regex over the source text, frequency
threshold ≥ ~10, skip sentence starts) finds most NAMES cheaply —
`scripts/make_glossary.py <book.md> <glossary.md> --host … --model …` does
this and translates each hit ONE time through the local model. Its known
blind spots — check for all of them by hand:

- **Non-ASCII letters**: `[A-Z][a-z]+` misses Möbius, Poincaré unless the
  lowercase class includes U+00C0–U+024F. Also add an ASCII-degraded duplicate
  (`Mobius => Мёбиус`) in case OCR dropped the umlaut somewhere.
- **Lowercase terms** (amplitwist, gradient descent) — invisible to the
  capital-letter heuristic by construction. Hand-add.
- **Exercise/imperative verbs** as false positives: "(i) Show that…" makes
  Show/Prove/Deduce/Check/Verify/Find/Use look like recurring proper nouns
  (a parenthesis is not recognized as a sentence start). Maintain a stoplist;
  purge anything that reads as a command.
- **Mid-sentence capitals** (General relativity → "General") — same stoplist
  family.

## Translating the entries themselves

If a model produces the target column, constrain it explicitly:
"If the term is a person's name, transliterate per standard practice; never
translate a surname's literal meaning." Otherwise you get Schwarz => Черный,
Green's => Гринс. Verify every surname row by eye — this is minutes of work
that saves a whole book of «лемма Черного».

## Feeding the glossary

- **Human/agent translation**: keep glossary.tsv open; consistency is enforced
  by the later audit (translation-consistency-audit) anyway.
- **Local MT model with a fixed prompt template** (Hy-MT2 class): the glossary
  goes in the **system message** ("Strictly use these exact term translations
  (English => Russian): …"). NEVER between the instruction line and the text —
  fixed-template models treat everything after the instruction as payload and
  will happily translate your glossary line by line, 2000 wasted tokens per
  paragraph. See local-mt-batch.
- Series of books by one author: ONE shared glossary file passed to every
  volume beats per-book auto-generation.

## Lifecycle rules (the ones that bite)

1. **Review BEFORE the long run, freeze DURING.** In cached MT pipelines the
   glossary is part of each block's cache key — editing it mid-run invalidates
   the cache and silently re-translates everything. Edit early or after.
2. Every change is append/annotate in the TSV with a note column ("издательство",
   "решение редактора 2026-07"); the md feed is regenerated, never hand-forked.
3. After the translation, run translation-consistency-audit against this same
   glossary — it will find the terms that leaked past it.

## Companion skills

- **translation-consistency-audit** — the post-hoc enforcement of this artifact.
- **scholarly-translation-apparatus** — glossary.tsv conventions for humanities
  books (quotes, sigla, canonical translations).
- **local-mt-batch** — how a machine-translation engine consumes glossary.md.
- **translate-book-to-latex** — the agent-translates methodology this feeds.
