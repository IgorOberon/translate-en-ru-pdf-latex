---
name: scholarly-translation-apparatus
description: >-
  Handle scholarly translation apparatus: primary-source quotations and a verification ledger, canonical terminology, endnotes and multi-edition citations. Use for humanities books with these features. Complements the book translation workflow; not for ordinary math typesetting or generic font/build diagnosis.
---

# Translating a scholarly book: the quote ledger, endnotes, and citation apparatus

`translate-book-to-latex` carries the per-chapter loop, engine/font choice, and
the math/figure traps. This skill carries the apparatus a **humanities** book
adds on top: it quotes a primary text, it footnotes everything, and it cites
sources in a compressed multi-edition shorthand. The single decision that defines
the quality of the whole translation is in §1. It carries *process*, not any
book's text.

## 0. The shape of a scholarly chapter (recognise it first)

Born-digital academic books (Springer, Palgrave, OUP, …) almost always lay a
chapter out as three blocks in this order:

```
<body>                 prose with superscript note markers: ...philosophers."1
Notes                  numbered ENDNOTES 1..N  (the real footnote bodies)
References             the bibliography (alphabetical)
```

So the "footnotes" live at the **end** of the chapter as endnotes, referenced by
superscript numbers in the body. Your job is to put each endnote back where it is
referenced. Decide your target form **once** and keep it for all chapters:

- **Footnotes at page bottom** (recommended, most readable): each superscript
  marker `word^n` in the body becomes `word\footnote{<translated endnote n>}`.
  You must stitch — match every body marker to its `Notes` entry. Do NOT lose one;
  count them (`grep -c footnote chNN.tex` should equal N).
- **Endnotes** (faithful to source): keep them collected; needs the `endnotes`
  package. Choose this only if the user wants exact structural fidelity.

The `References` block becomes a chapter-end `\section*{Литература}` / `\section*{Bibliography}`
with the entries **left in the original Latin script** (titles are not translated);
only the connective text inside a note ("see also", "cf.", "trans.") is translated.

## 1. Quoted primary sources — SUBSTITUTE the canonical translation, never re-translate

This is the heart of a humanities translation and the mistake that ruins it.

A commentary in language **L2** quotes a primary work **A** (Hegel, Kant, Plato,
Scripture…). The author quotes A *in L2* (often itself a translation of A from
L0). If A already has a **canonical translation in your target language L3**
(e.g. the Stolpner *Наука логики*, the Lossky *Критика чистого разума*, a standard
Bible translation), then **quoting A by re-translating the author's L2 quote into
L3 is a translation-of-a-translation — the worst possible result.** A specialist
reader will reject terminology that doesn't match the canonical edition.

**Rule: for every quotation of a primary source, substitute the canonical L3
translation of that passage. Re-translate only the author's *own* prose and
quotes of *secondary* literature (other commentators) that have no canonical L3 form.**

How to tell a primary-source quote from a secondary one: primary quotes carry the
work's citation shorthand (`(SL 115/118/111)`, `(EL 49)`, a Stephanus number, a
chapter:verse). Quotes attributed to *a named modern scholar* ("as Houlgate
notes…") are secondary — translate those normally.

### The quote ledger (resumable, and the only honest way to ship)

You usually will **not** have the printed canonical edition open. Do not let that
stall you and do not silently invent. Render each primary quote in the **canonical
style and terminology** (the established equivalents — see §2) and **log every one**
to a per-chapter TSV so it can be checked later against the printed edition:

```
notes/quotes_chNN.tsv      columns:  slref <TAB> source_quote <TAB> target_render <TAB> status
SL 78/83/82	pure being and pure nothing are the same	чистое бытие и чистое ничто суть одно и то же	draft
```

`status` is `draft` until someone collates it against the printed edition, then
`verified`. This ledger is the deliverable that makes the translation auditable:
at the end you can say exactly "N primary quotes, all rendered in canonical style,
M still to verify against the print edition" instead of pretending they're exact.
When the user later supplies the canonical text (a PDF/file), you sweep the
ledgers, fix any divergence, and flip `draft → verified` — without re-reading the
whole book.

Wrap primary block quotes in a dedicated environment so they are visually marked
and trivially greppable later:

```latex
\newenvironment{primaryquote}{\begin{quote}\small}{\end{quote}}
```

## 2. The terminology spine: one glossary, built before translating

A scholarly work hinges on a fixed technical vocabulary with established target
equivalents. Build it **first**, as a TSV, and feed it to every translation pass
(or every subagent). Three columns minimum — source term, original-language term,
canonical target term — plus a notes column for the traps:

```
glossary.tsv     english <TAB> german <TAB> russian <TAB> notes
Determinate being	Dasein	наличное бытие	KEY: never "существование"
Sublation	Aufhebung	снятие	KEY: not "отмена"/"упразднение"
Quantum	Quantum	определённое количество	canon; not "квант"
```

Mark the high-risk terms (where the obvious cognate is *wrong*) so they survive.
One source term → one target term, everywhere; the cross-chapter check is in the
`translation-consistency-audit` skill. If a translator hits a term not in the
glossary, it does **not** get invented silently — it goes to `notes/glossary_queue.tsv`
for ratification, so the spine stays consistent.

## 3. Macros that centralise the apparatus

Define these once in the preamble; they keep formatting uniform and make the
output greppable for QA.

```latex
% Inline original-language term in brackets, as the source prints it: [Aufheben]
\newcommand{\de}[1]{[\textit{\foreignlanguage{german}{#1}}]}
% Inline original term kept in italics (no brackets)
\newcommand{\en}[1]{\foreignlanguage{english}{\textit{#1}}}
% Multi-edition citation shorthand:  \slref{115/118/111} -> (SL 115/118/111)
\newcommand{\slref}[1]{(SL~#1)}
```

The `(SL x/y/z)` form is a **triple page reference** to three editions the author
keyed (e.g. two German + one English). Do not "fix" or collapse it — reproduce the
shape verbatim; it is part of the scholarly apparatus. One macro keeps the format
identical across thousands of citations.

**polyglossia/babel trap — Latin is not a loaded language.** `\foreignlanguage{latin}{plura entia}`
errors with *"the language latin is not loaded"* under polyglossia (which typically
loads only your target language + english + german). For Latin phrases (`ens`,
`a priori`, `plura entia`, `omnis determinatio est negatio`) use plain
`\textit{...}`, not `\foreignlanguage{latin}{...}`. Greek (`τὸ ἕτερον`) and
the math you need usually render inline in a full Unicode serif (Times New Roman,
STIX Two Text) with no language switch — verify by looking, not by assuming.

## 4. Source prep: getting clean translatable text out of the PDF

A born-digital PDF made from InDesign/Quark often uses **custom Type1 font
encodings**. Plain `pdftotext` then silently corrupts the text:

- umlauts / ß / © / “smart” punctuation become the replacement char `�`
  (`Gülten` → `G�lten`, `©` → `�`);
- words glue to their endnote markers (`philosophers."1`, `isreality`);
- ligatures (`fi`, `fl`) may vanish.

Best extraction: **`pdftotext -enc UTF-8 -f A -l B` WITHOUT `-layout`** (no-layout
reflows paragraphs, which you want for prose; `-enc UTF-8` preserves what the
ToUnicode map has). Then a cleanup pass: strip running headers (the SHOUTING
chapter title), bare page numbers, and the `© The Author(s) … DOI …` furniture
that pdftotext injects at every page break; rejoin hyphenated line-breaks; and
repair every `�` from context (umlauts in names/German words, dashes, ©).
Map chapters to PDF pages once — there is a constant offset between the printed
page number and the PDF page index (front matter); record it and slice per chapter.

If the ToUnicode map is broken for the special glyphs specifically (so `�`
persists even to a UTF-8 file), the missing characters are a bounded set (a few
proper names, German words) — fix them against context; do not OCR the whole book.

## 5. Build gotchas specific to this kind of book

- **MiKTeX `xelatex.fmt` corruption.** If xelatex suddenly dies at startup with
  `FATAL xelatex.core - internal error` (Debug.cpp) and `still open: …xelatex.fmt`
  — and it built fine a moment ago — the **format file is corrupt/locked** (often
  a prior xelatex killed by a timeout). It is NOT a document error and produces no
  document `.log`. Fix: `initexmf --dump=xelatex` then `rm main.fdb_latexmk` and
  rebuild. Bake auto-recovery into the build command:
  ```bash
  latexmk -xelatex -interaction=nonstopmode main.tex || \
    { initexmf --dump=xelatex; rm -f main.fdb_latexmk; latexmk -xelatex main.tex; }
  ```
  latexmk also *caches* the failure ("gave an error in previous invocation"); clear
  `main.fdb_latexmk` to force a clean retry.
- **A back-of-book index — do NOT trust plain makeindex for Cyrillic.** `makeindex`
  sorts by codepoint, which is fragile for Cyrillic (ё lands after я, case
  interleaves, no locale); it may look fine on a short list and mis-order a long
  one. Use **`upmendex`** (ICU collation, ships with TeX Live/MiKTeX) or
  `xindy -L russian`. Hierarchical subentries still work (`\index{бесконечное!дурное}`).
  For a real two-register index (Именной + Предметный), auto-tagging hundreds of
  entries, and the `\index[name]{}` vs `\index{name}{}` syntax trap, use the
  dedicated **latex-book-index** skill. See translation-consistency-audit for the
  text QA.
- **`python` exit code 49 in Git-Bash on Windows** = the Microsoft-Store Python
  stub; it runs nothing. Use the **PowerShell** tool or `py -3.x` for any scripting,
  or avoid Python and use shell/grep tools.

## 6. Per-chapter checklist

1. Extract the chapter body + `Notes` + `References` (clean per §4).
2. Translate body prose with the glossary (§2) + style guide; keep the author's voice.
3. Stitch each endnote into a `\footnote{}` at its marker (§0); lose none.
4. For each primary-source quote: substitute canonical L3 rendering, wrap block
   quotes in `primaryquote`, and append a row to `quotes_chNN.tsv` (§1).
5. Render `References` as `\section*{Литература}`, titles in original script (§0).
6. Compile; `grep -c footnote` == N; fix the build with §5 if it dies.
7. Record status in a resumable `manifest.json` so the next session resumes exactly.
