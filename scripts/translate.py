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
import difflib
import hashlib
import threading
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit, urlunsplit

from glossary_selection import load_profile, select_glossary
from request_plan import PLANNER_VERSION, plan_fragments
from provenance import atomic_text, canonical_hash, sha_file, sha_text, write_json

print(">> translate.py v4 (unified validator, v5 cache, provenance, shared request plan)",
      flush=True)

from endpoint_policy import model_opener
OPENER = model_opener()

PLACEHOLDER_RE = re.compile(r"\u27e6M\d{6}\u27e7")


def has_damaged_tokens(reply):
    """True when any M###### appears outside an intact \u27e6M######\u27e7 token.

    Models occasionally corrupt the placeholder brackets (\u27e8M001705\u27e9,
    \u2039M003223\u203a, \u25a6M009806\u25e6 ...): the exact unmask would then silently skip
    them and the formula would vanish from the book.
    """
    return bool(re.search(r"M\d{6}", PLACEHOLDER_RE.sub("", reply)))


# Ровно то, что чинит восстановительный проход mask_math.unmask: M###### с
# одним небуквенным соседом с каждой стороны (⟨M001705⟩, ‹M003223›, ▦M009806◦).
RECOVERABLE_RE = re.compile(r"[^\w\s]?M\d{6}[^\w\s]?")


def damage_is_recoverable(reply):
    """True, если ВСЕ битые маркеры ответа починит unmask.

    Три попытки на битом маркере кончались тем, что блок оставался
    английским (на NFCM так потерялись 3 блока из 10013). Но unmask умеет
    восстанавливать маркер, у которого модель испортила только скобки —
    цифры-то целы. Значит терять блок не за чем: если после исчерпания
    попыток порча ИМЕННО такая, ответ можно принять.
    """
    left = PLACEHOLDER_RE.sub("", reply)
    if not re.search(r"M\d{6}", left):
        return True
    return not re.search(r"M\d{6}", RECOVERABLE_RE.sub("", left))


CJK_RE = re.compile(
    "[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    "\u1100-\u11ff\uac00-\ud7af]")   # +хангыль: «시작» доехало до PDF тома 6
CJK_TARGETS = {"chinese", "japanese", "korean", "mandarin", "cantonese",
               "zh", "ja", "ko"}


def has_cjk(reply):
    """Hy-MT2's native script occasionally leaks into non-CJK targets
    (证明, 与 ...) — such replies must be resampled, never cached."""
    return bool(CJK_RE.search(reply))


ECHO_MIN_CHARS = 200        # короче — не судим (заголовки, имена, подписи)
ECHO_RATIO = 0.97


def _norm_for_echo(s):
    return re.sub(r"\s+", " ", PLACEHOLDER_RE.sub("", s)).strip().lower()


def looks_like_echo(block, reply):
    """Ответ почти дословно повторяет исходник — модель вернула эхо вместо
    перевода. Такой ответ надо пересэмплировать и никогда не кэшировать:
    иначе английский абзац молча уезжает в «переведённую» книгу.
    Не судим короткие блоки и блоки без слов исходного письма."""
    b = _norm_for_echo(block)
    if len(b) < ECHO_MIN_CHARS or not re.search(r"[A-Za-z]{2,}", b):
        return False
    r = _norm_for_echo(reply)
    if b == r:
        return True
    return difflib.SequenceMatcher(None, b, r).ratio() >= ECHO_RATIO


# Модель иногда возвращает не перевод текста, а сам промпт — причём в режиме
# hymt она его ещё и ПЕРЕВОДИТ, так что в книгу попадает «/но_тхинк/ Перевести
# следующий отрывок на русский язык». Эхо-детектор такое пропускает: ответ не
# похож ни на исходный блок, ни на глоссарий.
INSTRUCTION_LEAK_RE = re.compile(
    # Служебный токен узнаётся по слэшу или подчёркиванию: без этого
    # «что можно думать об обвинении» ловилось как утечка «/no_think».
    r"(/no[_ ]?think|no_think|/но[_ ]?тхинк|но_тхинк"
    r"|/без[_ ]?(?:рассужден|размышлен|расчет|расчёт)"
    r"|без_(?:рассужден|размышлен|расчет|расчёт)"
    r"|/(?:но|не)[_ ]?думать|(?:но|не)_думать"
    r"|translate the following segment|"
    r"перевести следующий отрывок|переведите следующий (?:отрывок|сегмент)|"
    r"without additional explanation|без дополнительных объяснений|"
    r"placeholder tokens|copy any .{0,20}placeholder|"
    r"strictly use these exact term|скопируйте любые)", re.IGNORECASE)


def leaks_instructions(block, reply):
    """True, когда в ответе видна инструкция промпта, а не перевод."""
    src = Counter(m.group().casefold() for m in INSTRUCTION_LEAK_RE.finditer(block))
    out = Counter(m.group().casefold() for m in INSTRUCTION_LEAK_RE.finditer(reply))
    return bool(out - src)


GLOSSARY_LEAK_MIN_LINES = 3


def glossary_lines(glossary):
    """Содержательные строки глоссария: 'Term => Перевод' и его заголовки.

    Возвращается множество нормализованных строк — по ним ловится ответ,
    в который модель вывалила собственную инструкцию вместо перевода.
    """
    out = set()
    for ln in (glossary or "").splitlines():
        s = ln.strip()
        if len(s) >= 6 and ("=>" in s or s.startswith("#")):
            out.add(re.sub(r"\s+", " ", s).lower())
    return out


def leaks_glossary(block, reply, gloss_set):
    """True, когда модель напечатала строки глоссария вместо перевода.

    Hy-MT2 на части блоков вываливает системный промпт целиком: в готовую
    книгу уезжает весь глоссарий, а его '#'-заголовки становятся главами и
    портят оглавление. Эхо-детектор такое не ловит — ответ не похож на
    исходник, он похож на инструкцию. Строки, которые есть и в самом
    исходнике, не в счёт: там утечки нет.
    """
    if not gloss_set:
        return False
    src = {re.sub(r"\s+", " ", ln.strip()).lower() for ln in block.splitlines()}
    hits = 0
    for ln in reply.splitlines():
        s = re.sub(r"\s+", " ", ln.strip()).lower()
        if s and s in gloss_set and s not in src:
            hits += 1
            if hits >= GLOSSARY_LEAK_MIN_LINES:
                return True
    return False
# Сокращения, после которых точка не кончает предложение. Немецкий научный
# набор XIX века полон их: «z. B.», «d. h.», «u. s. w.», «S. 33.», «§. 160.»,
# плюс инициалы и порядковые номера.
ABBREV_END = re.compile(
    r"(?:\b(?:z|d|u|s|f|i|c|vgl|Vgl|Bd|Th|Nr|Anm|Abschn|Aufl|Hrn|Hr|St|Kap|Cap"
    r"|dgl|ff|cf|resp|bzw|usw|etc|S|Th|vol)\.|\b[A-ZÄÖÜ]\.|\b\d{1,4}\.|§\.)"
    r"\s*$")

THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)

GENERIC_SYSTEM = """You are a professional literary translator. Translate the user's text from {src} into fluent, natural, literary {lang}.

Hard rules:
- Output ONLY the translation. No notes, no explanations, no preamble.
- Copy every placeholder token of the form \u27e6M######\u27e7 through EXACTLY as-is. They stand for math, code and references -- never translate, reorder, alter, add or drop them.
- Preserve all Markdown structure: keep heading markers (#, ##, ...), list markers, blockquotes (>), table pipes, and emphasis markers (*italic*, **bold**). Translate only the words, not the syntax.
- Do not translate numbers, units, code identifiers, file paths or URLs.
- Translate figure/table captions and footnotes.
- Keep the meaning faithful; write idiomatic {lang}, not word-for-word."""


POLISH_SYSTEM = """You are a meticulous literary editor. The user gives you a text in {lang}. Improve it: fix grammar, agreement and calques, replace clumsy or unnatural phrasing with fluent, idiomatic {lang}. Do NOT change the meaning, do NOT add or drop information.

Hard rules:
- Output ONLY the edited text. No notes, no explanations, no preamble.
- Copy every placeholder token of the form ⟦M######⟧ through EXACTLY as-is. They stand for math, code and references -- never reorder, alter, add or drop them.
- Preserve all Markdown structure: keep heading markers (#, ##, ...), list markers, blockquotes (>), table pipes, and emphasis markers (*italic*, **bold**).
- Do not change numbers, units, code identifiers, file paths or URLs.
- If a segment is already good, return it unchanged."""


# Подсказка на повтор после испорченного маркера. Обычная просьба «copy
# placeholders unchanged» стоит в промпте всегда, и если модель её уже
# нарушила, повторять то же самое бессмысленно — нужен более резкий приказ
# именно про этот отказ.
TOKEN_RETRY_HINT = (
    "\n\nCRITICAL: your previous attempt CORRUPTED a placeholder token. "
    "Every token looks exactly like ⟦M000123⟧ — copy it CHARACTER BY "
    "CHARACTER, including the ⟦ and ⟧ brackets and all six digits. "
    "Never translate, re-bracket, renumber, split or drop a token.")


def build_messages(block, mode, target_lang, glossary, think="off",
                   source_lang="English", retry_hint=""):
    if mode == "polish":
        sys_prompt = POLISH_SYSTEM.format(lang=target_lang)
        if glossary:
            sys_prompt += (
                f"\n\nGlossary ({source_lang} => {target_lang}) -- these "
                "renderings are canonical, never replace them with "
                "synonyms:\n" + glossary
            )
        return [{"role": "system", "content": sys_prompt + retry_hint},
                {"role": "user", "content": block}]
    if mode == "hymt":
        sys_prompt = ("Copy any \u27e6M######\u27e7 placeholder tokens through "
                      "unchanged. Never translate these rules or the glossary; "
                      "they are instructions, not text. Preserve every clause and example; "
                      "do not replace unclear words or segment boundaries with ellipses. "
                      "Preserve Markdown syntax, table pipes and row breaks; "
                      "translate cell text without moving cells.")
        if glossary:
            sys_prompt += (
                f"\nStrictly use these exact term translations "
                f"({source_lang} => {target_lang}):\n" + glossary
            )
        # Control-token живёт в СИСТЕМНОМ сообщении, а не в переводимом тексте.
        # Пока «/no_think» стоял первой строкой user-контента, модель на
        # коротких блоках переводила именно его: в томе 6 шесть глав из
        # одиннадцати получили названия «/без_рассуждений», «/но_думать».
        if think != "on":
            sys_prompt = "/no_think\n" + sys_prompt
        user = (f"Translate the following segment into {target_lang}, "
                "without additional explanation.\n\n" + block)
        return [{"role": "system", "content": sys_prompt + retry_hint},
                {"role": "user", "content": user}]
    sys_prompt = GENERIC_SYSTEM.format(lang=target_lang, src=source_lang)
    if think != "on":
        sys_prompt = "/no_think\n" + sys_prompt
    if glossary:
        sys_prompt += (
            f"\n\nGlossary ({source_lang} => {target_lang}) -- use these "
            "exact renderings consistently:\n" + glossary
        )
    return [
        {"role": "system", "content": sys_prompt + retry_hint},
        {"role": "user", "content": block},
    ]


def api_url(host):
    """localhost:1234 -> +/v1/chat/completions; хосты, уже несущие версию
    в пути (…/v1beta/openai, …/v1) -> +/chat/completions."""
    h = host.rstrip("/")
    if h.endswith("/chat/completions"):
        return h
    if re.search(r"/(v\d+[a-z]*|openai)$", h):
        return h + "/chat/completions"
    return h + "/v1/chat/completions"


def call_api(host, model, messages, temperature, top_p):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": 4096,
    }
    # облачные OpenAI-совместимые эндпоинты требуют настоящий ключ
    token = os.environ.get("LLM_API_KEY") or "local"
    req = urllib.request.Request(
        api_url(host),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
    )
    with OPENER.open(req, timeout=600) as r:
        data = json.load(r)
    if data["choices"][0].get("finish_reason") not in (None, "stop"):
        raise ValueError("API response did not finish normally (truncation/refusal)")
    text = data["choices"][0]["message"]["content"]
    return THINK_RE.sub("", text).strip()


IMAGE_ONLY_RE = re.compile(r"^\s*(!\[[^\]]*\]\([^)]*\)\s*)+$")


def is_translatable(block):
    """Блок из одних картинок переводить нечего: имя файла — латиница, и без
    этой проверки модель «переводит» путь, а рисунок теряется."""
    if IMAGE_ONLY_RE.match(block):
        return False
    return _has_letters(block)


def _has_letters(block):
    """False for blocks that are only placeholders / symbols / whitespace.
    \u041A\u0438\u0440\u0438\u043B\u043B\u0438\u0446\u0430 \u0438 \u0433\u0440\u0435\u0447\u0435\u0441\u043A\u0438\u0439 \u0443\u0447\u0442\u0435\u043D\u044B: \u0432 \u0440\u0435\u0436\u0438\u043C\u0435 polish \u0432\u0445\u043E\u0434\u043D\u043E\u0439 \u0442\u0435\u043A\u0441\u0442 \u0443\u0436\u0435 \u0440\u0443\u0441\u0441\u043A\u0438\u0439."""
    stripped = PLACEHOLDER_RE.sub("", block)
    return bool(re.search(r"[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF]",
                          stripped))


def split_blocks(text):
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


VALIDATOR_VERSION = "candidate-v4"
REQUEST_VERSION = "request-v5"
REPAIR_TOKEN = re.compile(r"[⟨‹▦⟦\[<](M\d{6})[⟩›◦⟧\]>]")


@dataclass(frozen=True)
class ValidationPolicy:
    min_ratio: float = 0.0
    length_min_chars: int = 300
    reject_cjk: bool = True
    reject_echo: bool = True
    mode: str = "hymt"


@dataclass(frozen=True)
class Candidate:
    text: str
    reasons: tuple
    repaired: bool = False

    @property
    def ok(self):
        return not self.reasons


def added_cjk(source, reply):
    # A single quoted name must not whitelist an arbitrary hallucinated paragraph.
    return bool(Counter(CJK_RE.findall(reply)) - Counter(CJK_RE.findall(source)))


def added_ellipsis(source, reply):
    return len(re.findall(r"…|\.{3,}", reply)) > len(re.findall(r"…|\.{3,}", source))


def structural_literals(text):
    """Cheap omission checks, not semantic review. Mask IDs are checked separately.

    Digit groups allow decimal punctuation to localize but do not allow numbers
    to disappear. Greek enumeration labels and Markdown note IDs stay verbatim.
    """
    text = PLACEHOLDER_RE.sub("", text)
    return {"numbers": Counter(re.findall(r"\d+", text)),
            "enumeration labels": Counter(re.findall(r"(?<!\w)([α-ω])[).]", text)),
            "footnote IDs": Counter(re.findall(r"\[\^([^\]]+)\]", text))}


def validate_candidate(source, reply, policy=None, glossary=""):
    """One gate for API, cache, repair and assembled fragments. No bad fallback."""
    policy = policy or ValidationPolicy()
    reasons = []
    if not isinstance(reply, str) or not reply.strip():
        return Candidate("", ("empty",))
    ids = PLACEHOLDER_RE.findall(source)
    allowed = {token[1:-1] for token in ids}
    repaired = REPAIR_TOKEN.sub(lambda m: "⟦" + m[1] + "⟧" if m[1] in allowed else m[0], reply)
    if has_damaged_tokens(repaired):
        reasons.append("damaged token")
    if PLACEHOLDER_RE.findall(repaired) != ids:
        reasons.append("mask IDs/count/order")
    if leaks_instructions(source, repaired):
        reasons.append("instruction leak")
    if leaks_glossary(source, repaired, glossary_lines(glossary)):
        reasons.append("glossary leak")
    if policy.reject_cjk and added_cjk(source, repaired):
        reasons.append("CJK addition")
    if policy.reject_echo and looks_like_echo(source, repaired):
        reasons.append("echo")
    prose = PLACEHOLDER_RE.sub("", source).strip()
    translated = PLACEHOLDER_RE.sub("", repaired).strip()
    source_literals, target_literals = structural_literals(source), structural_literals(repaired)
    from prepare_mineru import table_signature
    if table_signature(source) != table_signature(repaired):
        reasons.append("table rows/columns/numeric cells changed")
    for kind in source_literals:
        if source_literals[kind] != target_literals[kind]:
            reasons.append(kind + " changed (possible omission/addition)")
    # Never silently turn an unread word or a request boundary into an omission.
    if added_ellipsis(prose, translated):
        reasons.append("added ellipsis (possible omission)")
    # Short names, headings, captions and formula-only blocks have no length
    # heuristic. Explicit --min-ratio also applies to long polish prose.
    if (policy.min_ratio and len(prose) >= policy.length_min_chars
            and not source.lstrip().startswith("#")
            and len(translated) < policy.min_ratio * len(prose)):
        reasons.append("too short")
    return Candidate(repaired.strip(), tuple(reasons), repaired != reply)


def request_config(a, glossary, glossary_profile=None):
    endpoint = urlsplit(api_url(a.host))
    # No authentication/query strings in on-disk metadata.
    safe_endpoint = urlunsplit((endpoint.scheme, endpoint.hostname or "",
                               endpoint.path, "", ""))
    return {"schema": REQUEST_VERSION, "source_lang": a.source_lang,
            "target_lang": a.target_lang, "model": a.model, "mode": a.mode,
            "endpoint": safe_endpoint, "port": endpoint.port,
            "glossary_profile_sha256": canonical_hash(glossary_profile or {}),
            "glossary_sha256": sha_text(glossary), "think": a.think,
            "templates_sha256": canonical_hash([GENERIC_SYSTEM, POLISH_SYSTEM,
                build_messages("", a.mode, a.target_lang, glossary, a.think, a.source_lang),
                TOKEN_RETRY_HINT]),
            "planner": PLANNER_VERSION, "split_chars": a.split_chars,
            "generation": {"temperature": a.temperature, "top_p": a.top_p, "max_tokens": 4096}}


def request_identity(block, config, fragments, messages):
    return canonical_hash({"config": config, "source": block, "plan": fragments,
                           "messages": messages})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mode", choices=["hymt", "generic", "polish"], default="hymt",
                    help="hymt: перевод Hy-MT2; generic: перевод общей моделью; "
                         "polish: литературная правка уже переведённого текста")
    ap.add_argument("--model", default="hy-mt2-7b")
    ap.add_argument("--host", default="http://localhost:1234")
    ap.add_argument("--target-lang", default="Russian")
    ap.add_argument("--source-lang", default="English",
                    help="язык исходника. Он подставляется в системный промпт "
                         "и в шапку глоссария; при немецком источнике "
                         "хардкод «English» и промпт «from English» "
                         "противоречили самому тексту")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--glossary-profile", help="optional critical entries and relevant term groups JSON")
    ap.add_argument("--parallel", type=int, default=1,
                    help="concurrent requests (match LM Studio's Parallel slots, e.g. 3)")
    ap.add_argument("--think", choices=["on", "off"], default="off",
                    help="Hunyuan hybrid thinking mode (off = fast, default)")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--top-p", type=float, default=0.6)
    ap.add_argument("--max-chars", type=int, default=4000,
                    help="ПОРОГ ПРЕДУПРЕЖДЕНИЯ, а не нарезки: блок длиннее "
                         "этого числа знаков заметен в stderr. Режет блоки "
                         "--split-chars, и без него длинный блок уезжает в "
                         "модель целиком — а Hy-MT2 такие КОНСПЕКТИРУЕТ. "
                         "Разводить эти два ключа приходится потому, что "
                         "нарезка входит в ключ кэша: сменить порог значит "
                         "перевести заново все блоки длиннее него")
    ap.add_argument("--split-chars", type=int, default=0,
                    help="делить блок длиннее N знаков по границам предложений "
                         "и переводить частями (0 = не делить). Hy-MT2 на "
                         "длинных абзацах КОНСПЕКТИРУЕТ: на томе 6 отношение "
                         "длин падало с 0.99 при 700 знаках до 0.79 при 3500. "
                         "Разумное значение — 1200")
    ap.add_argument("--min-ratio", type=float, default=0.0,
                    help="брак ответа короче исходника в эту долю (0 = не "
                         "проверять). Эвристика сокращений, не проверка смысла")
    ap.add_argument("--cache-dir", default=".tcache")
    ap.add_argument("--reject-cjk", choices=["auto", "on", "off"], default="auto",
                    help="брак ответов с CJK-иероглифами (auto = включено, "
                         "если целевой язык не китайский/японский/корейский)")
    ap.add_argument("--echo-check", choices=["auto", "on", "off"], default="auto",
                    help="брак ответов-эхо: модель вернула исходник вместо "
                         "перевода (auto = включено везде, кроме --mode polish, "
                         "где «вернуть как есть» — штатный ответ)")
    ap.add_argument("--manifest-sha256", default=None, help="identity supplied by parts orchestrator")
    a = ap.parse_args()
    if a.split_chars < 0 or not 0 <= a.min_ratio <= 2:
        ap.error("invalid split-chars/min-ratio")

    reject_cjk = (a.reject_cjk == "on"
                  or (a.reject_cjk == "auto"
                      and a.target_lang.strip().lower() not in CJK_TARGETS))
    reject_echo = (a.echo_check == "on"
                   or (a.echo_check == "auto" and a.mode != "polish"))

    # generic-режим держит инструкцию только у instruction-tuned моделей;
    # base/чат-модели без RLHF (напр. gemma-*-it-obliterated) галлюцинируют
    if a.mode == "generic":
        good = ("qwen", "deepseek", "gpt", "claude", "gemini", "llama",
                "mistral", "gemma-3", "gemma3")
        if not any(g in a.model.lower() for g in good):
            sys.stderr.write(
                f"?? generic-режим требует instruction-tuned модель; "
                f"'{a.model}' в белом списке не найдена — возможны "
                "галлюцинации. Проверьте на нескольких блоках или возьмите "
                "qwen3.5/deepseek.\n")

    glossary = ""
    if a.glossary and not Path(a.glossary).is_file():
        ap.error("requested glossary does not exist")
    if a.glossary and os.path.exists(a.glossary):
        glossary = Path(a.glossary).read_text(encoding="utf-8").strip()
    glossary_profile = load_profile(a.glossary_profile)
    validation_glossary = select_glossary("", glossary, glossary_profile, all_groups=True)
    os.makedirs(a.cache_dir, exist_ok=True)
    text = Path(a.src).read_bytes().decode("utf-8")
    source_hash = sha_text(text)
    blocks = split_blocks(text)
    n = len(blocks)
    out = [None] * n
    jobs, records, attempts = [], {}, {}
    n_cached = 0
    policy = ValidationPolicy(a.min_ratio, reject_cjk=reject_cjk,
                              reject_echo=reject_echo, mode=a.mode)
    config = request_config(a, glossary, glossary_profile)
    config_hash = canonical_hash(config)
    for i, block in enumerate(blocks):
        if not block.strip() or not is_translatable(block):
            out[i] = block
            continue
        fragments = plan_fragments(block, a.split_chars)
        if len(block) > a.max_chars:
            sys.stderr.write(f"[{i + 1}/{n}] source block {len(block)} chars; planned {len(fragments)} request(s)\n")
        messages = [build_messages(f["text"], a.mode, a.target_lang, select_glossary(f["text"], glossary, glossary_profile),
                                   a.think, a.source_lang) for f in fragments]
        key = request_identity(block, config, fragments, messages)
        cache = Path(a.cache_dir) / (key + ".json")
        records[i] = {"request_sha256": key, "fragments": fragments}
        if cache.exists():
            try:
                entry = json.loads(cache.read_text(encoding="utf-8"))
                pieces = entry["pieces"]
                valid = (entry.get("schema") == REQUEST_VERSION
                         and entry.get("request_sha256") == key
                         and entry.get("response_sha256") == sha_text(entry["response"])
                         and len(pieces) == len(fragments))
                if valid:
                    checked = [validate_candidate(f["text"], p, policy, validation_glossary)
                               for f, p in zip(fragments, pieces)]
                    assembled = " ".join(v.text for v in checked)
                    result = validate_candidate(block, assembled, policy, glossary)
                    valid = (all(v.ok for v in checked) and result.ok
                             and assembled == entry["response"])
                if valid:
                    out[i] = result.text
                    n_cached += 1
                    sys.stderr.write(f"[{i + 1}/{n}] cache (revalidated)\n")
                    continue
            except (ValueError, KeyError, TypeError, OSError):
                pass
            # Old/invalid entries remain as evidence, never delete the cache.
            sys.stderr.write(f"[{i + 1}/{n}] cache miss (policy/identity)\n")
        jobs.append((i, block, cache))

    lock = threading.Lock()
    done = [0]
    consec_fail = [0]
    failed = []                 # машиночитаемый след «keeping source»
    abort = threading.Event()   # сервер мёртв: стоп, а не сотни «keeping source»

    def translate_chunk(i, block):
        selected_glossary = select_glossary(block, glossary, glossary_profile)
        messages = build_messages(block, a.mode, a.target_lang, selected_glossary,
                                  a.think, a.source_lang)
        why = "unknown"
        for attempt in range(3):
            try:
                reply = call_api(a.host, a.model, messages, a.temperature, a.top_p)
                candidate = validate_candidate(block, reply, policy, glossary)
                if candidate.ok:
                    return candidate.text, "repaired" if candidate.repaired else "ok"
                why = "; ".join(candidate.reasons)
                if any("token" in r or "mask" in r for r in candidate.reasons):
                    messages = build_messages(block, a.mode, a.target_lang, selected_glossary,
                                              a.think, a.source_lang, TOKEN_RETRY_HINT)
            except (urllib.error.URLError, KeyError, TimeoutError, ValueError) as e:
                why = f"request failed: {type(e).__name__}"
                time.sleep(2)
            with lock:
                attempts.setdefault(i + 1, []).append({"attempt": attempt + 1, "reason": why})
                sys.stderr.write(f"[{i + 1}/{n}] retry {attempt + 1}: {why}\n")
        # Preserve the user's short-but-kept fix: never return a rejected reply.
        return None, why

    def work(job):
        i, block, cache = job
        if abort.is_set():
            return i, block
        fragments = records[i]["fragments"]
        pieces, ru, why = [], None, "not attempted"
        for fragment in fragments:
            if fragment["oversized"]:
                sys.stderr.write(f"[{i + 1}/{n}] indivisible request: {len(fragment['text'])} chars\n")
            piece, why = translate_chunk(i, fragment["text"])
            if piece is None:
                break
            pieces.append(piece)
        else:
            assembled = validate_candidate(block, " ".join(pieces), policy, glossary)
            if assembled.ok:
                ru = assembled.text
            else:
                why = "; ".join(assembled.reasons)
        with lock:
            done[0] += 1
            if ru is None:
                consec_fail[0] += 1
                failed.append({"index": i + 1, "reason": why})
                sys.stderr.write(f"[{done[0]}/{n}] FAILED block {i + 1} ({why}), keeping source\n")
                if consec_fail[0] >= 10:
                    abort.set()
            else:
                consec_fail[0] = 0
                sys.stderr.write(f"[{done[0]}/{n}] ok\n")
        if ru is not None:
            write_json(cache, {"schema": REQUEST_VERSION,
                              "request_sha256": records[i]["request_sha256"],
                              "config_sha256": config_hash, "pieces": pieces,
                              "response": ru, "response_sha256": sha_text(ru),
                              "validator": VALIDATOR_VERSION, "policy": asdict(policy)})
        return i, (ru if ru is not None else block)

    workers = max(1, a.parallel)
    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for i, res in ex.map(work, jobs):
                out[i] = res

    # машиночитаемый итог стадии: раньше единственным следом «keeping source»
    # была строка в stderr, которую никто не читал, — и английские абзацы
    # молча уезжали в готовую книгу
    failed.sort(key=lambda f: f["index"])
    report_path = Path(a.dst + ".report.json")
    if sha_file(a.src) != source_hash:
        abort.set()
        failed.append({"index": 0, "reason": "source changed during translation"})
    result_text = None
    if not abort.is_set():
        result_text = "\n\n".join(re.sub(r"\n\s*\n+", "\n", b) for b in out)
        atomic_text(a.dst, result_text)
    write_json(report_path, {
        "schema": 1, "stage": "raw_mt", "run_id": __import__("uuid").uuid4().hex,
        "status": "failed" if failed or abort.is_set() else "passed",
        "source_sha256": source_hash,
        "output_sha256": sha_text(result_text) if result_text is not None else None,
        "manifest_sha256": a.manifest_sha256,
        "request_config_sha256": config_hash, "request_config": config,
        "validator": VALIDATOR_VERSION, "policy": asdict(policy),
        "src": a.src, "dst": a.dst, "mode": a.mode, "model": a.model,
        "blocks_total": n, "from_cache": n_cached,
        "translated": max(0, done[0] - len(failed)),
        "kept_source": len(failed), "failed_blocks": failed,
        "aborted": abort.is_set(), "attempts": attempts,
        "requests": {str(i + 1): row for i, row in records.items()},
        "semantic_review": "not_run"})
    if abort.is_set():
        sys.stderr.write("!! repeated failures or changed input; output not published; cache retained\n")
        sys.exit(3)

    if failed:
        sys.stderr.write(
            f"!! непереведённых блоков: {len(failed)} из {n} — оставлены "
            f"исходником; список: {report_path.name}; код возврата 4. "
            "Перезапуск той же команды повторит только их (провалы не "
            "кэшируются).\n")
        # эхо на длинной сессии: hy-mt2-7b после ~350 блоков начинает
        # возвращать исходник; лечит разбиение на части по ~300 блоков
        echoes = sum(1 for f in failed if f.get("reason") == "echo")
        if echoes >= 20 and n > 350:
            sys.stderr.write(
                f"   из них {echoes} — echo (модель вернула исходник). На "
                "длинных книгах hy-mt2-7b «устаёт» после ~350 блоков: разбейте "
                "masked-файл на части по ~300 блоков и переведите каждую "
                "отдельным --cache-dir (см. README, «Длинные книги»).\n")
        sys.exit(4)
    print(f"translated {n} blocks -> {a.dst}  (report: {report_path.name})")


if __name__ == "__main__":
    main()
