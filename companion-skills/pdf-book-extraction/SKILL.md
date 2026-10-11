---
name: pdf-book-extraction
description: Convert PDFs and books into clean Markdown with figures intact, using the right engine for the document type (MinerU, Marker, PyMuPDF, pandoc, Calibre). Use this skill whenever the user wants to extract text/formulas/images from a PDF or scanned book, mentions MinerU or Marker or OCR of math, hits MinerU timeouts or zombie processes, has missing/broken figure files after extraction, or needs to reconcile images between two extraction runs. Russian phrasings that must trigger it too — «вытащи текст из PDF», «извлеки книгу в markdown», «распознай формулы из скана», «картинки потерялись после извлечения». Also use it to pick an extraction strategy before any document-conversion pipeline.
---

# PDF/book -> Markdown extraction

For `translate-pdf-latex`, use its current orchestrator and extraction helpers.
The bundled chunker below is a historical standalone example without the full
timeout, process-ownership and acceptance protections of that pipeline. Do not
substitute it into production. Unload the translation model before GPU OCR;
check owned OCR workers have stopped before loading MT. Do not kill unrelated
Python processes. Preserve MinerU JSON sidecars for footnotes and structure.

## Engine selection matrix

| Source document | Engine | Notes |
|---|---|---|
| Math-heavy PDF (textbook, paper) | **MinerU** (`mineru -p in.pdf -o out`) | best formula recognition (vision model) |
| Scan WITH an old OCR text layer, math inside | **MinerU** | ignore the layer on purpose: generic OCR turns formulas into garbage; re-recognize from pixels |
| General digital PDF | **Marker** (`marker_single in.pdf --output_dir out --output_format markdown`) | fast universal |
| Scan without math | Marker `--force_ocr` | |
| Simple digital PDF, no formulas | PyMuPDF (`pymupdf4llm`) | fastest, CPU-only |
| EPUB / FB2 / DOCX / ODT / HTML | **pandoc** directly | born-digital: lossless, no OCR needed — always prefer over a PDF twin |
| DJVU / MOBI / AZW3 | Calibre `ebook-convert x.djvu x.epub` then pandoc | |

Born-digital text layers LIE silently (a subset font's ToUnicode can drop every
digit while prose extracts fine) — before trusting direct extraction, run the
**pdf-text-layer-trap** probe; on a lying layer go vision-first or re-OCR.

GPU prerequisites for MinerU/Marker: CUDA torch
(`python -c "import torch; print(torch.cuda.is_available())"` must be True;
on Windows pip often installs `+cpu` — reinstall from the proper index, e.g.
`--index-url https://download.pytorch.org/whl/cu128` for RTX 50xx) and a mostly
FREE GPU (eject any loaded LLM first; see local-llm-lmstudio skill).

## MinerU operational hazards (all real)

1. **~60-minute client timeout per task.** Books that extract longer than an hour
   fail with `Timed out waiting for result` no matter the speed. Cure: chunk the
   PDF (~200 pages/part), run MinerU per part, merge. Each part finishes in
   20–35 min; resume = skip parts that already produced markdown.
2. **Zombie workers.** On timeout the client often fails to kill the server
   (`did not exit after forceful stop`) — the orphan keeps burning GPU and may even
   FINISH the job. Closing a console does not reliably kill all descendants.
   Identify the owned process tree and verify its exit before restarting;
   check GPU use as well. Never kill all Python processes by name.
3. **Results live in Temp staging, not your -o dir, until the client collects
   them.** After a client death, salvage finished work from
   `%TEMP%\mineru-api-client-*\output\<task-uuid>\<name>\hybrid_auto\`
   (markdown + images/). Verify completeness by reading the md TAIL — it must show
   the book's end (index/bibliography).
4. **VRAM spikes on dense pages** can spill into system RAM (Windows "Shared GPU
   memory" grows) and freeze the machine. Cap appetite:
   `MINERU_VIRTUAL_VRAM_SIZE=8` (GB) -> smaller batch, slower but stable.
5. Startup line `gpu_memory: N GB, batch_size: M` is the health check: 13–16 GB
   good; 1–2 GB = something else holds the GPU.

## Chunked extraction pattern

Ready-made: `scripts/extract_chunked.py <book.pdf> <outdir> --pages-per-chunk 200`
(resumable — parts that already produced markdown are skipped on re-run).
What it implements, if you need to adapt it: split with pymupdf, run per part,
merge markdown in order, harvest images **recursively from the whole part
output tree** (MinerU sometimes nests them deeper than next-to-the-md), resolve
filename collisions by CONTENT comparison (`filecmp.cmp(shallow=False)`, never
by size), and normalize image links to a single `images/` dir. Keep `_chunks/`
until verified — it is the resume state.

## Figure integrity pipeline (run after ANY extraction/merge)

1. Diff references vs files — `scripts/check_images.py <body.tex|book.md> <images-dir>`:
   extracts `![](images/x.jpg)` (md) or `\includegraphics{...}` (tex) names;
   reports missing / zero-byte / fake-JPEG (magic bytes must be FF D8 ... FF D9)
   and writes `missing_images.txt`.
2. Existing-but-unloadable images (TeX says "not a recognized image format"):
   exotic JPEG (CMYK / progressive). `scripts/reencode_images.py <images-dir>`
   re-encodes everything to baseline RGB with Pillow; idempotent, makes a
   one-time backup first.
3. **Reconciling two extraction runs** (re-extraction gives most figures the same
   content-hash names, but a few crops shift by a pixel -> new names) —
   `scripts/map_missing_images.py <body.tex> <new.md> <new-images> <build-images>`
   implements pass 1; pass 2 is the recipe below:
   - Pass 1 — anchor mapping: align OLD and NEW reference sequences with
     `difflib.SequenceMatcher(a=old, b=new, autojunk=False)`; identical names act
     as anchors; equal-length replace-gaps map pairwise in document order.
   - Pass 2 — context mapping for the remainder: compare the ±250-char prose
     window around each figure (strip image markup, lowercase, keep letters),
     match on WORD tokens with `autojunk=False` (char-level ratios on >200-char
     strings collapse because difflib junks the space character!), accept only
     with a clear margin over the runner-up (e.g. ratio ≥ 0.60 and ≥ 0.03 above
     second best).
4. Never trust the build log for missing figures if a safe-includegraphics
   wrapper is installed — it hides them by design. The refs-vs-files diff is the
   only honest audit.

## Quality expectations

Extraction is a draft: spot-check formulas against the original on dense layouts;
text inside raster figures stays untranslated/unchanged (only captions are text).
Prefer born-digital sources over scans whenever both exist.

## Companion skills

- **pdf-text-layer-trap** — detect silently-lossy born-digital text layers
  BEFORE trusting any extractor's output.
- **extract-pdf-figures** / **hybrid-figure-triage** — pixel-accurate per-figure
  crops and the redraw-vs-crop decision, when figures are the deliverable.
- **translate-book-to-latex** — the agent-reads-and-translates route (vision,
  LuaLaTeX) when markdown extraction is the wrong tool for the document.
- **local-llm-lmstudio** — GPU/VRAM choreography while extractors run.
- **local-mt-batch** — what usually consumes the markdown this skill produces.
