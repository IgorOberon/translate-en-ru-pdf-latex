#!/usr/bin/env python3
"""Mask / unmask math, LaTeX commands, code and URLs in a markdown file.

Masking replaces each protected span with a unique placeholder ``⟦M######⟧`` and
records the mapping in a JSON sidecar, so a translator (LLM) only ever sees plain
prose. Unmasking restores every span verbatim. This guarantees formulas and code
survive translation even if the model is sloppy.

Unmasking is two-pass: an exact pass restores intact ``⟦M######⟧`` tokens, a
recovery pass then repairs tokens whose brackets the model damaged (e.g.
``⟨M001705⟩``, ``‹M003223›``, ``▦M009806◦``, ``⟦M006576⟋``) — any ``M######``
whose id exists in the map is restored together with its broken bracket
neighbours. Ids absent from the map are left untouched and reported.

Usage:
  mask_math.py mask   <in.md>  <out.md>  <map.json>
  mask_math.py unmask <in.md>  <out.md>  <map.json>
"""
import json
import re
import sys

print(">> mask_math.py v2 (recovery unmask)", flush=True)

PLACEHOLDER = "\u27e6M{:06d}\u27e7"            # e.g. ⟦M000001⟧
PLACEHOLDER_RE = re.compile(r"\u27e6M\d{6}\u27e7")
# recovery: M###### with at most one broken bracket char on each side.
# Neighbours must be non-word AND non-space: eating spaces would glue the
# restored span to surrounding words.
DAMAGED_RE = re.compile(r"[^\w\s]?M(\d{6})[^\w\s]?")

# Ordered: mask the most specific / outermost spans first. Once a span becomes a
# placeholder, later patterns cannot match inside it (placeholders contain no
# characters that the patterns below look for).
PATTERNS = [
    # маркеры плашек rescue_plaques.py — до environment, чтобы текст плашки
    # между ними оставался открытым для перевода
    ("plaque_marker",  re.compile(r"\\plaque(?:begin|end)\b")),
    ("fenced_code",    re.compile(r"```.*?```", re.DOTALL)),
    ("display_dollar", re.compile(r"\$\$.*?\$\$", re.DOTALL)),
    ("display_brack",  re.compile(r"\\\[.*?\\\]", re.DOTALL)),
    ("environment",    re.compile(r"\\begin\{([^}]*)\}.*?\\end\{\1\}", re.DOTALL)),
    ("inline_paren",   re.compile(r"\\\(.*?\\\)", re.DOTALL)),
    # inline $...$ : not preceded by a backslash, at least one char, no bare $ inside
    ("inline_dollar",  re.compile(r"(?<!\\)\$(?:\\.|[^$\\])+?\$")),
    ("inline_code",    re.compile(r"`[^`]+`")),
    # Keep note IDs and the definition colon immutable; translate the body.
    ("footnote_marker", re.compile(r"\[\^[^\]\s]+\]:?")),
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
    """Two-pass restore; returns (text, exact_n, repaired_n, unresolved_n)."""
    stats = {"exact": 0, "repaired": 0}

    def exact_sub(m):
        if m.group(0) in mapping:
            stats["exact"] += 1
            return mapping[m.group(0)]
        return m.group(0)

    # Restore repeatedly in case a restored span itself contains a placeholder
    # (should not happen, but it is cheap to be safe).
    for _ in range(3):
        if not PLACEHOLDER_RE.search(text):
            break
        text = PLACEHOLDER_RE.sub(exact_sub, text)

    def repair_sub(m):
        key = PLACEHOLDER.format(int(m.group(1)))
        if key in mapping:
            stats["repaired"] += 1
            return mapping[key]
        return m.group(0)  # unknown id: leave as-is, count as unresolved

    text = DAMAGED_RE.sub(repair_sub, text)
    unresolved = len(re.findall(r"M\d{6}", text))
    return text, stats["exact"], stats["repaired"], unresolved


CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")


def _dollar_positions(line):
    """Позиции НЕэкранированных «$» в строке."""
    out, i = [], 0
    while i < len(line):
        if line[i] == "\\":
            i += 2                       # \$ и вообще любая escape-пара
            continue
        if line[i] == "$":
            out.append(i)
        i += 1
    return out


def tighten_inline_math(text):
    """Убрать краевые пробелы внутри «$ … $». -> (текст, число строк).

    pandoc с tex_math_dollars требует: после открывающего «$» не пробел и
    перед закрывающим не пробел. Иначе спан считается литеральным текстом,
    доллары экранируются в «\\$», формула разваливается, и дальше идёт
    каскад вплоть до «Cyrillic in cmmi10». Извлечение MinerU ставит пробелы
    внутрь постоянно: «$ \\mathbf { a } $».

    Два предохранителя, оба оплачены:

    * КИРИЛЛИЦА ВНУТРИ — спан не трогаем. Пара «$…$» бывает ложной: первая
      формула закрылась, вторая открылась, а между ними проза. Сжать такую
      «пару» значит вклеить русский текст внутрь математики (реальный
      случай: «$представляет собой$»).
    * Пары считаются ПО ПОРЯДКУ, а не поиском ближайшего «$». Эталонная
      реализация брала следующий доллар от текущей позиции и на строке вида
      «a $x$ b $y$ c» принимала « b » за содержимое формулы: латинская проза
      кириллическим стражем не защищена, и текст уезжал внутрь математики.
    """
    out_lines, n = [], 0
    for line in text.split("\n"):
        if "$$" in line or line.lstrip().startswith("!["):
            out_lines.append(line)
            continue
        pos = _dollar_positions(line)
        if len(pos) < 2:
            out_lines.append(line)
            continue
        pieces, prev, changed = [], 0, False
        for a, b in zip(pos[0::2], pos[1::2]):
            inner = line[a + 1:b]
            stripped = inner.strip()
            if (inner == stripped or not stripped
                    or CYRILLIC_RE.search(inner)):
                continue
            pieces.append(line[prev:a] + "$" + stripped + "$")
            prev = b + 1
            changed = True
        if not changed:
            out_lines.append(line)
            continue
        pieces.append(line[prev:])
        out_lines.append("".join(pieces))
        n += 1
    return "\n".join(out_lines), n


def main():
    argv = [a for a in sys.argv[1:] if a != "--no-tighten"]
    tighten = "--no-tighten" not in sys.argv
    if len(argv) != 4 or argv[0] not in ("mask", "unmask"):
        print(__doc__)
        sys.exit(1)
    op, src, dst, mapf = argv
    data = open(src, encoding="utf-8").read()

    if op == "mask":
        out, mapping = mask(data)
        with open(mapf, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=0)
        open(dst, "w", encoding="utf-8").write(out)
        print(f"masked {len(mapping)} spans -> {dst}  (map: {mapf})")
    else:
        mapping = json.load(open(mapf, encoding="utf-8"))
        out, exact_n, repaired_n, unresolved = unmask(data, mapping)
        n_tight = 0
        if tighten:
            out, n_tight = tighten_inline_math(out)
        open(dst, "w", encoding="utf-8").write(out)
        msg = (f"unmasked -> {dst}  (restored exact: {exact_n}, "
               f"repaired damaged: {repaired_n}, unresolved: {unresolved}, "
               f"tightened $-spans on {n_tight} line(s))")
        if unresolved:
            msg += f"  (WARNING: {unresolved} placeholder(s) left unresolved)"
        print(msg)


if __name__ == "__main__":
    main()
