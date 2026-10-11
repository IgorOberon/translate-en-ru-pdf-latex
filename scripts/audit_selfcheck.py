#!/usr/bin/env python3
"""Consistency self-audit of a built book: md + body.tex + main.pdf.

Checks (diagnosis only — the tool never modifies anything):
  a) equation/statement numbers: the union of \\tag{N} inside display math
     and trailing \\hfill(N), collected in document order, segmented by
     chapters ('# ' headings). Within a chapter a drop in value starts a new
     numbering run (the book restarts numbering per section); a jump inside
     a run is reported as missing numbers.
  b) figures: caption numbers (image + «Рисунок [N]») vs mentions of
     «Рисунок [N]» / bare «[N]» in prose, per chapter.
  c) sections: arabic numbering breaks inside '## ' headings per chapter
     (the recurring '## 1 Введение' in every chapter follows the original's
     per-section numbering — recorded as the norm, not a defect).
  d) PDF text hygiene: leftover mask tokens M######, «⟦», literal LaTeX
     leaks (\\real{, pandocbounded, \\tag, \\hfill), «[рисунок не найден]»;
     «??» is a WARNING with ±60-char contexts (this book has authentic
     author's «???»).

Usage:
  python scripts/audit_selfcheck.py <book.md> <body.tex> <main.pdf>
                                    [--report audit_report.md]
"""
import argparse
import re
import sys
from pathlib import Path

print(">> audit_selfcheck.py v1", flush=True)

NUM_RE = re.compile(r"\\tag\{(\d+(?:\.\d+)?)\}|\\hfill\((\d+(?:\.\d+)?)\)")
CAPTION_NUM_RE = re.compile(r"Рисунок \[(\d+[ab]?)\]")
BARE_REF_RE = re.compile(r"\[(\d{1,2}[ab]?)\]")


def fmt_missing(a, b):
    """Human range of missing numbers a..b-1: short list or 'a–b (n шт.)'."""
    ks = list(range(a, b))
    if len(ks) <= 6:
        return ", ".join(f"({k})" for k in ks)
    return f"({ks[0]})–({ks[-1]}) ({len(ks)} шт.)"


def split_chapters(md_lines):
    """Yield (title, lines, start_line) per '# ' chapter (1-based start);
    front matter goes to chapter 0."""
    chapters, cur, title, start = [], [], "(до первой главы)", 1
    for i, ln in enumerate(md_lines, start=1):
        if ln.startswith("# ") and not ln.startswith("## "):
            chapters.append((title, cur, start))
            title, cur, start = ln[2:].strip(), [], i
        else:
            cur.append(ln)
    chapters.append((title, cur, start))
    return chapters


# Приложение ответов ВЫБОРОЧНО по построению: «Ответы к нечётным задачам»
# приводит 1, 3, 7, 12 — и проверка нумерации честно рапортует о «пропусках»,
# которых нет. На NFCM это была самая шумная ложная тревога аудита.
ANSWER_SECTION_RE = re.compile(
    r"ответ|указани|решени|подсказк|answers?\b|hints?\b|solutions?\b",
    re.IGNORECASE)


def is_answer_section(title):
    return bool(ANSWER_SECTION_RE.search(title or ""))


def audit_eq_numbers(md_text):
    """Per chapter: numbering runs with gaps reported."""
    findings = []
    total = 0
    for ci, (title, lines, start) in enumerate(split_chapters(md_text.splitlines())):
        if is_answer_section(title):
            findings.append(
                f"гл.{ci} «{title[:40]}»: раздел ответов/указаний — "
                "нумерация выборочна по построению, пропуски не считаются")
            continue
        nums = []
        for k, ln in enumerate(lines):
            for m in NUM_RE.finditer(ln):
                nums.append((m.group(1) or m.group(2), start + k))
        total += len(nums)
        prev = None
        for raw, lineno in nums:
            major = int(raw.split(".")[0])
            if prev is not None and major > prev + 1:
                findings.append(
                    f"гл.{ci} «{title[:40]}»: есть ({prev}),({raw}) — нет "
                    + fmt_missing(prev + 1, major)
                    + f" [md строка ~{lineno}]")
            prev = major  # a drop in value simply starts a new numbering run
    return findings, total


def audit_figures(md_text):
    findings = []
    caps_total, mentions_total = 0, 0
    for ci, (title, lines, _start) in enumerate(split_chapters(md_text.splitlines())):
        captions, mentions = set(), set()
        for i, ln in enumerate(lines):
            s = ln.strip()
            caption_here = None
            if s.startswith("![]("):
                # caption on the same line after a hard break or next lines
                tail = s.split(")", 1)[1] if ")" in s else ""
                m = CAPTION_NUM_RE.search(tail)
                if not m:
                    for j in (1, 2):
                        if i + j < len(lines) and lines[i + j].strip():
                            m = CAPTION_NUM_RE.match(lines[i + j].strip())
                            break
                if m:
                    caption_here = m.group(1)
                    captions.add(caption_here)
            for m in CAPTION_NUM_RE.finditer(ln):
                if m.group(1) != caption_here:
                    mentions.add(m.group(1))
            if not s.startswith("![]("):
                # bare figure refs in prose: «... показано в [2a]»
                for m in BARE_REF_RE.finditer(ln):
                    if m.group(1) != caption_here:
                        mentions.add(m.group(1))
        caps_total += len(captions)
        mentions_total += len(mentions)
        # prose refers to panels of a figure as [11a]/[11b] while the caption
        # is «Рисунок [11]» — compare by the numeric base
        base = lambda s: re.sub(r"[ab]$", "", s)
        cap_bases = {base(c) for c in captions}
        men_bases = {base(m) for m in mentions}
        ghost = sorted(men_bases - cap_bases, key=str)
        orphan = sorted(cap_bases - men_bases, key=str)
        if ghost:
            findings.append(
                f"гл.{ci} «{title[:40]}»: упомянуты, но нет блока фигуры: "
                + ", ".join(f"[{g}]" for g in ghost))
        if orphan:
            findings.append(
                f"гл.{ci} «{title[:40]}»: фигуры без упоминания в тексте: "
                + ", ".join(f"[{o}]" for o in orphan))
    return findings, caps_total, mentions_total


def audit_sections(md_text):
    findings = []
    norm_note = ("«## 1 Введение» повторяется в главах — это ВЕРНО оригиналу "
                 "(нумерация подразделов начинается заново в каждом разделе)")
    for ci, (title, lines, _start) in enumerate(split_chapters(md_text.splitlines())):
        prev = None
        for ln in lines:
            m = re.match(r"##\s+(\d{1,3})\s+\S", ln)
            if not m:
                if re.match(r"##\s+[IVXLC]+\s", ln):
                    prev = None  # a new roman section restarts arabic numbering
                continue
            n = int(m.group(1))
            if prev is not None and n > prev + 1:
                findings.append(
                    f"гл.{ci} «{title[:40]}»: подразделы {prev} -> {n} "
                    f"(нет {fmt_missing(prev + 1, n)})")
            prev = n  # a drop restarts the per-section numbering
    return findings, norm_note


def audit_dup_headings(md_text, min_len=8):
    """Повторы одинаковых заголовков внутри одной главы — след дубля
    извлечения (гибридный бэкенд MinerU обрабатывает документ окнами и на
    стыке способен выдать одни и те же страницы дважды). Короткие заголовки
    («Пример», «Итоги») законно повторяются — не судим."""
    findings = []
    for ci, (title, lines, _start) in enumerate(split_chapters(md_text.splitlines())):
        seen = {}
        for ln in lines:
            m = re.match(r"\s{0,3}#{2,6}\s*(.+?)\s*$", ln)
            if not m:
                continue
            h = " ".join(m.group(1).split()).casefold()
            if len(h) >= min_len:
                seen[h] = seen.get(h, 0) + 1
        for h, n in seen.items():
            if n >= 2:
                findings.append(f"гл.{ci} «{title[:40]}»: заголовок «{h[:50]}» "
                                f"повторён x{n} — возможен дубль извлечения")
    return findings


def audit_pdf(pdf_path):
    import fitz
    doc = fitz.open(str(pdf_path))
    text = "\n".join(doc[i].get_text() for i in range(len(doc)))
    doc.close()
    hard = {}
    hard["mask tokens M######"] = len(re.findall(r"M\d{6}", text))
    hard["«⟦»"] = text.count("⟦")
    hard["literal \\real{"] = text.count("\\real{")
    hard["literal pandocbounded"] = text.count("pandocbounded")
    hard["literal \\tag"] = text.count("\\tag")
    hard["literal \\hfill"] = text.count("\\hfill")
    hard["[рисунок не найден]"] = text.count("[рисунок не найден]")
    contexts, last_end = [], -1000
    for m in re.finditer(r"\?\?+", text):
        if m.start() - last_end < 80:   # same physical site (???…)
            last_end = m.end()
            continue
        last_end = m.end()
        a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
        contexts.append(" ".join(text[a:b].split()))
    return hard, contexts


# --------------------------------------------------------------------------
# Прескан body.tex на конструкцию, которая роняет XeTeX НАСМЕРТЬ.
#
# «! Internal error: bad native font flag in 'map_char_to_glyph'»: rc=3, PDF
# не пишется, и — главное — в main.log ошибки НЕТ, лог просто обрывается на
# текущей странице. Найти место можно только бисектом по body.tex; на
# «New Foundations for Classical Mechanics» это стоило часов. Триггер —
# ТЕКСТОВЫЙ переключатель шрифта поверх МАТЕМАТИЧЕСКОГО акцента:
# «{\bf \dot{\theta}}^2», «\mathbf{\bar{\alpha}}», «\mathsf{\hat{\cal A}}».
#
# Проверка стоит секунду и делается ДО сборки. Правило починки живёт в
# clean_markdown.py (repair-math); сюда попадает то, что мимо него прошло —
# например правки, внесённые в body.tex руками.
FONT_SWITCH_ALT = "|".join((
    "mathbf", "mathsf", "mathtt", "mathit", "mathrm", "textrm", "textbf",
    "texttt", "emph", "pmb", "bf", "rm", "it", "sf", "tt", "sc"))
MATH_ACCENT_ALT = "|".join((
    "ddot", "dot", "hat", "tilde", "bar", "vec", "check", "breve", "acute",
    "grave"))
SWITCH_ACCENT_RE = re.compile(
    r"\\(" + FONT_SWITCH_ALT + r")(?![A-Za-z])\s*\{?\s*"
    r"\\(?:" + MATH_ACCENT_ALT + r")(?![A-Za-z])")

# Рвут только НАСТОЯЩИЕ переключатели математического шрифта. \pmb рисует
# жирность наложением и не трогает шрифт вовсе — не роняет даже над строчной
# греческой; \emph и \text* работают в текстовом режиме и дают другую ошибку.
# Проверено микротестами: \mathit/\mathsf/\mathtt/\mathrm/\mathbf над
# \alpha — краш; \pmb над тем же \varepsilon — собирается.
CRASHING_SWITCHES = {"mathbf", "mathsf", "mathtt", "mathit", "mathrm",
                     "bf", "rm", "it", "sf", "tt", "sc"}

# Роняет НЕ всякое сочетание, и это выяснено матрицей микротестов на боевой
# преамбуле: падает акцент над глифом, которого в затребованном шрифте нет.
#   \mathbf{\bar{\alpha}}  \mathrm{\bar{\alpha}}  \mathbf{\dot{\cal A}}  КРАШ
#   \mathbf{\bar{x}}  \mathbf{\hat{\Gamma}}  \pmb{\hat{v}}              ok
# Поэтому находки делятся надвое: доказанно опасные валят приёмку, прочие
# идут предупреждением. Иначе гейт кричал бы на местах, которые в готовой
# книге спокойно собираются, и ему перестали бы верить.
LOWER_GREEK = ("alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta"
               "|vartheta|iota|kappa|lambda|mu|nu|xi|pi|varpi|rho|varrho"
               "|sigma|varsigma|tau|upsilon|phi|varphi|chi|psi|omega")
RISKY_ARG_RE = re.compile(
    r"\\(?:" + LOWER_GREEK + r")(?![A-Za-z])"      # строчная греческая
    r"|\\(?:cal|mathcal|mathscr|mathfrak|mathbb)(?![A-Za-z])")


def _accent_arg(line, at):
    """Аргумент акцента, начиная от позиции его команды. Балансно."""
    i = line.find("{", at)
    if i == -1:
        return ""
    depth = 0
    for j in range(i, len(line)):
        if line[j] == "{":
            depth += 1
        elif line[j] == "}":
            depth -= 1
            if depth == 0:
                return line[i + 1:j]
    return line[i + 1:]


def audit_switch_accent(body_text, limit=20):
    """-> (опасные, прочие, всего). Опасные валят приёмку, прочие — нет."""
    risky, other = [], []
    for i, line in enumerate(body_text.split("\n"), start=1):
        for m in SWITCH_ACCENT_RE.finditer(line):
            a, b = max(0, m.start() - 30), min(len(line), m.end() + 40)
            note = f"строка {i}: …{line[a:b].strip()}…"
            arg = _accent_arg(line, m.end())
            bad = (m.group(1) in CRASHING_SWITCHES
                   and RISKY_ARG_RE.search(arg))
            (risky if bad else other).append(note)
    return risky[:limit], other[:limit], len(risky) + len(other)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("body_tex")
    ap.add_argument("pdf")
    ap.add_argument("--report", default="audit_report.md")
    a = ap.parse_args()

    md_text = Path(a.md).read_text(encoding="utf-8")
    body = Path(a.body_tex).read_text(encoding="utf-8", errors="replace")

    eq_findings, eq_total = audit_eq_numbers(md_text)
    fig_findings, caps_n, men_n = audit_figures(md_text)
    sec_findings, norm_note = audit_sections(md_text)

    lines = ["# Самоаудит согласованности", ""]
    lines += [f"- источник: {a.md}",
              f"- body.tex: \\tag={body.count(chr(92) + 'tag{')}, "
              f"\\hfill={body.count(chr(92) + 'hfill(')}, "
              f"фигурных блоков \\FigWithCaption={body.count(chr(92) + 'FigWithCaption')}",
              ""]
    lines += ["## (a) Номера формул/утверждений",
              f"всего номеров: {eq_total}; разрывов: {len(eq_findings)}", ""]
    lines += [f"- {f}" for f in eq_findings] or ["- разрывов нет"]
    lines += ["", "## (b) Фигуры",
              f"подписей: {caps_n}; глав с несостыковками: {len(fig_findings)}", ""]
    lines += [f"- {f}" for f in fig_findings] or ["- несостыковок нет"]
    lines += ["", "## (c) Разделы",
              f"- норма: {norm_note}",
              f"разрывов: {len(sec_findings)}", ""]
    lines += [f"- {f}" for f in sec_findings] or ["- разрывов нет"]

    dup_findings = audit_dup_headings(md_text)
    lines += ["", "## (e) Повторы заголовков (дубли извлечения)",
              f"повторов: {len(dup_findings)}", ""]
    lines += [f"- {f}" for f in dup_findings] or ["- повторов нет"]

    sw_risky, sw_other, sw_total = audit_switch_accent(body)
    lines += ["", "## (f) Переключатель шрифта поверх мат. акцента",
              "Роняет XeTeX: «bad native font flag in map_char_to_glyph», "
              "rc=3, PDF не пишется, и в main.log ошибки НЕТ. Падает не "
              "всякое сочетание, а акцент над глифом, которого в "
              "затребованном шрифте нет: строчная греческая, каллиграфия. "
              "Лечение — clean_markdown.py (repair-math) или вручную "
              "\\boldsymbol{\\<акцент>{…}}.",
              f"всего: {sw_total}, из них опасных: {len(sw_risky)}", ""]
    lines += [f"- ОПАСНО {f}" for f in sw_risky]
    lines += [f"- (соберётся) {f}" for f in sw_other]
    if not sw_total:
        lines.append("- чисто")

    pdf_ok = True
    try:
        hard, contexts = audit_pdf(a.pdf)
        lines += ["", "## (d) Гигиена PDF-текста", ""]
        for k, v in hard.items():
            mark = "OK" if v == 0 else "!!"
            lines.append(f"- {mark} {k}: {v}")
            if v and k != "«??»":
                pdf_ok = False
        lines += ["", f"### WARNING: «??» — {len(contexts)} контекст(ов) "
                      "(в этой книге есть аутентичные «???» автора)", ""]
        lines += [f"- …{c}…" for c in contexts[:20]]
    except ImportError:
        lines += ["", "## (d) PDF: PyMuPDF не установлен — раздел пропущен"]

    Path(a.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"?? АУДИТ: {len(eq_findings)} разрывов формул, "
          f"{len(fig_findings)} несостыковок фигур — {a.report}")
    if sw_risky:
        # доказанно фатально — говорим громко и валим приёмку
        print(f"!! {len(sw_risky)} мест «переключатель шрифта + акцент над "
              f"строчной греческой/каллиграфией» в {a.body_tex} — XeTeX "
              f"упадёт с «bad native font flag» и НИЧЕГО не напишет в "
              f"main.log. Первое: {sw_risky[0]}")
        pdf_ok = False
    elif sw_other:
        print(f"?? {len(sw_other)} мест «переключатель + акцент» — по замерам "
              f"такие собираются, но лучше прогнать clean_markdown.py")
    sys.exit(0 if pdf_ok else 1)


if __name__ == "__main__":
    main()
