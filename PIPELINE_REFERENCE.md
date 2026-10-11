---
name: translate-en-ru-pdf-latex-reference
description: >-
  Translate English PDFs (books, papers, technical and math-heavy documents) into
  Russian and typeset the result as LaTeX/PDF. Use this skill whenever the user wants
  to translate a PDF from English to Russian, convert an English document into a
  Russian LaTeX or PDF, localize a math-heavy or academic PDF into Russian, or run a
  PDF-to-translation-to-LaTeX pipeline — even if they only say "translate this book/paper"
  and mention a .pdf or LaTeX. It masks mathematics/code before translation and
  checks technical invariants; OCR completeness and semantic accuracy need review.
---

# Translate English PDF -> Russian LaTeX

Advanced reference, not the default agent context. Normal local-first operation:
`SKILL.md` and `docs/LOCAL_AGENT.md` (`pipeline.py init/run/status`). Auto-glossary,
polish and cloud configurations below are opt-in. Do not read this entire manual
or run editorial agents merely to dispatch an ordinary translation.

A local pipeline that turns an English PDF into a typeset Russian PDF while preserving
math and structure. The prose is translated by a local MT model (Hy-MT2 via LM Studio;
Ollama works for the generic/polish mode); math and markup are never sent through the
model — they are masked first; source-aware validation checks IDs/count/order.
This does not establish OCR completeness or semantic translation accuracy.

Before reuse, post-editing or publication, read [docs/INTEGRITY.md](docs/INTEGRITY.md).
It defines the v5 cache migration, manifests, checked corrections, draft/release
profiles, and shared transactional build. Follow it instead of old existence-only
resume examples. A bypass produces a draft, never an approved final PDF.
For OCR books, also follow its early checked corrections, unit boundaries,
strict source-review and book-owned term-guard rules. Do not delete footnote
markers or globally substitute philosophical terms to make a gate green.
For complex OCR, use checked `unit_anchors` for unlabeled remarks and paragraph
boundaries; source page ranges describe block coverage, not precise line positions.
Review suspected OCR stops/quotes before splitting. Added ellipses are rejected.
Agent uncertainties must quote the exact source request and be resolved in the
source-bound `editorial.findings.json` ledger before release; see the same contract.

## When to use
Any "translate this PDF / book / paper from English to Russian" request, especially with
mathematics or academic content, or whenever the user wants LaTeX/PDF output.

## Prerequisites (tell the user if any are missing)
- **Translation engine**: LM Studio serving **Hy-MT2-7B** (GGUF, Q8_0; official Tencent quants,
  links in github.com/Tencent-Hunyuan/Hy-MT2) — or Ollama with a general model
  (`ollama pull qwen3.5:9b`) for the `generic` mode / polish pass.
- **Extraction**: `pip install marker-pdf`. Math-heavy alternative: MinerU (`pip install mineru`).
  Scanned books: pdf-craft. Born-digital, no math: `pip install pymupdf4llm`.
- **Pandoc**, and **TeX Live** with **XeLaTeX** + **latexmk** (packages: polyglossia,
  cm-unicode, csquotes, microtype, booktabs, longtable, array, hyperref).
- **Python 3.10+** with `requirements.txt`; optional extractors are installed separately.

## The pipeline (run from the skill directory, in order)
Replace `book` with the document's name.

**Fully autonomous one-shot run** (all steps below + resume support):
```
python scripts/translate_book.py <book> --auto-glossary   # book: pdf/epub/fb2/docx/odt/html/rst/txt/md
```
PDF input additionally takes `--extract auto|digital|scan|math`; djvu/mobi/azw
are converted via Calibre's ebook-convert if installed. Born-digital formats
(epub/docx/...) go straight through pandoc — better fidelity than any PDF OCR.
Output lands in `<book>_ru/` with the final `<book>.ru.pdf`. Re-running the same
command resumes (extraction skipped, translated paragraphs taken from cache).
Add `--auto-glossary` to build the glossary automatically: recurring names and
multi-word terms are detected in the extracted text and each is translated once
by the model (written to `work/glossary.md`; review it — edits reset the cache).
Standalone: `python scripts/make_glossary.py <extracted.md> glossary.md`.

v7 orchestrator flags: `--layout screen|print|compact` (screen = on-screen
default; print = twoside/openright/8mm binding offset; compact = 10pt dense
draft, ~35% fewer pages), `--title "…" --author "…"` (simple title page;
default title is the input stem), `--heading-numbers auto|latex` (auto
suppresses LaTeX section numbers when headings carry the book's own numbering),
`--no-clean` (skip markdown sanitation), `--parallel 3`, `--vram-limit 8`,
`--mineru-timeout S` (kill a stochastically hung MinerU VLM after S seconds,
rc 124, re-run is safe), `--no-lock` (skip the machine-wide pipeline lock;
by default concurrent runs queue on `%TEMP%\freetranslate.lock`), and
`--polish [--polish-model M --polish-host H]` — stage 4b literary polish of
the finished translation (mask -> `translate.py --mode polish` -> unmask,
own cache; defaults to Ollama :11434 / qwen3.5:9b).
The build loops XeLaTeX until aux+toc stabilize (max 4 passes) and then runs
two verifiers automatically: `audit_selfcheck.py` (equation/statement number
gaps with md line numbers, figure captions vs mentions, section numbering,
PDF-text hygiene) and `layout_report.py` (metrics, worst overfulls with pages,
missing glyph list, page previews).

**Existing LaTeX skeleton?** If the target project already has its own main.tex,
preamble and chapter stubs with insertion markers (`% >>> ... N.M ... <<<` +
`\origpages{a--b}`), do NOT run translate_book.py — use the skeleton orchestrator
instead: `python skeleton/translate_into_skeleton.py <project>` (same stages, but
sections land on their markers and the book is built with the project's own
engine). Each chapter is located in the PDF by its printed page numbers
(`--folio auto`, default), so `--offset N` is only a fallback for scans with no
text layer — a single book-wide offset is unreliable because it drifts. See
skeleton/README.md.

The manual steps below remain for control and debugging.

1. **Extract** — PDF to markdown (math kept as LaTeX) + figures:
   ```
   bash scripts/extract.sh <input.pdf> out/ [auto|digital|scan|math]
   ```
   Choose the mode by the PDF: `digital` (born-digital, little math, fast, no GPU),
   `math` (formula-dense -> MinerU, best formula fidelity), `scan` (scanned ->
   forced OCR), `auto` (Marker, the good general default). Output lands in
   `out/<name>/<name>.md` plus an images folder.

1a. **Sanitize** — cut OCR junk before it wastes translation and breaks layout:
   the book's own recognized TOC and back-of-book index (original page numbers
   are useless in a re-typeset translation; both go to `.removed_*.md` audit
   files), running heads that became headings, trailing page numbers on
   headings, lone statement numbers glued as `\hfill(N)`, CJK hallucination
   lines from the extractor (>3 CJK chars on a line -> `.removed_cjk.md` audit
   file, lone stray glyphs cut; `--no-strip-cjk`), Unicode math glyphs
   in prose normalized into `$...$` (incl. plane-1 math alphanumerics and
   ★ ♦ ❑ ⋅ ≈ ∇), plus repair-math for extraction artifacts (duplicate `\tag`s
   on one formula, bare `&` inside `\tag`, formulas locked in literal `\$...\$`):
   ```
   python scripts/clean_markdown.py out/<name>/<name>.md out/<name>/<name>.clean.md
   ```
   Idempotent; every rule can be switched off (`--no-strip-toc`,
   `--no-strip-index`, ...). The orchestrator runs this automatically.

2. **Mask** — hide math, LaTeX commands, code and URLs so the model can't touch them:
   ```
   python scripts/mask_math.py mask out/<name>/<name>.clean.md work/book.masked.md work/book.map.json
   ```

3. **Translate** — masked markdown EN->RU (resumable). Recommended engine: **Hy-MT2-7B**
   served by LM Studio (Developer tab -> Start Server, OpenAI-compatible on :1234):
   ```
   python scripts/translate.py work/book.masked.md work/book.ru.masked.md \
       --mode hymt --model hy-mt2-7b --host http://localhost:1234 --glossary glossary.md
   ```
   The `--model` id must match what the server reports (`curl http://localhost:1234/v1/models`).
   Set the sampler in LM Studio when loading the model: temperature 0.7, top_p 0.6,
   top_k 20, repeat penalty 1.05; context 8192; full GPU offload.
   Fallback / literary polish pass with a general LLM via Ollama's OpenAI endpoint:
   ```
   python scripts/translate.py ... --mode generic --model qwen3.5:9b --host http://localhost:11434
   ```
   Prepare a `glossary.md` first (see `glossary.example.md`) so names/terms stay
   consistent. The script splits by paragraph, caches each chunk (safe to re-run),
   skips math-only blocks, and enforces the rules below (as extra translation
   instructions in `hymt` mode, as a system prompt in `generic` mode).
   Exit codes: **0** all translated; **3** server dead (output NOT written,
   cache intact — re-run resumes); **4** output written but some blocks stayed
   as their English source — the list is in `<dst>.report.json` (`kept_source`,
   `failed_blocks`). Both orchestrators retry a 4 once automatically (failures
   are never cached, so only they are re-requested) and reject the run if it
   persists.

4. **Unmask** — restore all math/markup verbatim. v2 also REPAIRS placeholder
   tokens whose brackets the model damaged (`⟨M001705⟩`, `‹M003223›`,
   `▦M009806◦` instead of `⟦M001705⟧`) by looking the id up in the map —
   check the log line `restored exact: N, repaired damaged: M, unresolved: K`
   (K must be 0 — both orchestrators now enforce this and reject the run
   otherwise). Prevention also lives in translate.py: replies with a damaged
   token are rejected and retried, and never cached:
   ```
   python scripts/mask_math.py unmask work/book.ru.masked.md work/book.ru.md work/book.map.json
   ```

5. **To LaTeX** — convert the translated markdown into a full document with the
   Russian preamble. Two Lua filters run here: `figcaption.lua` glues each
   figure to its «Рисунок [N]» caption (no page break, caption as wide as the
   image), `structure.lua` demotes OCR front matter (cover/publisher/preface
   chapters become unnumbered, so content chapters match the original) and
   suppresses LaTeX section numbers when headings carry native numbering:
   ```
   bash scripts/to_latex.sh work/book.ru.md build/ assets/preamble.tex
   ```

6. **Build** — compile with XeLaTeX:
   ```
   bash scripts/build.sh build/          # -> build/main.pdf
   ```

7. **Fix compile errors iteratively.** Read `build/main.log`. The usual culprit is an
   unescaped special character the translation introduced in prose. Escape
   `% & _ # $ { } ~ ^ \` as `\% \& \_ \# \$ \{ \} \textasciitilde{} \textasciicircum{}
   \textbackslash{}`. Fix `build/body.tex` (or fix the markdown and re-run from step 5),
   recompile, and repeat until clean. This compile→read-log→fix loop is exactly what an
   agent (OpenCode/Claude Code) should do here.

## Second route: scanned Fraktur (19th-century German)

Universal extractors produce garbage on blackletter, so those books go a
different way — and this route has its own acceptance stage, unlike the
MinerU one for a long time:

```
ocr_fraktur.py -> build_ocr_md.py -> run_doc_translate.py
               -> postfix_ru.py   -> assemble_ru_book.py
```

- OCR with Tesseract `deu_latf` (the LSTM model), **not** `deu_frak`: measured
  on 22 pages of Hegel 1812, `deu_latf` recovered 400 of the book's terms
  against 316, and it does not mangle whole words.
- `build_ocr_md.py` rebuilds the book's STRUCTURE from `structure.json`:
  dropped pages and re-shoots, chapter headings by page or by anchor,
  numbered paragraphs («§. 86.», which Fraktur OCR reads as «s. 86.»,
  «6. 84.», «Ss. 104.»), print folios, long-s and tz-ligature repair.
- `assemble_ru_book.py` gates the build on the translation reports and runs
  `layout_report.py` + `accept_fraktur.py` afterwards. A German block left
  inside a Russian book no longer reaches the printed page silently.
- Full recipe with commands: README, section «Готические тома»; traps and
  the `structure.json` key table: АГЕНТ.md.

## Translation rules (also enforced as the system prompt inside translate.py)
Translate **only** natural-language prose from English into fluent, literary Russian.
Never alter:
- Anything inside placeholder tokens `⟦M######⟧` — copy them through **verbatim,
  unchanged**. They stand for math, code and references.
- Markdown structure: keep `#`/`##` heading levels, list markers, blockquotes and table
  pipes — translate the words inside, not the syntax.
- Numbers, units, code identifiers, file paths, URLs.

Additional rules:
- Follow the glossary exactly; be consistent across the whole document.
- Translate figure/table captions and footnotes.
- Preserve inline emphasis (`*italics*`, `**bold**`): translate the content, keep markers.
- Output only the translation — no notes, no summaries, no commentary.

## Notes for local models
- Keep the glossary tight and the rules lean — small models drop instructions when
  overloaded.
- `translate.py` requests non-thinking output by default; it does not change the
  loaded model's context window. Check capacity for the actual runtime.
- Masking protects extracted spans only when ID/count/order checks pass. Missing
  source formulas and OCR errors require source review, not another mask pass.

## Files in this skill
- `scripts/extract.sh` — PDF -> markdown (+images) via Marker / MinerU / PyMuPDF.
- `scripts/clean_markdown.py` — markdown sanitation (stage 1a): OCR TOC/index/running heads, heading tails, statement numbers, strip-cjk (extractor CJK hallucination lines -> audit file), strip-ocr-garbage (junk lines from vector-figure OCR in digital mode -> `.removed_ocr.md`), repair-math (duplicate `\tag`s — last one wins, bare `&` inside `\tag`, formulas in literal `\$...\$` but NOT currency like `\$10`, **font switch over a math accent -> `\boldsymbol`** — the construct that kills XeTeX with «bad native font flag» while leaving main.log empty — plus the rest of the MinerU zoo: overset on a relation, `\textbf{\em X}`, `\mathsf{\bar{(2.16)}}`, lowercase `\mathscr` -> `\mathit`), extended Unicode math normalization (plane-1 math alphanumerics via NFKC — incl. recovering pymupdf4llm's byte-stripped 0xD400–0xD7FF Hangul range —, ★ ♦ ❑ ⋅ ≈ ∇), strip-dup-runs (content duplicated at the seam of MinerU's 64-page extraction windows — matched on prose with math stripped, since the two window recognitions differ in markup; -> `.removed_dup.md`); idempotent, per-rule flags, audit files.
- `scripts/mask_math.py` — mask/unmask math, LaTeX commands, code, URLs (JSON map); v2 repairs damaged placeholder tokens from the map; unmask also tightens `$…$` boundaries (a space right after the opening or before the closing dollar makes pandoc treat the span as literal text and escape the dollars, which cascades all the way to «Cyrillic in cmmi10») — Cyrillic inside a span is never touched, it means the pair is false.
- `scripts/procutils.py` — shared process hygiene: `reap_mineru` identifies real MinerU entrypoints (never arbitrary Python by substring), `unload_llm` verifies LM Studio is empty, `run_mineru` tracks its descendants and waits for cleanup before MT (file log, timeout rc 124). psutil is required; no broad CIM fallback. `PipelineLock` serializes pipeline jobs, not unrelated GPU applications.
- `scripts/prepare_mineru.py` — required before MT in Python MinerU routes: restore page footnotes from the content-list JSON and normalize simple HTML tables. Keep raw files; `.prepare.json` records hashes. Ambiguous notes/complex tables stop for review. In manual shell workflows run this explicitly, then feed `.prepared.md` to sanitation/masking. See `docs/INTEGRITY.md`.
- `scripts/rescue_plaques.py` — shaded text-boxes (definitions/postulates) that MinerU cropped into images: `detect` reports candidate crops AND emits a ready-to-forward vision-agent prompt (`plaques_vision_prompt.md`), a vision agent transcribes+translates them (NOT MinerU re-OCR — its VLM stalls on the crops), `patch` inserts a plain-LaTeX box by image hash and drops the duplicate heading MinerU emitted. Procedure in АГЕНТ.md.
- `scripts/translate.py` — chunked, resumable translation via any OpenAI-compatible server, local or cloud (API key via `LLM_API_KEY` env var); modes: `hymt` (Hy-MT2), `generic` (any general LLM), `polish` (literary edit of an already-translated text); rejects replies with damaged mask tokens, leaked CJK, or that merely echo the source (`--echo-check`, auto-off in polish where "return it unchanged" is the good answer); fails fast after 10 consecutive failed blocks (exit 3, output not written, cache intact); v3.4 writes `<dst>.report.json` every run and exits 4 when any block stayed as source — a partial failure is no longer a silent exit 0. Engine/polish/agent configurations catalog: КОНФИГУРАЦИИ.md.
- `scripts/translate_book.py` — one-shot orchestrator: any supported book format -> Russian PDF, all steps + preflight + resume + layout profiles + smart build + verifiers; frees the GPU before each extraction (forced `lms unload --all`) and reaps leftover MinerU server/worker processes before and after it. A handful of untranslated blocks (`--untranslated-tol`, default 2%: names/bibliography echoes) no longer aborts the run before typesetting; a mass shortfall still does. `--extract digital` warns it skips vector figures.
- `scripts/translate_folder.py` — batch mode: every supported document in a folder, independent per-book runs, skip-finished resume.
- `skeleton/translate_into_skeleton.py` — orchestrator for a pre-existing LaTeX skeleton: same stages, sections inserted at the stubs' markers, built with the project's native engine (LuaLaTeX/XeLaTeX autodetect); locates each chapter in the PDF by its printed folios (`--folio auto` — a single book-wide `--offset` drifts and silently truncates every chapter) and probes the slice afterwards; same GPU hygiene (forced `lms unload --all` + MinerU reaping), plus a Cyrillic acceptance gate — a chapter with <50% Cyrillic prose letters is rejected explicitly — duplicate backstops (`--no-dup-check`), and a soft `layout_report.py` run after every successful build (previews in `book/preview/`); details in skeleton/README.md.
- `scripts/make_glossary.py` — auto-glossary: detects recurring names/terms, translates each once (local or cloud endpoint via `LLM_API_KEY`).
- `scripts/slim_glossary.py` — per-chapter slim glossary feed from a master tsv/md (a 200+ line glossary in the system prompt makes a small model's renderings drift): always-classes by note regexp + rows tagged «гл.N», capped at `--max-rules`.
- `scripts/extract_chunked.py` — chunked MinerU extraction for large PDFs (defeats the 60-min timeout); `--vram-limit` caps GPU appetite; hung chunks are killed on `--mineru-timeout` and auto-retried once.
- `scripts/ocr_fraktur.py` — Fraktur OCR: PDF pages -> PNG -> per-page text (Tesseract `deu_latf`, parallel, resumable, `--dpi auto`).
- `scripts/build_ocr_md.py` — per-page OCR text -> `book.md` WITH the book's structure, driven by `structure.json`: dropped pages/re-shoots, page reordering, injected chapter headings (by page, by text `anchor`, or by paragraph number `at_paragraph`), ready Russian heading text (`ru` -> `headings.ru.json`, so section titles never go through MT), numbered paragraphs with monotonicity filtering and hole healing, print folios, long-s/tz repair, stale part files moved aside as `*.stale`.
- `scripts/page_number_map.py` — «scan page -> printed page» map from running heads (a single offset lies when the scan has re-shoots or gaps).
- `scripts/scan_doctor.py` — scan doctor: run it twice, after OCR and after `book.md`; OCR-model coverage, headings landing on dropped pages, duplicate scans, dedup acceptance.
- `scripts/run_doc_translate.py` — validate an ordered parts manifest, translate with one shared revalidated cache, require result identities; estimate actual request sizes with the shared planner. `--context-per-request` supplies a verified runtime limit; unknown capacity is a warning, not context/parallel arithmetic.
- `scripts/postfix_ru.py` — aligned-block editorial diagnostics and checked post-edits with immutable raw MT reports plus lineage. Terminology rules are suggestions, not global replacements; footnote restructuring is refused. OCR warnings and book-owned term guards remain explicit review findings.
- `scripts/agent_exchange.py` — export exact masked requests for an explicitly requested agent-backed experiment. Does not invoke an API; keep model evidence and raw answers, validate before release. See docs/INTEGRITY.md for transport limitations.
- `scripts/assemble_ru_book.py` — parts -> markdown -> LaTeX -> PDF; heading levels restored from the source, translation-report gate before the build, `layout_report` + `accept_fraktur` after it.
- `scripts/accept_fraktur.py` — acceptance for the Fraktur route: paragraph numbers and their monotonicity, folios, stubs, and the headline metric — the ru/de length ratio BY BLOCK-LENGTH BAND, which shows at a glance whether the model is translating or summarizing.
- `scripts/check_glossary.py` — glossary compliance: how often the prescribed rendering actually appears. German terms are matched case-sensitively (a capitalized noun is what distinguishes the term «Werden» from the auxiliary «werden»); Russian by stem, ё/е folded.
- `scripts/probe_tiers.py` — is there a geometric signal for the edition's tiers (Anmerkung/Zusatz) at all, i.e. is a second hOCR pass worth it? Uses the labelled tier as ground truth; on the 1843 edition the answer was no (identical type size and leading), and the probe says so in a minute instead of hours.
- `scripts/sync_skill.py` — mirror the pipeline into `~/.claude/skills/translate-en-ru-pdf-latex`.
- `scripts/check_images.py` — verify every referenced figure exists and is a real image.
- `scripts/reencode_images.py` — re-encode exotic JPEGs (CMYK/progressive) to baseline RGB.
- `scripts/trim_images.py` — trim near-white margins off figure crops (one-time backup, adaptive mode for faint figures).
- `scripts/audit_selfcheck.py` — consistency verifier: equation/statement numbering gaps (with md line numbers), figure captions vs mentions, section numbering, repeated headings within a chapter (extraction duplicates), PDF-text hygiene.
- `scripts/layout_report.py` — post-build layout report: metrics, top-5 overfulls with pages, missing glyphs GROUPED BY FONT with a diagnosis (Cyrillic in `cmmi*` means Russian text was pulled inside `$…$`; Latin in `rsfs*` means `\mathscr{lowercase}`), hygiene gates, page previews.
- `scripts/full_audit.py` — deep typesetting audit (m1-m8): geometry vs median text frame, under-filled pages, caption integrity for every figure, duplicates, PNG evidence.
- `scripts/measure_build.py`, `scripts/ref_probe.py` — build-quality metrics and reference-scan passport (for comparing runs).
- `scripts/to_latex.sh` — pandoc markdown -> assembled LaTeX with the preamble + both Lua filters.
- `scripts/build.sh` — XeLaTeX compile via latexmk.
- `assets/preamble.tex` — Russian XeLaTeX preamble (fontspec + polyglossia + math + pandoc-compat + figure/caption block + truncated running heads).
- `assets/preamble.windows.tex` — drop-in variant with Windows system fonts (Times New Roman/Arial/Consolas).
- `assets/figcaption.lua` — pandoc filter: figure + caption glued into one block.
- `assets/structure.lua` — pandoc filter: OCR front matter demoted, native heading numbers instead of doubled numbering.
- `glossary.example.md` — glossary format.
- `README.md` — quick start and prerequisites; `РУКОВОДСТВО.md`/`ПОСОБИЕ.md` — user manuals (Russian).
