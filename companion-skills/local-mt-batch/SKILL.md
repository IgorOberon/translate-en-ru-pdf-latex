---
name: local-mt-batch
description: >-
  Machine-translate a large document (book, manual, transcript) through a LOCAL
  specialized MT model (Hy-MT2 class via LM Studio/llama.cpp server) reliably:
  formula/code masking, block splitting, resumable per-block caching, glossary
  injection, parallel requests, and round-trip verification. Use when the user
  wants a free/private bulk translation on their own GPU instead of an agent
  writing the prose (that is translate-book-to-latex), mentions Hy-MT2 / «перевести
  книгу локальной моделью» / a translation that must survive interruptions, or
  when a local MT run misbehaves: the model translates the glossary itself,
  outputs 2000 tokens per paragraph, mangles formulas, or restarts from zero
  after a crash.
---

# Batch MT through a local model — the engine-side discipline

The complementary route to agent translation: a specialized MT model performs
bulk translation locally, without a per-token cloud bill. Speed and quality
depend on the book, model and hardware. Glossary adherence is not guaranteed;
polishing is optional. Caching reduces rework, not all possible failures.

For the current `translate-pdf-latex` project, use its `pipeline.py` and current
scripts. The scripts here are historical standalone references, not replacements
for its acceptance gates, process management or cache validation.

Working reference implementations ship with the skill: `scripts/mask_math.py`
(§1) and `scripts/translate.py` (§2–3, both prompt modes). Where this engine
sits in the whole book pipeline — extraction to compiled PDF — is drawn in
`references/pipeline.md`.

## 1. Mask everything the model must not touch

Before translation, replace every formula (`$…$`, `$$…$$`, LaTeX environments),
code span/block, `\ref{…}`/`\eqref{…}`, and URL with an opaque token
`⟦M000123⟧` (any short unique scheme works); store the token→original map as
JSON. The model receives prose + tokens and one rule: copy tokens unchanged.
`scripts/mask_math.py mask|unmask <in> <out> <map.json>` does exactly this.

- After translation, substitute back byte-for-byte and **verify**: zero tokens
  may remain in the output. `N placeholders left` = the model damaged a token;
  locate `⟦M` in the translated file, fix that block, rerun (cache makes it
  cheap).
- Masking protects captured payloads but does not prove that extraction captured
  every formula or that the model preserved every token. Check token identities,
  counts and protected structures, not only zero unresolved placeholders.

## 2. Blocks, cache, resume

All of this section and §3 is implemented in `scripts/translate.py`
(`--mode hymt` for fixed-template MT models, `--mode generic` for ordinary
LLMs; `--glossary`, `--parallel`, per-block `.tcache`).

- Split on blank lines into paragraph blocks; skip untranslatable blocks
  (pure-token lines, tables of numbers) without an API call.
- Cache each result on disk keyed by
  `hash(prompt_version + mode + model + target_lang + glossary + block)`.
  Consequences you rely on:
  - **any crash/Ctrl+C is free** — rerun the same command, cached blocks fly by;
  - **editing the glossary invalidates everything** (it is in the key) — freeze
    it before the long run;
  - **changing the prompt layout must bump prompt_version**, or poisoned old
    outputs (e.g. from a bad layout that translated the glossary) get reused.
- The historical helper can retain SOURCE after exhausted retries. Treat that
  result as incomplete, not accepted translation. Current pipeline runs must
  use their fail-fast and acceptance checks; preserve cache and resolve failures.

## 3. The prompt contract for fixed-template MT models

Specialized MT models are trained on a rigid template like
`Translate the following segment into <lang>, without additional explanation.\n\n<text>`
and treat EVERYTHING after the instruction as payload.

- Auxiliary material (token-copy rule, glossary) goes in the **system message**;
  the user message stays exactly on-template. Violating this makes the model
  translate your glossary line by line — the signature symptom is
  completion_tokens ≈ 2000 for a 3-line paragraph.
- Hybrid thinking models: prefix the user message with `/no_think` (silent
  chain-of-thought otherwise burns 10–20x time per block).
- Sampler per the model card (Hy-MT2: temp 0.7, top_p 0.6, top_k 20, repeat
  penalty 1.05), saved as the model's server-side defaults.

## 4. Throughput

- Healthy: 1–5 s per paragraph block (7B Q8 on a 16 GB GPU). 30–60 s per block
  means thinking mode, glossary-echo, or CPU inference — diagnose via server
  logs (prompt/completion token counts tell which).
- The server runs N parallel slots; 3 concurrent requests ≈ 3x. Preserve output
  ORDER (map results by block index, not completion order). If long blocks
  start failing only under parallelism, the context is split across slots —
  raise it or drop to sequential.
- Book-scale expectation: ~6000 blocks ≈ 2–5 hours with parallel=3.

## 5. Glossary injection

One `term => перевод` per line in the system message under a strict-use
instruction. Build and curate it with **translation-glossary-builder** (what to
include, collision traps, size budget ~30–130 lines, name transliteration).

## 6. Verification before typesetting

1. Unmask reports zero leftover placeholders.
2. Tail of the translated file shows the END of the book (index/bibliography),
   in the target language — proves completeness better than any counter.
3. Spot-read 3–5 blocks from the middle: fluent target prose, terms per
   glossary, tokens untouched.
4. Then run translation-consistency-audit across chapters, and optionally
   translation-literary-edit-pass for style.

## Companion skills

- **translation-glossary-builder** — the terminology fed into every request.
- **local-llm-lmstudio** — server ops: proxy bypass, JIT/eject VRAM
  choreography, KV-cache math, parallel slots.
- **translate-book-to-latex** — the agent-writes-the-prose alternative when
  quality matters more than cost/speed; both routes share figures/LaTeX skills.
- **translation-consistency-audit / translation-literary-edit-pass** — the QA
  and polish passes after this engine finishes.
