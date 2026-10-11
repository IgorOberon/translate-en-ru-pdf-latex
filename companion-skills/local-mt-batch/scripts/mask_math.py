#!/usr/bin/env python3
"""Mask / unmask math, LaTeX commands, code and URLs in a markdown file.

Masking replaces each protected span with a unique placeholder ``⟦M######⟧`` and
records the mapping in a JSON sidecar, so a translator (LLM) only ever sees plain
prose. Unmasking restores every span verbatim. This guarantees formulas and code
survive translation even if the model is sloppy.

Usage:
  mask_math.py mask   <in.md>  <out.md>  <map.json>
  mask_math.py unmask <in.md>  <out.md>  <map.json>
"""
import json
import re
import sys

PLACEHOLDER = "\u27e6M{:06d}\u27e7"            # e.g. ⟦M000001⟧
PLACEHOLDER_RE = re.compile(r"\u27e6M\d{6}\u27e7")

# Ordered: mask the most specific / outermost spans first. Once a span becomes a
# placeholder, later patterns cannot match inside it (placeholders contain no
# characters that the patterns below look for).
PATTERNS = [
    ("fenced_code",    re.compile(r"```.*?```", re.DOTALL)),
    ("display_dollar", re.compile(r"\$\$.*?\$\$", re.DOTALL)),
    ("display_brack",  re.compile(r"\\\[.*?\\\]", re.DOTALL)),
    ("environment",    re.compile(r"\\begin\{([^}]*)\}.*?\\end\{\1\}", re.DOTALL)),
    ("inline_paren",   re.compile(r"\\\(.*?\\\)", re.DOTALL)),
    # inline $...$ : not preceded by a backslash, at least one char, no bare $ inside
    ("inline_dollar",  re.compile(r"(?<!\\)\$(?:\\.|[^$\\])+?\$")),
    ("inline_code",    re.compile(r"`[^`]+`")),
    ("ref_cmd",        re.compile(
        r"\\(?:ref|eqref|autoref|cref|Cref|vref|pageref|nameref|label"
        r"|cite|citep|citet|citeauthor|citeyear|citealp)\b(?:\[[^\]]*\])?\{[^}]*\}")),
    ("md_link_url",    re.compile(r"(?<=\]\()[^)\s]+(?=\))")),
    ("autolink",       re.compile(r"<https?://[^>\s]+>")),
    ("bare_url",       re.compile(r"https?://[^\s)]+")),
]


def mask(text):
    mapping = {}
    counter = [0]

    def make(match):
        key = PLACEHOLDER.format(counter[0])
        counter[0] += 1
        mapping[key] = match.group(0)
        return key

    for _name, rx in PATTERNS:
        text = rx.sub(make, text)
    return text, mapping


def unmask(text, mapping):
    # Restore repeatedly in case a restored span itself contains a placeholder
    # (should not happen, but it is cheap to be safe).
    for _ in range(3):
        if not PLACEHOLDER_RE.search(text):
            break
        text = PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
    return text


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in ("mask", "unmask"):
        print(__doc__)
        sys.exit(1)
    op, src, dst, mapf = sys.argv[1:5]
    data = open(src, encoding="utf-8").read()

    if op == "mask":
        out, mapping = mask(data)
        with open(mapf, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=0)
        open(dst, "w", encoding="utf-8").write(out)
        print(f"masked {len(mapping)} spans -> {dst}  (map: {mapf})")
    else:
        mapping = json.load(open(mapf, encoding="utf-8"))
        out = unmask(data, mapping)
        left = len(PLACEHOLDER_RE.findall(out))
        open(dst, "w", encoding="utf-8").write(out)
        msg = f"unmasked -> {dst}"
        if left:
            msg += f"  (WARNING: {left} placeholder(s) left unresolved)"
        print(msg)


if __name__ == "__main__":
    main()
