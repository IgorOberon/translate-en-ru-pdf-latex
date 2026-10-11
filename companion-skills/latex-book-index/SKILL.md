---
name: latex-book-index
description: >-
  Build or rebuild name and subject indexes for a large LaTeX book after translation or repagination. Use for Unicode collation, multiple named imakeidx registers, controlled auto-tagging, or malformed index entries. Not for a table of contents, a terminology glossary or general typography fixes.
---

# Building a back-of-book index (names + subjects) with correct non-Latin sorting

The original printed index is **useless after translation or re-typesetting**: its
page numbers point at the source pagination, not yours, and (for a translation) its
headwords are in the wrong language. You must **regenerate** the index against your
own book. Two things are hard and everything else is plumbing:

1. **Collation.** Getting Cyrillic/Greek/accented headwords into correct
   alphabetical order. Plain `makeindex` does **not** do this reliably.
2. **Tagging at scale.** A 300–900 page book has hundreds of index-worthy
   mentions. You cannot hand-place `\index{}` at each one; you **auto-tag** from a
   canonical list and inject the marks safely into the `.tex`.

Decide up front whether you want **one** index or **two registers** — a *name
index* (persons) and a *subject index* are conventional and worth the small extra
setup. Names auto-tag cleanly (proper nouns are unambiguous); subjects need a
curated term list (see §4).

## 1. Collation: use upmendex (or xindy), NOT plain makeindex

`makeindex` sorts by raw byte/codepoint. For UTF-8 Cyrillic that is fragile:
**ё lands after я** (U+0451 > U+044F), upper- and lower-case interleave wrongly,
there is no locale, and multiword heads sort oddly. It may *look* right on a short
list and quietly mis-order a long one — and "the index compiled" tells you nothing
about the order.

Use a Unicode-aware processor instead:

- **`upmendex`** — ships with TeX Live and MiKTeX; a drop-in makeindex replacement
  with ICU collation. `upmendex persons.idx` → `persons.ind`. This is the **default
  recommendation** — it just works for Russian/Greek with no style file.
- **`xindy -L russian -C utf8 persons.idx`** — the other correct option; needs the
  language module present.

Always **render the finished index pages and read them** — compiling clean does not
prove the sort is right. Confirm е/ё placement, case, and that multiword heads
("гражданское общество") sit where they belong.

## 2. Two registers with imakeidx — and the syntax trap that corrupts the body

```latex
\usepackage{imakeidx}
\makeindex[name=persons,title=Именной указатель,intoc,columns=2]
\makeindex[name=subject,title=Предметный указатель,intoc,columns=2]
...
\printindex[persons]
\printindex[subject]
```

**THE TRAP (silent, compiles "successfully"):** a named-register entry is
`\index[persons]{Headword}` — index name in **square brackets**. If you instead
write `\index{persons}{Headword}` (braces), LaTeX routes the term *persons* into
the *default* index (which you never declared → a harmless-looking
`Undefined index file 'master'` warning) **and typesets the second group
`{Headword}` as visible text in the body.** The book builds, the indices come out
empty, and stray headwords are scattered through the prose. If your index is empty
or you see headword fragments in the text, grep for `\index{` (brace form) first —
`scripts/check_index_syntax.py` does exactly this.

## 3. Build sequence (run the index program manually)

imakeidx can auto-run the index program only with `-shell-escape`, which is often
off. Don't rely on it — run it by hand between passes:

```bash
lualatex -interaction=nonstopmode book.tex          # writes persons.idx, subject.idx
upmendex persons.idx                                 # -> persons.ind
upmendex subject.idx                                 # -> subject.ind
lualatex -interaction=nonstopmode book.tex           # \printindex reads the .ind
lualatex -interaction=nonstopmode book.tex           # settle TOC/index/page numbers
```

Bash trap: **`grep -c PATTERN file` exits 1 when the count is 0.** If a build chain
ends on a zero-match grep (e.g. `grep -c '^!' log`) the whole job reports failure
though the PDF is fine. Don't end a `&&`/background chain on a counting grep; use
`grep -E '^!' log | head` or append `|| true`.

## 4. Auto-tagging: inject \index from a canonical list, safely

You tag from lists you already have: the **name glossary** (`names` table from the
translation) for persons, and a **curated set of distinctive concept terms** for
subjects. `scripts/add_index.py` post-processes the chapter `.tex` files and
appends the marks. Key rules it encodes:

- **Inject at the END of a body paragraph line, never inline.** Appending
  `\index[...]{}` to the end of a paragraph is safe; splicing it at the match
  position risks landing inside a command, `\textit{}`, math, or a citation. The
  page recorded is where the paragraph ends — close enough for an index, and it
  never breaks the build.
- **Skip non-body lines.** Never tag inside headings (`\chapter`, `\section`,
  `\booksection`), the bibliography list, or lines that begin with `\`. A footnote
  in a heading already taught you why TOC-bound moving args hate stray macros.
- **Persons — proper nouns, declension-tolerant.** Match a capitalised surname
  plus up to ~3 trailing lowercase letters (`Кант`, `Канта`, `Кантом`) with word
  boundaries; the leading capital keeps you from tagging the adjective
  (`кантовский`). Headword form: `Фамилия, Имя`. **Exclude the book's own
  subject** — a Hegel handbook with "Гегель" on every page yields a useless
  index entry; drop it. Decide persons-vs-places: a "name index" usually means
  people only, so exclude the toponym/realia tables from your name list.
- **Subjects — curated, distinctive, NOT every common word.** Indexing «бытие» or
  «свобода» (on every page) produces a wall of page numbers nobody can use. Pick
  ~25–40 *distinctive* concept terms (снятие, наличное бытие, дурная
  бесконечность, господство и рабство, хитрость разума, вторая природа…), each
  with a declension-tolerant regex and a canonical headword. Be honest that an
  auto-built subject index is a strong *draft*; a hand-curated one is editorial
  work.
- **Re-run cleanly.** Auto-tagging mutates the `.tex`; running it twice double-tags.
  Regenerate the `.tex` from source (your md→tex step) first, then tag once, then
  build. Make tagging the last step before compiling.

## 5. Order of front/back matter and what goes in the TOC

`\printindex[...]` belongs in `\backmatter` (or at the end), one call per register;
`intoc` in the `\makeindex` options puts each index into the table of contents.
Indices come last; the table of *contents* is unrelated (`\tableofcontents`) — do
not confuse a request for "the index" with "the contents".

## 6. Checklist

1. Preamble: `imakeidx` + one `\makeindex[name=…]` per register (§2).
2. `\printindex[name]` per register in `\backmatter` (§5).
3. Build the canonical name list (people only, minus the book's subject) and the
   curated subject-term list.
4. Regenerate `.tex` from source, then run `scripts/add_index.py` once (§4).
5. `scripts/check_index_syntax.py` — assert zero `\index{name}{` brace-form bugs (§2).
6. Build with the manual upmendex sequence (§3).
7. **Render the index pages and read them** — verify Cyrillic/Greek order,
   case, multiword heads, and that no headwords leaked into the body (§1–2).

## Companion skills
- **scholarly-translation-apparatus** — the surrounding humanities-translation
  apparatus (quote ledger, endnotes, glossary) that produces the name list you tag from.
- **translation-consistency-audit** — unify name spellings *before* indexing, so
  one person is not split across two headwords.
- **multiagent-latex-production** — the orchestration that produced the chapter
  `.tex` files you tag.
- **latex-running-heads-overfull** — fix any Overfull lines the two-column index introduces.
