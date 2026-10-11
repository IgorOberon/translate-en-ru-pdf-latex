#!/usr/bin/env python3
"""Auto-build a translation glossary from extracted markdown.

Finds recurring proper names and multi-word title-case terms in the book,
translates each ONE time with the local model, and writes ready-to-use
'english => русский' lines for translate.py / translate_book.py.

Review the result before the long run: delete lines you don't want and fix
renderings you dislike. Lowercase technical terms (e.g. "gradient descent")
are not detected by the heuristic — add those by hand if needed.

Usage:
  python scripts/make_glossary.py extract/book/book.md glossary.md \
      --host http://localhost:1234 --model hy-mt2-7b
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

STOP = set("""The This That These Those There Then Thus When Where While Which Who Whom Whose What Why How
If In On At As An A And But Or Nor For So Yet To Of By With From Into Onto Over Under About Above Below
After Before During Between Through Without Within Against Across Along Around Behind Beyond
We You They He She It Its His Her Our Your Their Them Him Us Me My Mine I
Chapter Section Figure Table Theorem Lemma Proof Corollary Definition Proposition Example Exercise
Equation Remark Notation Note Notes Problem Problems Solution Solutions Algorithm Appendix
Let Suppose Assume Consider Given Since Because Therefore Hence However Moreover Furthermore
Finally First Second Third Next Now Here Also Both Each Every All Some Any No Not New Old
One Two Three Four Five Part Page Pages Index Preface Contents Introduction Conclusion Summary
References Bibliography Acknowledgments Acknowledgements Abstract Editor Edition Press University
January February March April May June July August September October November December
Recall Observe Indeed Similarly Clearly Obviously Unfortunately Fortunately Alternatively
Equivalently Conversely Namely Otherwise Nevertheless Nonetheless Meanwhile Instead Rather
Yes Only Such Even Most More Many Much Very Just Like Unlike
Show Prove Deduce Check Verify Explain Find Use Write Draw Give Compute Calculate
Sketch Confirm Conclude Apply Try Solve Determine Describe Answer Express Evaluate
Derive Justify Argue Repeat Combine Substitute Differentiate Integrate Multiply Divide
General Writing Reading Looking Starting Using Taking Making Doing Working Referring
Returning Beginning Ending Comparing Combining Applying Sec""".split())

CONNECT = {"of", "the", "von", "van", "de", "der", "den", "la", "le",
           "di", "da", "del", "dos", "du", "and"}

from endpoint_policy import model_opener
OPENER = model_opener()

CAPWORD = re.compile(r"[A-Z][a-z\u00C0-\u024F][\w'\u2019-]{1,}")
MULTI = re.compile(
    r"\b[A-Z][a-z\u00C0-\u024F][\w'\u2019-]*"
    r"(?:[ \t]+(?:(?:of|the|von|van|de|der|den|la|le|di|da|del|dos|du|and)[ \t]+)?"
    r"[A-Z][a-z\u00C0-\u024F][\w'\u2019-]*)+\b")


def _load_mask_module():
    spec = importlib.util.spec_from_file_location(
        "mask_math", Path(__file__).with_name("mask_math.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_text(md_text):
    """Strip math/code/links via the masking machinery, drop the placeholders."""
    mm = _load_mask_module()
    masked, _mapping = mm.mask(md_text)
    return mm.PLACEHOLDER_RE.sub(" ", masked)


def sentence_start(text, pos):
    i = pos - 1
    while i >= 0 and text[i] in " \t\"'\u00ab\u201c(*_#>-":
        i -= 1
    return i < 0 or text[i] in ".!?\n:"


def collect_candidates(text, min_count):
    multi = collections.Counter()
    covered = []
    for m in MULTI.finditer(text):
        words = re.sub(r"\s+", " ", m.group(0)).split()
        while words and (words[0] in STOP or words[0].lower() in CONNECT):
            words = words[1:]
        while words and words[-1].lower() in CONNECT:
            words = words[:-1]
        if len(words) >= 2:
            multi[" ".join(words)] += 1
            covered.append((m.start(), m.end()))

    total = collections.Counter()
    nonstart = collections.Counter()
    for m in CAPWORD.finditer(text):
        w = m.group(0)
        if w in STOP or len(w) < 4:
            continue
        total[w] += 1
        if not sentence_start(text, m.start()):
            nonstart[w] += 1

    terms = {t: c for t, c in multi.items() if c >= max(2, min_count - 1)}
    for w, c in nonstart.items():
        if c >= min_count:
            terms[w] = max(terms.get(w, 0), total[w])
    return sorted(terms.items(), key=lambda kv: -kv[1])


def translate_term(term, host, model, target_lang):
    prompt = (f"Translate the following segment into {target_lang}, "
              "without additional explanation. If it is a person's name, "
              "transliterate it according to standard practice; never translate "
              f"a surname's literal meaning.\n\n{term}")
    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "stream": False, "temperature": 0.3, "top_p": 0.6,
               "max_tokens": 100}
    # облачные OpenAI-совместимые эндпоинты: url и ключ как в translate.py
    from translate import api_url
    token = os.environ.get("LLM_API_KEY") or "local"
    req = urllib.request.Request(
        api_url(host),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    with OPENER.open(req, timeout=120) as r:
        text = json.load(r)["choices"][0]["message"]["content"]
    text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    line = text.strip().splitlines()[0].strip().strip('"\u00ab\u00bb')
    return line.rstrip(".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown")
    ap.add_argument("out")
    ap.add_argument("--host", default="http://localhost:1234")
    ap.add_argument("--model", default="hy-mt2-7b")
    ap.add_argument("--target-lang", default="Russian")
    ap.add_argument("--min-count", type=int, default=3,
                    help="keep single names seen at least this many times mid-sentence")
    ap.add_argument("--max-terms", type=int, default=60)
    a = ap.parse_args()

    text = clean_text(open(a.markdown, encoding="utf-8").read())
    cands = collect_candidates(text, a.min_count)[: a.max_terms]
    if not cands:
        print("no recurring names/terms found; write glossary.md by hand")
        sys.exit(0)
    print(f"{len(cands)} candidate terms; translating each once...")

    lines = []
    for i, (term, cnt) in enumerate(cands, 1):
        ru = None
        for attempt in range(3):
            try:
                ru = translate_term(term, a.host, a.model, a.target_lang)
                break
            except (urllib.error.URLError, urllib.error.HTTPError,
                    KeyError, TimeoutError, json.JSONDecodeError) as e:
                sys.stderr.write(f"[{i}/{len(cands)}] retry {attempt + 1}: {e}\n")
                time.sleep(2)
        if not ru:
            sys.stderr.write(f"[{i}/{len(cands)}] SKIP {term}\n")
            continue
        lines.append(f"{term} => {ru}")
        print(f"[{i}/{len(cands)}] ({cnt}x) {term} => {ru}")

    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {len(lines)} lines -> {a.out}")
    print("REVIEW IT: delete unwanted lines, fix renderings. "
          "Changing the glossary resets the translation cache.")


if __name__ == "__main__":
    main()
