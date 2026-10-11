---
name: translation-consistency-audit
description: >-
  Report cross-chapter terminology, name and abbreviation drift in an existing translation, plus mechanical quote/spacing inconsistencies. Use for glossary-driven textual QA. Produces findings rather than automatic edits; not a factual accuracy audit, translation pass or LaTeX layout repair.
---

# Cross-chapter consistency audit for a translated book

A book translated chapter-by-chapter (especially across sessions or subagents)
develops *invisible* drift: nothing fails to compile, the prose reads fine in
isolation, but a term or a name is rendered two ways across chapters and a
specialist notices instantly. This skill is the cheap grep sweep that catches it
before a print pass. It **reports**; a human or a follow-up edit applies fixes.

Point it at the per-chapter translated source (`chapters/ch*.tex`, or `.md`).

## 1. Terminology uniformity (one source term → one target term)

Drive this from the project `glossary.tsv` (the spine; see
`scholarly-translation-apparatus`). For each canonical target term, two checks:

- **Is the canonical term present and stable?** Count it per file; a chapter that
  discusses the concept but has zero hits may have used a synonym.
  ```bash
  for t in "наличное бытие" "для-себя-бытие" "определённое количество" "снятие"; do
    printf '%-24s' "$t:"; grep -ohc "$t" chapters/ch*.tex | paste -sd+ - | bc
  done
  ```
- **Did a forbidden synonym leak in?** For each "KEY" glossary row whose obvious
  cognate is *wrong*, grep for the wrong word and inspect every hit in context —
  some are legitimate (a real use of "existence") and some are a mistranslated
  term. Judgement, not blind replace:
  ```bash
  grep -nE "существовани" chapters/ch*.tex     # Dasein must be «наличное бытие», but
                                               # "существование" is also a real word — read each hit
  ```

## 2. Proper-name transliteration variants (the highest-yield check)

Names are transliterated by ear and drift the most. List the recurring people and
grep all plausible spellings of each; **a correct result is ONE spelling with all
the hits on it.** Any split is a finding.

```bash
for variants in "Хоулгейт|Хаулгейт|Хоулгэйт" "Мак-Таггарт|Мактаггарт" \
                "Кьеркегор|Киркегор|Кьеркегаард" "Лейбниц|Лайбниц"; do
  echo "--- $variants ---"; grep -ohE "$variants" chapters/ch*.tex | sort | uniq -c
done
```

Build the variant list from the bibliography/References names. Also check the
abbreviation of the primary work (e.g. Cyrillic «СЛ» vs Latin «SL») is used one
way in running prose.

## 3. Typography hygiene of the translated prose

These are textual defects (not LaTeX-build defects — those are a different skill):

```bash
# straight ASCII quotes leaking into target prose (should be 0 — use « » „ " or “ ”)
grep -onE "\"[[:alpha:]]" chapters/ch*.tex | head
# guillemet / nested-quote BALANCE — the two counts must be equal
echo "« $(grep -o "«" chapters/ch*.tex | wc -l)  » $(grep -o "»" chapters/ch*.tex | wc -l)"
echo "„ $(grep -o "„" chapters/ch*.tex | wc -l)  “ $(grep -o "“" chapters/ch*.tex | wc -l)"
# double spaces between words
grep -rnE "[[:alpha:]]  +[[:alpha:]]" chapters/ch*.tex | wc -l
# hyphen between digits where a range needs an en-dash (-- in LaTeX, or –)
grep -oE "[0-9]+-[0-9]+" chapters/ch*.tex | head
```

An **unbalanced** guillemet count (`« ≠ »`) is the one that bites in print — it
means a quote was opened and never closed (or vice versa) somewhere; binary-search
the offending chapter by running the count per file.

## 4. Run it in one pass

`scripts/consistency_sweep.py` (stdlib only) takes a directory of chapter files
and a `glossary.tsv` and prints a compact report: per-term counts, name-variant
splits, quote balance, straight-quote and double-space hits. Run it after each
batch of chapters and again before the final QA. On a machine where `python`
is the Windows Store stub (exit 49), run it with `py -3.x` or via PowerShell, or
just use the grep one-liners above — they need no Python.

```bash
py -3 scripts/consistency_sweep.py --dir chapters --glossary glossary.tsv
```

## 5. What "passing" looks like

- every name resolves to a single spelling across all chapters;
- each KEY glossary term appears, and no forbidden cognate is a mistranslation;
- `« == »` and `„ == “` exactly; zero straight quotes; zero double spaces;
  zero hyphen-in-numeric-range.

Report findings as a short list (`file:line` is clickable); do not auto-edit
prose — a wrong "fix" to a name or term is worse than the split. Hand the list
back, or pair with a targeted edit pass once the human confirms the canonical form.
