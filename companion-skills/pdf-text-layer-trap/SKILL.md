---
name: pdf-text-layer-trap
description: >-
  Detect silent character loss in born-digital PDF text layers, especially missing digits, years and citation locators despite readable prose. Compare extraction with rendered pages and use vision or OCR for proven losses. Not for ordinary scans without a text layer, figure extraction or output font embedding.
---

# The born-digital PDF whose text layer lies

`translate-book-to-latex §1` triages a PDF in one test: `len(doc[p].get_text().strip())`
— `0` ⇒ scanned ⇒ read by vision; `>0` ⇒ born-digital ⇒ **read the extracted text
layer**. That test has a blind spot this skill exists to close: a born-digital PDF
can return a *long, clean-looking* text layer that has **silently dropped an entire
semantic class of characters** — most often **all the digits**. The page passes as
"digital, safe", you translate from the extracted skeleton, and every year, every
`§`, every page locator, every equation number is quietly wrong or absent.

Cause: the PDF embeds **subset fonts** (InDesign/Quark/LaTeX exports do this). The
`ToUnicode` CMap that maps glyph IDs back to Unicode is built per subset and can
omit a class — commonly the lining/old-style **figures** — so the glyphs render on
the page but extract to nothing. The loss is **invisible in the prose** (letters
are fine) and **unrecoverable from context** (you cannot infer "1808" from the
surrounding words). That is what separates it from the bounded `�`-mojibake of
umlauts/ß/© in `scholarly-translation-apparatus §4`, which you *can* repair from
context — here the lost class is open-ended and load-bearing.

## 1. The probe — prove the loss in one command (no Python needed)

Don't eyeball; **count the digits**. Across the whole document, tally each digit
0–9 in the extracted text:

```bash
pdftotext -enc UTF-8 book.pdf - | grep -oE '[0-9]' | sort | uniq -c
```

Read the tally like a forensic test:

- **Healthy** text layer: all ten digits appear, in plausible book-like
  proportions (1 and 2 most common, etc.), totalling thousands for a 300-page book.
- **Lossy** layer: the giveaway is that **some digits never appear at all**, and
  the ones that do appear are **a multiple of the page count** — because the only
  surviving digits come from a per-page watermark/ISBN, not the body. Worked
  example from this project's 308-page PDF: the tally was `0:308 1:924 4:308
  5:616 7:924 8:309 9:616` and **2, 3, 6 were entirely absent**. Every surviving
  count is `k × 308` for the digits of the repeated ISBN `978-1-107-19554-7`; the
  body's digits are simply gone.

Then confirm by **comparing one page's extracted text against its rendered image**
(Read the PDF page with `pages=`): if the image clearly shows "1827", "§381",
"577 sections" and the text layer shows "", "§", " sections", the layer is lossy.
Reproduce across `-layout`, raw, and default modes — it is a font/ToUnicode defect,
so no pdftotext flag fixes it, and `mutool`/`gs` re-extraction won't either.

The probe generalises: swap `[0-9]` for any suspect class to catch a dropped accent
set, Greek (`\p{Greek}` via `rg`), or math glyphs — any class whose extracted
frequency is ≈ 0 while the rendered page plainly shows it.

## 2. The remedy — vision-first for the lost class, text layer as skeleton

Once a class is proven lost, **do not** try to clean or reconstruct it from the
text — switch that class to **vision**:

- The **authoritative source is the rendered page** (Read with `pages=`). Take
  every member of the lost class (every digit, §, year, locator) **off the image**.
- The (lossy) **text layer is still useful as a word-skeleton anchor**: it is
  accurate for letters/punctuation, so it stops a vision pass from dropping or
  inventing a sentence. The gaps even mark *where* the numbers go — `Nuremberg (–)`
  tells you a year-range belongs in the parentheses; read it off the image.
- Bake this into every extraction/translation worker prompt as a hard rule:
  *"The rendered page is authoritative. ALL digits/§/years/page-numbers come from
  the image; the text skeleton has them missing — never copy a number from the
  skeleton."* (This is the inverse of `scholarly-translation-apparatus §4`'s
  "bounded set, fix from context" — restate it explicitly so a worker doesn't
  default to the wrong habit.)

This makes the project **vision-first** rather than text-first even though the PDF
is born-digital — the one case where `translate-book-to-latex`'s "digital ⇒ read
the text" guidance must be overridden.

## 3. Why it matters / when to bother

The dropped class is almost always the **highest-value, least-recoverable** data in
a scholarly or technical book: publication years, `§`/paragraph numbers, page
locators in citations, edition keys, equation/theorem numbers. Getting the prose
right while silently corrupting every number is a worse failure than an obvious
garble, because nothing flags it. Run the §1 probe **before** committing to a
text-first pipeline on any book where numbers carry meaning (anything with dated
citations, sectioned primary sources, or numbered equations). Thirty seconds of
`grep -oE '[0-9]' | sort | uniq -c` decides whether the whole job is text-first or
vision-first.

## Companion skills
- **translate-book-to-latex** — owns the scanned-vs-digital triage this skill
  refines; its vision path (read pages, zoom the margin for numbers) is exactly the
  fallback you switch to here.
- **scholarly-translation-apparatus** — §4 handles the *bounded* `�`-mojibake case
  (umlauts/ß/© fixable from context); this skill is its unbounded-class counterpart.
- **multiagent-latex-production** — put the "numbers come from the image" rule into
  every fanned-out worker's prompt.
