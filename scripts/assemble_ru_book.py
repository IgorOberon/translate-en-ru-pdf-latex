# -*- coding: utf-8 -*-
"""Сборка переведённой книги: части -> markdown -> LaTeX -> PDF.

Ключевая мера предосторожности — заголовки. Промпт режима hymt требует от
модели только сохранности masked-токенов и ничего не говорит о markdown, так
что «# Vorrede» вполне может вернуться без решётки. Поэтому уровни заголовков
здесь не читаются из перевода, а ВОССТАНАВЛИВАЮТСЯ по исходному book.md:
translate.py пишет ровно один выходной блок на каждый входной, нумерация
блоков совпадает, и уровень берётся из немецкого оригинала. Так структура
книги не зависит от аккуратности модели.

Маркеры <!--N--> (печатная страница оригинала) превращаются в поля-заметки:
том нужен для сличения редакций, и без исходной пагинации он для этого
бесполезен.

Использование:
    python scripts/assemble_ru_book.py <work_dir> [--build DIR] [--pdf OUT.pdf]
        [--title ...] [--subtitle ...] [--author ...] [--no-build]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile

if hasattr(sys.stdout, "reconfigure"):      # не обёртка: она
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import ROOT  # noqa: E402
from provenance import load_manifest, inside, check_result, sha_file, sha_text, write_json, canonical_hash, release_inputs
from build_release import compile_latex, inspect_pdf, publish_candidate
from editorial import source_review, term_guard_findings, review_ledger
from translate import added_ellipsis, structural_literals

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_MARK = re.compile(r"^<!--(-?\d+)-->$")


def check_reports(work_dir, n_parts):
    """Content identity and post-edit provenance, never block-count/mtime trust."""
    try:
        manifest = load_manifest(work_dir)
        if len(manifest["parts"]) != n_parts:
            raise ValueError("unexpected part count")
        configs = set()
        for row in manifest["parts"]:
            report = check_result(inside(work_dir, row["path"]),
                                  inside(work_dir, row["output"]),
                                  manifest["manifest_sha256"])
            configs.add(report["request_config_sha256"])
            if report.get("status") != "passed" or report.get("kept_source") or report.get("failed_blocks"):
                raise ValueError(f"raw MT failed: {row['output']}")
        if len(configs) != 1:
            raise ValueError("parts translated with different request configurations")
        return True, [f"verified identities: {n_parts} parts; semantic review not performed"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, [str(exc)]


def split_blocks(text):
    return re.split(r"\n\s*\n", text.strip())


def load_parts(work_dir, stem):
    manifest = load_manifest(work_dir)
    key = "output" if stem == "book.ru.part" else "path"
    result = []
    for row in manifest["parts"]:
        result.extend(split_blocks(inside(work_dir, row[key]).read_text(encoding="utf-8")))
    return result, len(manifest["parts"])


# Служебный токен и его смысловые переводы. Пока «/no_think» стоял первой
# строкой переводимого текста, модель на коротких блоках переводила ЕГО, а не
# заголовок: том 6 получил шесть глав с названием «/без_рассуждений», и они же
# попали в оглавление, в закладки PDF и в колонтитул 83 страниц. Утечка
# закрыта в translate.py, но заголовок — слишком дорогое место, чтобы
# полагаться на одну заслонку.
BAD_HEADING = re.compile(
    r"^\s*/|no[_ ]?think|без[_ ]?(?:рассужден|размышлен)|(?:но|не)[_ ]?думать",
    re.I)


def load_ru_headings(work_dir, src_blocks):
    """headings.ru.json от build_ocr_md: номер блока -> готовый русский текст.

    Файл привязан к НОМЕРУ БЛОКА, а book.md мог с тех пор пересобраться, и
    тогда номера съехали. Сверяем немецкий текст на этом месте: не совпал —
    файл не про этот исходник, и пользоваться им нельзя.
    """
    p = os.path.join(work_dir, "headings.ru.json")
    if not os.path.exists(p):
        return {}
    data = json.load(open(p, encoding="utf-8"))
    heads, stale = {}, []
    for k, v in (data.get("headings") or {}).items():
        i = int(k)
        if i >= len(src_blocks):
            stale.append(f"блок {i} за пределами исходника")
            continue
        de_here = re.sub(r"^#{1,6}\s*", "", src_blocks[i].strip()).strip()
        if de_here != v.get("de", "").strip():
            stale.append(f"блок {i}: в исходнике «{de_here[:40]}», "
                         f"в карте «{v.get('de', '')[:40]}»")
            continue
        heads[i] = v
    if stale:
        sys.exit("!! headings.ru.json не про этот book.md (номера блоков "
                 "съехали):\n   " + "\n   ".join(stale[:5])
                 + "\n   Пересоберите исходник build_ocr_md.py — он пишет "
                   "спутник вместе с book.md.")
    return heads


def restore_headings(src_blocks, ru_blocks, ru_heads=None, lax=False):
    """Уровень заголовка берём из немецкого исходника, текст — из перевода.

    Текст берётся из перевода только там, где готового русского нет в карте:
    название раздела — не проза, и доверять его модели не следует. Ответ
    модели, который не может быть заголовком (пустой, начинается со слэша,
    несёт служебный токен), останавливает сборку: механизм, задуманный как
    защита структуры, до сих пор молча цементировал первую строку ответа в
    \\chapter, и сработал против себя.
    """
    if len(src_blocks) != len(ru_blocks):
        sys.exit(f"!! блоки разошлись: исходник {len(src_blocks)}, "
                 f"перевод {len(ru_blocks)}. Сборка остановлена, иначе "
                 f"заголовки встанут не на свои места.")
    ru_heads = ru_heads or {}
    out, fixed, kept, from_map, bad, trimmed = [], 0, 0, 0, [], 0
    for i, (src, ru) in enumerate(zip(src_blocks, ru_blocks)):
        m = re.match(r"^(#{1,6})\s+", src.strip())
        body = ru.strip()
        if not m:
            # модель иногда дорисовывает решётку там, где её не было
            if body.startswith("#") and not PAGE_MARK.match(body):
                body = re.sub(r"^#{1,6}\s*", "", body)
            out.append(body)
            continue
        level = len(m.group(1))
        if i in ru_heads:
            out.append("#" * level + " " + ru_heads[i]["ru"].strip())
            from_map += 1
            continue
        stripped = re.sub(r"^#{1,6}\s*", "", body).strip()
        # многострочный ответ на заголовок — это перевод плюс отсебятина;
        # берём первую строку, но говорим об этом
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[0].strip()
            trimmed += 1
        if not stripped or BAD_HEADING.search(stripped):
            de_here = re.sub(r"^#{1,6}\s*", "", src.strip()).strip()
            bad.append(f"блок {i}: «{stripped[:60]}» "
                       f"(в исходнике «{de_here[:50]}»)")
            stripped = re.sub(r"^#{1,6}\s*", "", src.strip()).strip()
        if body.startswith("#" * level + " "):
            kept += 1
        else:
            fixed += 1
        out.append("#" * level + " " + stripped)
    if bad and not lax:
        sys.exit("!! модель вернула вместо заголовка служебный мусор:\n   "
                 + "\n   ".join(bad[:10])
                 + "\n   Заголовок уезжает в оглавление, в закладки PDF и в "
                   "колонтитул десятков страниц, поэтому сборка остановлена. "
                   "Впишите русский текст в structure.json (inject[...].ru) и "
                   "пересоберите исходник, либо соберите как есть ключом "
                   "--lax-headings: тогда на этих местах встанет немецкий "
                   "оригинал.")
    return out, fixed, kept, from_map, bad, trimmed


IMAGE_ONLY = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)$")


def to_markdown(blocks, page_marks=True, fig_width=0.42, layout=None):
    out, pending_marks = [], []
    for index, b in enumerate(blocks):
        m = PAGE_MARK.match(b.strip())
        if m:
            if page_marks and layout is None:
                pending_marks.append(r"\marginpar{\raggedright\scriptsize\bfseries %s}" % m.group(1))
            continue
        if b.lstrip().startswith("#"):
            # A marginpar before \chapter emits an otherwise empty page.
            # Keep source markers with the following heading's body, not its
            # preceding page; never split translated prose by character ratio.
            out.append(b)
            continue
        out.extend(pending_marks)
        pending_marks.clear()
        meta = (layout or {}).get(str(index), {})
        pages = meta.get("pages", [])
        if page_marks and pages and not re.fullmatch(r"§\s*\d+\.", b.strip()):
            # Coverage belongs to THIS block, never a fake position in the next.
            label = str(pages[0]) if len(pages) == 1 else ",".join(map(str, pages))
            if len(pages) > 1 and pages == list(range(pages[0], pages[-1] + 1)):
                label = f"{pages[0]}--{pages[-1]}"
            out.append(r"\marginpar{\raggedright\scriptsize с.~" + label + "}")
        img = IMAGE_ONLY.match(b.strip())
        if img:
            # Ширину задаём здесь, а не в исходнике: в markdown картинка
            # должна оставаться голой ссылкой, иначе translate.py перестанет
            # узнавать блок-картинку и отправит её в модель. Без ограничения
            # чертёж растягивается на всю полосу — у Евклида книга разбухала
            # со 194 страниц до 464.
            out.append(r"\begin{center}\includegraphics[width=%.2f\linewidth,"
                       r"keepaspectratio]{%s}\end{center}"
                       % (fig_width, img.group(1)))
            continue
        if meta.get("unit") in ("remark", "addition"):
            out.append("\\begin{quote}\\small\n\n" + b + "\n\n\\end{quote}")
        else:
            out.append(b)
    out.extend(pending_marks)
    return "\n\n".join(out) + "\n"


def escape_specials(text):
    """Знаки, которые pandoc с raw_tex/tex_math_dollars примет за разметку.

    В прозе перевода их быть не должно, но одиночный '$' из OCR превращает
    полкниги в формулу, а '\\' — в неизвестную команду.
    """
    n = [0]

    def esc(m):
        n[0] += 1
        return "\\" + m.group(0)

    # \marginpar мы вставили сами — его трогать нельзя
    parts = re.split(r"(\\marginpar\{[^}]*\})", text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<!\\)[$]", esc, parts[i])
        parts[i] = re.sub(r"\\(?![a-zA-Z$])", lambda m: r"\textbackslash{}",
                          parts[i])
    return "".join(parts), n[0]


TITLE_TEX = r"""
\begin{titlepage}
\centering
\vspace*{2.5cm}
{\Large %(author)s\par}
\vspace{2.2cm}
{\Huge\bfseries %(title)s\par}
\vspace{1.2cm}
{\large %(subtitle)s\par}
\vfill
{\small %(colophon)s\par}
\vspace{1.5cm}
\end{titlepage}
"""


TEX_SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
                "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def tex_escape(s):
    """Титул и колофон идут в LaTeX как есть, а в них живут «deu_latf» и
    «Hy-MT2-7B»: подчёркивание уводит строку в математику, и колофон выходит
    как «deu‗atf. : Hy − MT2 − 7B». Экранируем."""
    return "".join(TEX_SPECIALS.get(ch, ch) for ch in s or "")


def build_main_tex(preamble, body_rel, meta):
    with open(preamble, encoding="utf-8") as f:
        pre = f.read()
    title = TITLE_TEX % meta
    return "\n".join([
        pre,
        # Заголовки книги уже несут собственные порядковые имена («Первая
        # книга», «Первый отдел», «Первая глава») — нумерация LaTeX дала бы
        # «Глава 4. Первая книга». Гасим её, оглавление при этом остаётся.
        r"\setcounter{secnumdepth}{-1}",
        r"\setcounter{tocdepth}{2}",
        # поля под номера страниц оригинала
        r"\usepackage[a4paper,inner=2.4cm,outer=3.6cm,top=2.4cm,"
        r"bottom=2.6cm,marginparwidth=2.2cm,marginparsep=4mm]{geometry}",
        # geometry подключается ПОСЛЕ fancyhdr (он в преамбуле), поэтому
        # ширина и высота колонтитула остаются от прежней полосы: на
        # Энциклопедии это дало 114 Overfull подряд и предупреждение
        # «\headheight is too small». Пересчитываем и переобъявляем стиль.
        r"\setlength{\headheight}{14pt}",
        r"\setlength{\headwidth}{\textwidth}",
        r"\pagestyle{fancy}",
        r"\begin{document}",
        title,
        r"\tableofcontents\clearpage",
        r"\input{%s}" % body_rel,
        r"\end{document}",
        "",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--build", default=None)
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--preamble", default=os.path.join(ROOT, "assets",
                                                       "preamble.tex"))
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--colophon", default="")
    ap.add_argument("--no-page-marks", action="store_true")
    ap.add_argument("--figure-width", type=float, default=0.42,
                    help="доля ширины полосы под чертёж (0.42 — как в оригинале, где схема стоит сбоку от текста)")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--allow-untranslated", action="store_true",
                    help="собрать том, даже если перевод потерял блоки "
                         "(kept_source > 0 или непустой failed_blocks). "
                         "Без этого ключа сборка останавливается: немецкий "
                         "кусок посреди русской книги — не то, что стоит "
                         "обнаруживать глазами на печатной полосе")
    ap.add_argument("--no-accept", action="store_true",
                    help="не гонять приёмку после сборки")
    ap.add_argument("--lax-headings", action="store_true",
                    help="не останавливать сборку из-за заголовка, который "
                         "модель вернула мусором: поставить на его место "
                         "немецкий оригинал")
    a = ap.parse_args()

    build_root = Path(a.build or Path(a.work_dir) / "build")
    build_root.mkdir(parents=True, exist_ok=True)
    build = tempfile.mkdtemp(prefix="candidate-", dir=build_root)
    draft = a.no_accept or a.allow_untranslated or a.lax_headings or a.no_build
    release = {"schema": 1, "profile": "draft" if draft else "release", "status": "failed",
               "candidate": Path(build).name, "visual_review": "not_run", "semantic_review": "not_run"}
    write_json(Path(build) / "release.report.json", release)

    inputs_hash = release_inputs(a.work_dir)
    release["inputs_sha256"] = inputs_hash
    src_blocks, _ = load_parts(a.work_dir, "book.part")
    ru_blocks, n_parts = load_parts(a.work_dir, "book.ru.part")
    print(f"частей {n_parts}: блоков исходника {len(src_blocks)}, "
          f"перевода {len(ru_blocks)}")

    ok, lines = check_reports(a.work_dir, n_parts)
    for ln in lines:
        print(("   " if ok else "!! ") + ln)
    if not ok and not a.allow_untranslated:
        sys.exit("!! сборка остановлена. Повторный запуск run_doc_translate.py "
                 "переведёт только провалы (кэш держит успешное); собрать как "
                 "есть — ключом --allow-untranslated")

    cfg_path = Path(a.work_dir) / "structure.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    source_check = source_review(src_blocks, cfg)
    ledger = review_ledger(a.work_dir, load_manifest(a.work_dir), src_blocks)
    term_errors = [f for s, t in zip(src_blocks, ru_blocks)
                   for f in term_guard_findings(s, t, cfg.get("term_guards", []))]
    term_errors.extend({"kind": "added-ellipsis", "block": i}
                       for i, (s, t) in enumerate(zip(src_blocks, ru_blocks)) if added_ellipsis(s, t))
    term_errors.extend({"kind": "structural-literals", "block": i}
                       for i, (s, t) in enumerate(zip(src_blocks, ru_blocks))
                       if structural_literals(s) != structural_literals(t))
    write_json(Path(build) / "editorial.gate.json", {"source": source_check, "term_findings": term_errors, "ledger": ledger})
    if not draft and (source_check["status"] == "failed" or term_errors or ledger["status"] == "failed"):
        sys.exit("!! source/term review failed; inspect editorial.gate.json. Published PDF unchanged.")

    ru_heads = load_ru_headings(a.work_dir, src_blocks)
    blocks, fixed, kept, from_map, bad, trimmed = restore_headings(
        src_blocks, ru_blocks, ru_heads, a.lax_headings)
    print(f"заголовки: восстановлено {fixed}, пришло из перевода целыми "
          f"{kept}, взято готовыми из карты {from_map}")
    if trimmed:
        if not a.lax_headings:
            sys.exit("!! multiline heading: supply headings.ru.json; silent truncation prohibited")
        print(f"!! draft: {trimmed} multiline headings trimmed")
    if bad:
        print(f"!! {len(bad)} заголовков заменены немецким оригиналом "
              f"(--lax-headings): " + "; ".join(b[:60] for b in bad[:5]))

    trace = Path(a.work_dir) / "structure.trace.json"
    layout = json.loads(trace.read_text(encoding="utf-8")).get("layout") if trace.exists() else None
    if layout is not None:
        for index, meta in layout.items():
            if sha_text(src_blocks[int(index)]) != meta["source_sha256"]:
                raise ValueError("layout metadata/source identity mismatch")
    md = to_markdown(blocks, page_marks=not a.no_page_marks,
                     fig_width=a.figure_width, layout=layout)
    md, n_esc = escape_specials(md)
    if n_esc:
        print(f"экранировано спецсимволов: {n_esc}")

    md_path = os.path.join(build, "book.ru.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"{md_path}: {len(md)} символов")

    # Картинки должны лежать рядом с main.tex: graphicspath в преамбуле ищет
    # их в build/images. Без этого копирования сборка тихо подставляет рамку
    # «рисунок не найден» вместо каждого чертежа.
    src_img = os.path.join(a.work_dir, "images")
    if os.path.isdir(src_img):
        dst_img = os.path.join(build, "images")
        os.makedirs(dst_img, exist_ok=True)
        n_img = 0
        for f in os.listdir(src_img):
            s, d = os.path.join(src_img, f), os.path.join(dst_img, f)
            if os.path.isfile(s) and (not os.path.exists(d)
                                      or os.path.getmtime(s) > os.path.getmtime(d)):
                shutil.copyfile(s, d)
            n_img += 1
        print(f"картинок в сборке: {n_img}")

    body = os.path.join(build, "body.tex")
    cmd = ["pandoc", md_path,
           "--from=markdown+raw_tex-tex_math_dollars-smart",
           "--to=latex", "--top-level-division=chapter", "--wrap=preserve",
           "--output=" + body]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("pandoc не отработал")
    print(f"{body}: {os.path.getsize(body)} байт")

    meta = {"author": tex_escape(a.author or ""), "title": tex_escape(a.title or Path(a.work_dir).name),
            "subtitle": tex_escape(a.subtitle),
            "colophon": tex_escape(a.colophon)}
    with open(os.path.join(build, "main.tex"), "w", encoding="utf-8") as f:
        f.write(build_main_tex(a.preamble, "body.tex", meta))

    if a.no_build:
        release.update(status="warning", reason="--no-build: prebuild only")
        write_json(Path(build) / "release.report.json", release)
        print("сборка PDF пропущена (--no-build); кандидат: " + build)
        return 0

    compiled = compile_latex(Path(build) / "main.tex")
    release["compile"] = compiled
    pdf = Path(build) / "main.pdf"
    if compiled["status"] != "passed":
        release["reason"] = compiled.get("error")
        write_json(Path(build) / "release.report.json", release)
        print(f"!! build failed; candidate retained: {build}")
        return 1
    source_text = "\n\n".join(src_blocks)
    technical = inspect_pdf(pdf, Path(build) / "main.log", require_toc=True, source_text=source_text)
    release["technical"] = technical
    release["pdf_sha256"] = sha_file(pdf)
    release["manifest_sha256"] = load_manifest(a.work_dir)["manifest_sha256"]
    rc_accept = None
    if not a.no_accept:
        # Persist actual acceptance, including warnings; no stdout-only success.
        rc_accept = subprocess.run([sys.executable, "-X", "utf8",
            str(Path(HERE) / "accept_fraktur.py"), a.work_dir, "--build", build,
            "--profile", "release", "--json", str(Path(build) / "accept.report.json")]
            + (["--allow-untranslated"] if a.allow_untranslated else [])).returncode
        subprocess.run([sys.executable, "-X", "utf8",
                        str(Path(HERE) / "layout_report.py"), build])
    acceptance_path = Path(build) / "accept.report.json"
    if acceptance_path.exists():
        release["acceptance"] = json.loads(acceptance_path.read_text(encoding="utf-8"))
    if technical["status"] != "passed" or (not a.no_accept and
            (rc_accept != 0 or release.get("acceptance", {}).get("status") not in ("passed", "warning"))):
        release["reason"] = "mandatory technical acceptance failed or missing"
        write_json(Path(build) / "release.report.json", release)
        print(f"!! acceptance failed; published PDF untouched; candidate: {build}")
        return 3
    # Re-check input/report identities immediately before committing publication.
    ok, lines = check_reports(a.work_dir, n_parts)
    if release_inputs(a.work_dir) != inputs_hash:
        release["reason"] = "assembly inputs changed during build"
        write_json(Path(build) / "release.report.json", release)
        return 3
    if not ok and not a.allow_untranslated:
        release["reason"] = lines
        write_json(Path(build) / "release.report.json", release)
        return 3
    if draft:
        release.update(status="warning", reason="explicit bypass: draft only")
        write_json(Path(build) / "release.report.json", release)
        print(f"DRAFT (not published): {pdf}")
        return 4
    release["status"] = "passed"
    write_json(Path(build) / "release.report.json", release)
    if a.pdf:
        publish_candidate(pdf, a.pdf, release)
    print(f"PDF: {a.pdf or pdf}; technical acceptance passed; semantic review not_run")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
        sys.exit(f"!! assembly refused: {exc}. Published PDF unchanged.")
