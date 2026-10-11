# The six-stage local translation pipeline (condensed)

Historical overview of the source pipeline's user manual (РУКОВОДСТВО.md).
For current operation use translate-pdf-latex's SKILL.md and pipeline.py.
The older command described here drives all six stages end-to-end
(`translate_book.py`); each stage also runs standalone for debugging.

```
 book.pdf / .epub / ...
        │
   [1] EXTRACT      ── PDF: Marker / MinerU / PyMuPDF;  EPUB etc.: pandoc
        │              → markdown text + images/          (see pdf-book-extraction)
   [1b] GLOSSARY    ── (opt.) auto-find names/terms, translate each ONE time
        │              → glossary.md                (see translation-glossary-builder)
   [2] MASK         ── formulas, code, \ref{…}, URLs hidden behind ⟦M000123⟧
        │              tokens + JSON sidecar map           (scripts/mask_math.py)
   [3] TRANSLATE    ── local MT model translates ONLY prose, block by block,
        │              per-block disk cache = resume       (scripts/translate.py)
   [4] UNMASK       ── every token substituted back byte-for-byte; verify
        │              ZERO placeholders remain            (scripts/mask_math.py)
   [5] TYPESET      ── pandoc: markdown → LaTeX body + Russian preamble
        │                                                  (see latex-build-doctor)
   [6] COMPILE      ── XeLaTeX (2–3 passes) → book.ru.pdf
```

## The three load-bearing ideas

- **Masking is the reliability core.** The model physically cannot see math:
  every formula/code span/`\ref`/URL becomes an opaque token before stage 3 and
  returns verbatim after if the token survives. Check token identities/counts;
  masking cannot recover formulas already lost during extraction.
- **The glossary rides with every block** (system message), so a name on page 5
  and page 500 are guided by the same terminology (not guaranteed identical).
  Written by hand or explicitly generated and reviewed; frozen
  before the long run (it is part of the cache key).
- **Resume is the mantra.** Every translated block lands in a disk cache
  (`work\.tcache\`). After ANY failure — power, crash, Ctrl+C — rerun the SAME
  command: finished extraction is skipped, cached blocks fly by, work continues
  from the break. Cure the cause → repeat the command → nothing is lost.

## Working-folder layout (per book `mybook.*` → `mybook_ru\`)

```
mybook_ru\
├── mybook.ru.pdf      ← the deliverable
├── extract\           ← stage 1 output: markdown + images
├── work\              ← translation kitchen:
│   ├── glossary.md         the file YOU edit
│   ├── book.ru.md          finished translation in markdown (keep it!)
│   └── .tcache\            block cache = resume memory
└── build\             ← LaTeX: body.tex, main.tex, main.log, images, main.pdf
```

Delete NOTHING inside until the book is proofread (especially `.tcache`).
Afterwards keep the PDF, `book.ru.md` (re-typeset later without re-translating)
and `glossary.md` (gold for the next book by the same author).

## Stage-to-skill map

| Stage | Owned by |
|---|---|
| 1 extract | pdf-book-extraction (engines, chunking, image integrity) |
| 1b glossary | translation-glossary-builder |
| 2/4 mask/unmask, 3 translate | THIS skill (`scripts/mask_math.py`, `scripts/translate.py`) |
| 5–6 typeset/compile | latex-build-doctor (fatal builds), markdown-to-pdf-multiscript (multiscript pandoc route) |
| GPU/server ops throughout | local-llm-lmstudio, windows-python-env |
