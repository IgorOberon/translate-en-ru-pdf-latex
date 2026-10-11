#!/usr/bin/env python3
"""Translate a masked markdown file EN->RU via any OpenAI-compatible endpoint
(LM Studio, Ollama, llama.cpp server, vLLM ...).

Prompt modes:
  --mode hymt     Fixed Hunyuan/Hy-MT2 translation prompt ("Translate the following
                  segment into <lang>, without additional explanation.") for the
                  Tencent translation specialists. Optional glossary and the
                  placeholder rule are appended as extra translation instructions.
  --mode generic  Full rule set as a system prompt -- for general LLMs (Qwen3.5,
                  Gemma, abliterated variants) used as translators or for a
                  literary polish pass.

Shared behaviour: paragraph-block chunking, pass-through of placeholder-only
blocks, per-block cache (safe to re-run / resumes after interruption), retries.

Examples:
  # LM Studio + Hy-MT2-7B  (Developer tab -> Start Server, default port 1234)
  python translate.py in.masked.md out.ru.masked.md \
      --mode hymt --model hy-mt2-7b --host http://localhost:1234 --glossary glossary.md

  # Ollama + Qwen3.5 (OpenAI-compatible endpoint on port 11434)
  python translate.py in.masked.md out.ru.masked.md \
      --mode generic --model qwen3.5:9b --host http://localhost:11434

Notes:
  * --model must match the id the server reports (check GET <host>/v1/models).
  * top_k / repeat-penalty are not standard OpenAI fields: set them in the
    LM Studio model-load sidebar (Hy-MT2 recommended: top_k 20, repeat 1.05).
"""
import argparse
import concurrent.futures
import hashlib
import threading
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PLACEHOLDER_RE = re.compile(r"\u27e6M\d{6}\u27e7")
THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)

GENERIC_SYSTEM = """You are a professional literary translator. Translate the user's text from English into fluent, natural, literary {lang}.

Hard rules:
- Output ONLY the translation. No notes, no explanations, no preamble.
- Copy every placeholder token of the form \u27e6M######\u27e7 through EXACTLY as-is. They stand for math, code and references -- never translate, reorder, alter, add or drop them.
- Preserve all Markdown structure: keep heading markers (#, ##, ...), list markers, blockquotes (>), table pipes, and emphasis markers (*italic*, **bold**). Translate only the words, not the syntax.
- Do not translate numbers, units, code identifiers, file paths or URLs.
- Translate figure/table captions and footnotes.
- Keep the meaning faithful; write idiomatic {lang}, not word-for-word."""


def build_messages(block, mode, target_lang, glossary, think="off"):
    if mode == "hymt":
        sys_prompt = ("Copy any \u27e6M######\u27e7 placeholder tokens through "
                      "unchanged. Never translate these rules or the glossary; "
                      "they are instructions, not text.")
        if glossary:
            sys_prompt += (
                f"\nStrictly use these exact term translations "
                f"(English => {target_lang}):\n" + glossary
            )
        user = ("" if think == "on" else "/no_think\n") + (
            f"Translate the following segment into {target_lang}, "
            "without additional explanation.\n\n" + block
        )
        return [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user}]
    sys_prompt = GENERIC_SYSTEM.format(lang=target_lang)
    if glossary:
        sys_prompt += (
            f"\n\nGlossary (English => {target_lang}) -- use these exact renderings "
            "consistently:\n" + glossary
        )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": block},
    ]


def call_api(host, model, messages, temperature, top_p):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": 4096,
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer local"},
    )
    with OPENER.open(req, timeout=600) as r:
        data = json.load(r)
    text = data["choices"][0]["message"]["content"]
    return THINK_RE.sub("", text).strip()


def is_translatable(block):
    """False for blocks that are only placeholders / symbols / whitespace."""
    stripped = PLACEHOLDER_RE.sub("", block)
    return bool(re.search(r"[A-Za-z\u00C0-\u024F]", stripped))


def split_blocks(text):
    return re.split(r"\n\s*\n", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mode", choices=["hymt", "generic"], default="hymt")
    ap.add_argument("--model", default="hy-mt2-7b")
    ap.add_argument("--host", default="http://localhost:1234")
    ap.add_argument("--target-lang", default="Russian")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--parallel", type=int, default=1,
                    help="concurrent requests (match LM Studio's Parallel slots, e.g. 3)")
    ap.add_argument("--think", choices=["on", "off"], default="off",
                    help="Hunyuan hybrid thinking mode (off = fast, default)")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--top-p", type=float, default=0.6)
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--cache-dir", default=".tcache")
    a = ap.parse_args()

    glossary = ""
    if a.glossary and os.path.exists(a.glossary):
        glossary = open(a.glossary, encoding="utf-8").read().strip()
    os.makedirs(a.cache_dir, exist_ok=True)

    text = open(a.src, encoding="utf-8").read()
    blocks = split_blocks(text)
    n = len(blocks)
    out = [None] * n
    jobs = []
    for i, block in enumerate(blocks):
        if not block.strip() or not is_translatable(block):
            out[i] = block
            continue
        key = hashlib.sha256(
            ("v3" + a.mode + a.model + a.target_lang + glossary + block).encode("utf-8")
        ).hexdigest()
        cache = os.path.join(a.cache_dir, key + ".txt")
        if os.path.exists(cache):
            out[i] = open(cache, encoding="utf-8").read()
            sys.stderr.write(f"[{i + 1}/{n}] cache\n")
            continue
        jobs.append((i, block, cache))

    lock = threading.Lock()
    done = [0]

    def work(job):
        i, block, cache = job
        if len(block) > a.max_chars:
            with lock:
                sys.stderr.write(f"[{i + 1}/{n}] large block ({len(block)} chars)\n")
        messages = build_messages(block, a.mode, a.target_lang, glossary, a.think)
        ru = None
        for attempt in range(3):
            try:
                ru = call_api(a.host, a.model, messages, a.temperature, a.top_p)
                break
            except (urllib.error.URLError, urllib.error.HTTPError,
                    KeyError, TimeoutError, json.JSONDecodeError) as e:
                with lock:
                    sys.stderr.write(f"[{i + 1}/{n}] retry {attempt + 1}: {e}\n")
                time.sleep(2)
        with lock:
            done[0] += 1
            if ru is None:
                sys.stderr.write(f"[{done[0]}/{n}] FAILED block {i + 1}, keeping source\n")
            else:
                sys.stderr.write(f"[{done[0]}/{n}] ok\n")
        if ru is not None:
            open(cache, "w", encoding="utf-8").write(ru)
        return i, (ru if ru is not None else block)

    workers = max(1, a.parallel)
    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for i, res in ex.map(work, jobs):
                out[i] = res

    open(a.dst, "w", encoding="utf-8").write("\n\n".join(out))
    print(f"translated {n} blocks -> {a.dst}")


if __name__ == "__main__":
    main()
