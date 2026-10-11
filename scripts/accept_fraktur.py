#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Приёмка фрактурного маршрута: ocr_fraktur -> build_ocr_md ->
run_doc_translate -> assemble_ru_book.

Зачем отдельный скрипт. У маршрута MinerU приёмка есть: translate_book.py
зовёт layout_report.py и audit_selfcheck.py. У фрактурного маршрута её не было
ни одной стадии, и шесть томов подряд собрались без единой машинной проверки:
сборка LaTeX формально чистая (0 Overfull, 0 ошибок), а внутри — немецкие
куски, служебный токен вместо названия главы и ни одного номера параграфа.
Дефект доезжал до печатной полосы молча.

Гейты проверяют идентичность, выравнивание и заданные инварианты;
эвристики качества дают предупреждения. CJK и служебные фразы сверяются
с источником. Любое срабатывание требует диагностики, а не автоматического
удаления текста. Эти проверки не подтверждают смысловую полноту перевода.

Использование:
    python scripts/accept_fraktur.py <work_dir> [--structure structure.json]
        [--profile prebuild|draft|release] [--build DIR] [--json OUT.json]
        [--allow-untranslated] [--allow-ratio] [--quiet]

Коды: 0 — нет проваленных гейтов выбранного профиля; 1 — провал гейта.
Наличие предупреждений и непроверенных стадий смотреть в JSON.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from provenance import load_manifest, inside, check_result, normalized, sha_file, canonical_hash
from translate import added_cjk, added_ellipsis, leaks_instructions, split_blocks, structural_literals
from build_release import inspect_pdf
from editorial import reference_findings, source_review, term_guard_findings, review_ledger

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAGE_MARK = re.compile(r"^<!--(-?\d+)-->$")
PARA_MARK = re.compile(r"^§\s*(\d{1,4})\.?\s*$")
IMAGE_ONLY = re.compile(r"^!\[[^\]]*\]\([^)]+\)$")

# Хангыль здесь не роскошь: «시작» доехало до PDF тома 6. Кириллицу и латиницу
# не трогаем — латиница в немецкой книге законна (имена, цитаты).
FOREIGN_RE = re.compile(
    "[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    "\u1100-\u11ff\uac00-\ud7af]")

# Служебный токен и его смысловые переводы: пока «/no_think» стоял в
# переводимом тексте, модель переводила ЕГО, и шесть глав тома 6 получили
# название «/без_рассуждений».
LEAK_RE = re.compile(
    r"/no[_ ]?think|no_think"
    r"|/без[_ ]?(?:рассужден|размышлен|расчет|расчёт)"
    r"|без_(?:рассужден|размышлен|расчет|расчёт)"
    r"|/(?:но|не)[_ ]?думать|(?:но|не)_думать", re.I)

TERMINAL = ".!?:»\"')…"

# Полосы длины блока. Границы не круглые числа из головы: 900 — значение
# --split-chars, которым переведён том 6, поэтому «до 900» это блоки, которые
# уходили в модель целиком, а «от 900» — те, что резались. 3500 — порог, на
# котором у Hy-MT2 без нарезки отношение длин падало до 0,79 (при 1,03 на
# коротких): именно на этой полосе видно, конспектирует модель или переводит.
BANDS = [(0, 700), (700, 1500), (1500, 3500), (3500, 10 ** 9)]
BAND_MIN_BLOCKS = 15        # полоса тоньше — числу верить нельзя
RATIO_FLOOR = 0.80          # ниже — модель конспектирует, а не переводит


def blocks_of(path):
    """Блоки файла ровно так, как их видит translate.py."""
    return split_blocks(Path(path).read_text(encoding="utf-8"))


def is_prose(b):
    s = b.strip()
    return not (PAGE_MARK.match(s) or PARA_MARK.match(s)
                or IMAGE_ONLY.match(s) or s.startswith("#"))


class Report:
    """Копилка находок. Гейт валит код выхода, предупреждение — нет.

    `detail` — это текст ПРОВАЛА, и он показывается только при провале.
    Число, которое надо видеть всегда (и когда всё хорошо), передаётся
    отдельным `value`: иначе пройденная проверка печатает свою же
    страшилку («остались неразвёрнутые маски») как результат.
    """

    def __init__(self):
        self.gates, self.warns, self.metrics = [], [], {}

    def _put(self, name, ok, detail, value, bucket):
        self.metrics[name] = value if value is not None else ok
        if not ok:
            bucket.append((name, detail))
        return ok

    def gate(self, name, ok, detail="", value=None):
        return self._put(name, ok, detail, value, self.gates)

    def warn(self, name, ok, detail="", value=None):
        return self._put(name, ok, detail, value, self.warns)

    def note(self, name, value):
        self.metrics[name] = value


# ---------------------------------------------------------------- части

def find_parts(work_dir):
    manifest = load_manifest(work_dir)
    return [(i, str(inside(work_dir, row["path"])), str(inside(work_dir, row["output"])),
             str(inside(work_dir, row["output"])) + ".report.json")
            for i, row in enumerate(manifest["parts"], 1)]


def check_reports(work_dir, rep, allow_untranslated=False):
    try:
        manifest = load_manifest(work_dir)
        parts = find_parts(work_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        rep.gate("manifest", False, str(exc))
        return []
    configs = set()
    for n, src, dst, _ in parts:
        try:
            result = check_result(src, dst, manifest["manifest_sha256"])
            configs.add(result["request_config_sha256"])
            ok = result["status"] == "passed" and not result["kept_source"] and not result["failed_blocks"]
            (rep.warn if allow_untranslated else rep.gate)(
                f"translation part {n}", ok, "raw MT contains failed blocks")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            rep.gate(f"part {n} identity", False, str(exc))
    rep.gate("request configuration", len(configs) == 1, "mixed or missing translation configurations")
    return parts


def check_parts_cover_book(work_dir, md_path, parts, rep):
    """Части — это book.md, разрезанный на куски, и ничего сверх того.

    Проверка появилась после случая с «Энциклопедией» 1817: прежняя сборка
    давала пять частей, новая — три, а build_ocr_md.py лишние не убирал.
    Переводчик честно перевёл book.part4.md и book.part5.md от предыдущей
    редакции, сборщик так же честно подшил бы их в книгу, и НИ ОДНА проверка
    этого не увидела бы: выравнивание блоков сходится, потому что лишними
    оказываются обе стороны сразу. Ловится только сверкой с book.md.
    """
    if not os.path.exists(md_path) or not parts:
        return
    want = normalized(Path(md_path).read_text(encoding="utf-8"))
    have = "\n\n".join(normalized(Path(src).read_text(encoding="utf-8")) for _, src, _, _ in parts)
    rep.gate("части покрывают book.md", have == want, "source parts differ in content/order")


def check_alignment(parts, rep):
    """Блок исходника ↔ блок перевода, один к одному.

    assemble_ru_book восстанавливает уровни заголовков по НОМЕРУ блока в
    немецком исходнике. Разъехалось выравнивание — и заголовки встают не на
    свои места, причём сборка при этом проходит без единой жалобы.
    """
    bad = []
    pairs = []
    for n, src, dst, _ in parts:
        if not os.path.exists(dst):
            continue
        de, ru = blocks_of(src), blocks_of(dst)
        if len(de) != len(ru):
            bad.append(f"часть {n}: {len(de)} против {len(ru)}")
        pairs.extend(zip(de, ru))
    rep.gate("выравнивание блоков", not bad, "; ".join(bad))
    return pairs


# ------------------------------------------------------- структура книги

def check_paragraph_numbers(md_path, rep, expect=None):
    nums = []
    for b in blocks_of(md_path):
        m = PARA_MARK.match(b.strip())
        if m:
            nums.append(int(m.group(1)))
    rep.note("номеров §", len(nums))
    if not nums:
        if expect:
            rep.gate("номера §", False,
                     f"ни одного, а карта тома обещает {expect[0]}–{expect[1]}")
        return
    dups = [n for n, c in Counter(nums).items() if c > 1]
    rep.gate("номера § без повторов", not dups, f"повторяются: {sorted(dups)[:20]}")
    mono = all(a < b for a, b in zip(nums, nums[1:]))
    rep.gate("номера § возрастают", mono,
             "" if mono else "порядок нарушен: "
             + str([(a, b) for a, b in zip(nums, nums[1:]) if a >= b][:10]))
    if expect:
        lo, hi = expect
        want = set(range(lo, hi + 1))
        gaps = sorted(want - set(nums))
        rep.warn("номера § без пропусков", not gaps,
                 f"{len(gaps)} из {len(want)} нет: {gaps[:25]}"
                 + ("…" if len(gaps) > 25 else ""))
        extra = sorted(set(nums) - want)
        rep.warn("номера § вне диапазона", not extra, f"{extra[:20]}")


def check_page_marks(md_path, rep):
    marks = [int(m.group(1)) for b in blocks_of(md_path)
             if (m := PAGE_MARK.match(b.strip()))]
    rep.note("колонцифр", len(marks))
    if not marks:
        return
    dups = [n for n, c in Counter(marks).items() if c > 1]
    rep.gate("колонцифры без повторов", not dups, f"повторяются: {sorted(dups)[:20]}")
    mono = all(a < b for a, b in zip(marks, marks[1:]))
    rep.warn("колонцифры возрастают", mono,
             "" if mono else str([(a, b) for a, b in zip(marks, marks[1:])
                                  if a >= b][:10]))
    holes = [n for n in range(min(marks), max(marks) + 1) if n not in set(marks)]
    rep.warn("колонцифры без пропусков", not holes,
             f"{len(holes)} пропущено: {holes[:25]}" + ("…" if len(holes) > 25 else ""))


def check_number_profile(md_path, rep, cfg):
    """Expected ranges/restarts are book data, never inferred from a sequence gap."""
    text = Path(md_path).read_text(encoding="utf-8")
    nums = [int(m[1]) for b in blocks_of(md_path) if (m := PARA_MARK.fullmatch(b.strip()))]
    profile = cfg.get("paragraph_profile") or {}
    expect = profile.get("range") or cfg.get("paragraph_expect")
    sequence = profile.get("sequence")
    if sequence is None and expect:
        sequence = [n for n in range(expect[0], expect[1] + 1)
                    if n not in profile.get("allow_missing", [])]
    if sequence is not None:
        (rep.gate if profile.get("strict", True) else rep.warn)(
            "paragraph profile", nums == sequence,
            f"expected {sequence[:15]}… ({len(sequence)}), got {nums[:15]}… ({len(nums)})")
    else:
        check_paragraph_numbers(md_path, rep)
        if cfg.get("paragraph_numbers"):
            rep.warn("paragraph expectation", False, "no explicit range/sequence; completeness not verified")
    findings = reference_findings(text, set(nums))
    rep.note("references", findings)
    rep.warn("reference targets", not any(r["status"] == "warning" for r in findings),
             "unresolved/next/external references require source review; text was not rewritten")


def check_source_quality(md_path, rep):
    """Качество НЕМЕЦКОГО исходника: обрубки и несклеенные развороты.

    Меряется на book.md, а не на переводе: обрубок — дефект сборки исходника,
    и по переводу его уже не отличить от авторской фразы.
    """
    prose = [b.strip() for b in blocks_of(md_path) if is_prose(b)]
    if not prose:
        return
    stubs = [b for b in prose if b and b[-1] not in TERMINAL]
    lower = [b for b in prose
             if (m := re.search(r"[A-Za-zÄÖÜäöüß]", b)) and m.group().islower()]
    stub_s = f"{len(stubs)} из {len(prose)} ({100.0 * len(stubs) / len(prose):.1f} %)"
    low_s = f"{len(lower)} из {len(prose)} ({100.0 * len(lower) / len(prose):.1f} %)"
    rep.warn("блоки без конечной пунктуации",
             len(stubs) <= max(20, len(prose) // 20), stub_s, value=stub_s)
    rep.warn("абзацы с маленькой буквы",
             len(lower) <= max(20, len(prose) // 20), low_s, value=low_s)


# --------------------------------------------------------- качество MT

def check_ratio(pairs, rep, allow=False):
    """Отношение длин перевода к исходнику — общее и ПО ПОЛОСАМ ДЛИНЫ БЛОКА.

    Общее число почти ничего не говорит: короткие блоки переводятся с запасом
    и вытягивают среднее. Конспектирование видно только по полосам — у Hy-MT2
    без нарезки отношение падало с 1,03 на коротких блоках до 0,79 на блоках
    от 3500 знаков. Это повод сверить выровненные контексты, а не доказательство
    пересказа или его отсутствия: численная длина не проверяет смысл.
    """
    data = [(len(d), len(r)) for d, r in pairs if is_prose(d)]
    if not data:
        return
    de_all = sum(d for d, _ in data)
    ru_all = sum(r for _, r in data)
    rep.note("отношение длин ru/de", round(ru_all / max(1, de_all), 3))
    rows, bad = [], []
    for lo, hi in BANDS:
        band = [(d, r) for d, r in data if lo <= d < hi]
        if not band:
            continue
        de = sum(d for d, _ in band)
        ru = sum(r for _, r in band)
        ratio = ru / max(1, de)
        name = f"{lo}–{hi if hi < 10 ** 9 else '∞'}"
        rows.append((name, len(band), round(ratio, 3)))
        if len(band) >= BAND_MIN_BLOCKS and ratio < RATIO_FLOOR:
            bad.append(f"полоса {name}: {ratio:.3f} на {len(band)} блоках")
    rep.note("отношение длин по полосам",
             [{"полоса": n, "блоков": c, "ru/de": v} for n, c, v in rows])
    table = " | ".join(f"{n}: {v} ({c})" for n, c, v in rows)
    rep.warn("отношение длин по полосам", not bad or allow,
             "; ".join(bad), value=table)


def check_translation_hygiene(pairs, rep):
    """Source-aware technical invariants, not a ban on quoted foreign text."""
    foreign, leaks, structural, ellipses, literals = [], [], [], [], []
    for de, ru in pairs:
        if added_cjk(de, ru):
            foreign.append(ru.strip()[:90])
        if leaks_instructions(de, ru):
            leaks.append(ru.strip()[:90])
        if added_ellipsis(de, ru):
            ellipses.append(ru.strip()[:90])
        if structural_literals(de) != structural_literals(ru):
            literals.append(de.strip()[:90])
        for pattern in (PAGE_MARK, PARA_MARK):
            source_marker = pattern.fullmatch(de.strip())
            translated_marker = pattern.fullmatch(ru.strip())
            if source_marker and (not translated_marker or source_marker[1] != translated_marker[1]):
                structural.append(de.strip())
    rep.gate("structural marker conservation", not structural, str(structural))
    rep.gate("added ellipses", not ellipses, str(ellipses))
    rep.gate("numbers/enumeration/footnote conservation", not literals, str(literals))
    rep.gate("чужие письменности", not foreign,
             f"{len(foreign)} блоков: " + " | ".join(foreign[:3]),
             value=len(foreign))
    rep.gate("утечки служебного токена", not leaks,
             f"{len(leaks)} блоков: " + " | ".join(leaks[:3]),
             value=len(leaks))


# ------------------------------------------------------------- сборка

def check_build(build_dir, rep, required=False, source_text=""):
    log = os.path.join(build_dir, "main.log")
    body = os.path.join(build_dir, "body.tex")
    pdf = os.path.join(build_dir, "main.pdf")
    if not os.path.exists(log):
        (rep.gate("build", False, "required main.log missing") if required
         else rep.note("build", "not_run"))
        return
    if required:
        try:
            compiled = json.loads((Path(build_dir) / "compile.report.json").read_text(encoding="utf-8"))
            rep.gate("compile identity", compiled.get("status") == "passed"
                     and compiled.get("pdf_sha256") == sha_file(pdf)
                     and compiled.get("stabilized") is True,
                     "missing/failed/foreign bounded compile report")
        except (OSError, ValueError, KeyError):
            rep.gate("compile identity", False, "missing/invalid compile report")
        technical = inspect_pdf(pdf, log, require_toc=True, source_text=source_text)
        rep.gate("technical PDF", technical["status"] == "passed", str(technical["errors"]))
        rep.note("technical PDF detail", technical)
    text = open(log, encoding="utf-8", errors="replace").read()
    missing = Counter(re.findall(r"Missing character: There is no (.) in font",
                                 text))
    rep.gate("Missing character", not missing,
             f"{sum(missing.values())} шт.: {dict(missing.most_common(10))}",
             value=sum(missing.values()))
    over = [float(x) for x in
            re.findall(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide", text)]
    over_s = f"{len(over)}" + (f", максимум {max(over):.1f}pt" if over else "")
    rep.warn("Overfull \\hbox", len(over) <= 50, over_s, value=over_s)
    m = re.search(r"Output written on .*?\((\d+) pages", text, re.S)
    rep.note("страниц в PDF", int(m.group(1)) if m else None)
    if os.path.exists(pdf):
        rep.note("байт в PDF", os.path.getsize(pdf))
    if os.path.exists(body):
        tex = open(body, encoding="utf-8", errors="replace").read()
        lone = 0
        for m in re.finditer(r"\\begin\{(enumerate|itemize)\}(.*?)"
                             r"\\end\{\1\}", tex, re.S):
            if m.group(2).count(r"\item") == 1:
                lone += 1
        rep.warn("списки из одного пункта", lone == 0, str(lone), value=lone)
        rep.gate("маски M###### в body.tex",
                 not re.search(r"M\d{6}", tex), "остались неразвёрнутые маски")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir")
    ap.add_argument("--structure", default=None,
                    help="structure.json тома: оттуда берётся ожидаемый "
                         "диапазон номеров параграфов (paragraph_expect)")
    ap.add_argument("--build", default=None, help="по умолчанию <work_dir>/build")
    ap.add_argument("--md", default=None, help="по умолчанию <work_dir>/book.md")
    ap.add_argument("--json", default=None, help="куда положить машинный отчёт")
    ap.add_argument("--allow-untranslated", action="store_true",
                    help="не валить приёмку из-за kept_source > 0 "
                         "(осознанное решение выпустить том с немецкими кусками)")
    ap.add_argument("--allow-ratio", action="store_true",
                    help="не жаловаться на провал отношения длин по полосам")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--profile", choices=["prebuild", "draft", "release"], default="prebuild")
    a = ap.parse_args()

    if not os.path.isdir(a.work_dir):
        sys.exit(f"!! нет каталога {a.work_dir}")
    md = a.md or os.path.join(a.work_dir, "book.md")
    build = a.build or os.path.join(a.work_dir, "build")
    cfg = {}
    sj = a.structure or os.path.join(a.work_dir, "structure.json")
    if os.path.exists(sj):
        cfg = json.load(open(sj, encoding="utf-8"))

    rep = Report()
    parts = check_reports(a.work_dir, rep, a.allow_untranslated)
    pairs = check_alignment(parts, rep) if parts else []
    check_parts_cover_book(a.work_dir, md, parts, rep)
    if os.path.exists(md):
        check_number_profile(md, rep, cfg)
        trace = Path(a.work_dir) / "structure.trace.json"
        if trace.exists():
            trace_data = json.loads(trace.read_text(encoding="utf-8"))
            rep.gate("structure anchors", not trace_data.get("uncertainties"),
                     "unresolved paragraph candidates: inspect structure.trace.json")
        check_page_marks(md, rep)
        check_source_quality(md, rep)
        review = source_review(blocks_of(md), cfg)
        rep.gate("OCR review", review["status"] != "failed", "unreviewed suspicious OCR; inspect profile/source")
        try:
            ledger = review_ledger(a.work_dir, load_manifest(a.work_dir), blocks_of(md))
            rep.gate("editorial findings", ledger["status"] != "failed", str(ledger["findings"]))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            rep.gate("editorial findings", False, str(exc))
    else:
        rep.gate("book.md", False, "source missing")
    if pairs:
        check_ratio(pairs, rep, a.allow_ratio)
        check_translation_hygiene(pairs, rep)
        term_errors = [f for source, target in pairs
                       for f in term_guard_findings(source, target, cfg.get("term_guards", []))]
        rep.gate("term guards", not term_errors, str(term_errors[:3]))
    if a.profile != "prebuild":
        check_build(build, rep, required=a.profile == "release",
                    source_text=Path(md).read_text(encoding="utf-8") if Path(md).exists() else "")
    else:
        rep.note("build", "not_run")

    if not a.quiet:
        print(f"== приёмка: {a.work_dir} ==")
        for k, v in rep.metrics.items():
            if isinstance(v, bool):
                continue
            print(f"  {k:34s} {v}")
        print("-- гейты --")
        if rep.gates:
            for name, detail in rep.gates:
                print(f"  !! {name}: {detail}")
        else:
            print("  все пройдены")
        if rep.warns:
            print("-- предупреждения --")
            for name, detail in rep.warns:
                print(f"  ?? {name}: {detail}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "profile": a.profile,
                       "status": "failed" if rep.gates else "warning" if rep.warns or a.profile == "draft" or a.allow_untranslated else "passed",
                       "visual_review": "not_run", "semantic_review": "not_run",
                       "work_dir": a.work_dir, "metrics": rep.metrics,
                       "gates_failed": [g[0] for g in rep.gates],
                       "warnings": [w[0] for w in rep.warns]},
                      f, ensure_ascii=False, indent=1)
        print(f"машинный отчёт: {a.json}")
    return 1 if rep.gates else 0


if __name__ == "__main__":
    sys.exit(main())
