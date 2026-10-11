---
name: local-llm-lmstudio
description: Operate local LLMs through LM Studio's OpenAI-compatible server reliably. Use this skill whenever the user runs models locally via LM Studio (or a similar llama.cpp server), calls http://localhost:1234, mentions GGUF/quantization/VRAM/GPU offload, complains that local inference is slow or the server is unreachable, asks how much context fits in memory, batch-processes text through a local model, or coordinates GPU memory between an LLM and another GPU tool (OCR, extraction, training). Russian phrasings that must trigger it too — «локальная модель не отвечает», «LM Studio не видит модель», «сервер недоступен», «почему так медленно генерирует», «сколько контекста влезет в видеопамять». Apply it proactively when writing any script that talks to a local model server.
---

# Local LLM via LM Studio — field manual

## Talking to the server (the parts that bite)

- Endpoint: `http://127.0.0.1:1234/v1/chat/completions` (OpenAI schema).
  Health check: GET `/v1/models` — the `id` field there is the exact `model`
  string. Ready-made: `python scripts/server_probe.py [--host …]` (stdlib,
  bypasses the system proxy, prints the ids, and on 10054/refused prints the
  exact cure from this skill).
- **Bypass system proxies for localhost.** VPN/antivirus proxies intercept
  `localhost` and drop connections (WinError 10054). In Python:
  ```python
  opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
  ```
  and prefer `127.0.0.1` over `localhost` in URLs.
- Send only what the server honors: `model`, `messages`, `temperature`, `top_p`,
  `max_tokens`. Things like top_k / repeat penalty are set in the LM Studio UI —
  set them in **My Models -> gear** so they persist as the model's DEFAULTS
  (JIT/auto-load uses defaults, not whatever you clicked once in a chat tab).
- Server keeps running with zero models loaded; requests can JIT-load by model id.
  If JIT fails ("model not found"), load manually once and retry the same call.
- For long unattended runs: raise Max idle TTL (e.g. 720 min) in Developer settings.

## Prompting specialized models (hard-won)

- **Fixed-template models** (machine-translation, rerankers, etc.) treat everything
  after their trained instruction line as PAYLOAD. Never insert glossaries, rules or
  few-shots between the instruction and the text — the model will process them as
  content (e.g. translate your glossary line by line, at 2000 wasted tokens per call).
  Put auxiliary material in the **system** message; keep the user message exactly
  on-template: `<instruction>\n\n<payload>`.
- **Hybrid thinking models** (Hunyuan, Qwen3 family): reasoning mode silently
  generates hundreds of hidden tokens per call. For bulk deterministic work,
  disable it — prefix the user message with `/no_think` (and/or the UI's
  Reasoning toggle). 10–20x speedups are typical.
- Diagnose slowness with the Developer tab log, not vibes: each response shows
  `prompt_tokens` / `completion_tokens`. Healthy bulk task: completion ≈ size of the
  expected answer. If completion is 10x that — the model is thinking, echoing your
  prompt scaffolding, or looping (raise repeat penalty ~1.05–1.1).

## Throughput

- LM Studio serves N parallel slots (badge `Parallel N` on the loaded model).
  A sequential client wastes them; 3 concurrent requests ≈ 3x throughput on
  batchable work. Caveat: context may be shared/split across slots — if long
  prompts start failing only under parallelism, raise context or drop to 1.
- Expected speeds (sanity anchors, 7–8B Q8 on a 16 GB consumer GPU):
  generation 35–55 tok/s, prompt eval thousands tok/s. An order of magnitude
  below that = model on CPU or in system-RAM spillover (see below).

## VRAM choreography (the #1 cause of "it hangs")

- One GPU = one heavyweight at a time. LLM in LM Studio (~9 GB for 7B Q8 + cache)
  and a GPU extraction/OCR tool do NOT coexist on 16 GB. Eject the model before the
  other tool runs; JIT reloads it afterwards.
- Read the other tool's startup line: `gpu_memory: 16 GB, batch_size: 8` = healthy;
  `gpu_memory: 1 GB, batch_size: 1` = starved, will be 10–70x slower and may hit
  internal timeouts.
- **Windows "Shared GPU memory" is the death signal.** Dedicated VRAM full is fine;
  when Shared (= spillover into system RAM over PCIe) grows by gigabytes, everything
  slows 10–50x and the desktop can freeze. Watch it in Task Manager -> GPU. Fixes:
  eject the LLM, and/or cap the other tool (MinerU honors
  `MINERU_VIRTUAL_VRAM_SIZE=8` -> smaller batches).
- Task Manager's default GPU graphs (3D/Copy/Video) do NOT show CUDA compute —
  switch a graph to "Cuda" or trust `nvidia-smi`. "GPU 1%" during heavy inference
  is usually a lie of the wrong graph.
- KV-cache budget: for 7–9B models roughly **0.1–0.15 GB per 1000 tokens of
  context** (fp16), RESERVED at load time for the whole declared window. 8K ≈ 1 GB,
  32K ≈ 3–4 GB, 128K won't fit next to the weights on 16 GB. Don't declare context
  you don't need; K/V cache quantization (q8) halves it if you must go long.

## Console gotchas during long runs (Windows)

- A stray mouse click puts the console into QuickEdit select mode and PAUSES the
  program until Enter. Disable QuickEdit in console properties for unattended runs.
- Progress counters freezing while GPU stays busy = display problem, not compute;
  counters freezing AND GPU at zero = actually stalled.
- The machine must not sleep; display off is fine.

## Companion skills

- **transcribe-seminar** — long DETACHED GPU jobs on Windows that must outlive
  the agent session; also the coexistence trick when a foreign/elevated process
  holds the GPU (`[Insufficient Permissions]`, unkillable): run your own job in
  a lighter compute type (e.g. int8_float16) instead of fighting for the card.
- **local-mt-batch** — bulk translation through this server done right.
- **pdf-book-extraction** — the other GPU heavyweight this server must
  time-share with (eject/JIT choreography).
