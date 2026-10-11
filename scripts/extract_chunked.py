#!/usr/bin/env python3
"""Chunked MinerU extraction — defeats the client's 60-minute per-task timeout.

Splits the PDF into parts of --pages-per-chunk pages, runs `mineru` on each
part separately (each run finishes well under the timeout), then merges the
resulting markdown files in order and gathers all images into one folder, so
the main pipeline finds a single complete book.

Resumable: parts that already produced markdown are skipped on re-run.

Usage:
  python scripts/extract_chunked.py "D:\\books\\book.pdf" book_ru\\extract --pages-per-chunk 200

Then run the usual translate_book.py command — it will find the merged
markdown and skip extraction.
"""
import argparse
import faulthandler
import filecmp
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from procutils import TIMEOUT_RC, PipelineLock, run_mineru, unload_llm  # noqa: E402
from prepare_mineru import prepare

print(">> extract_chunked.py v4 (диагностика тихой смерти) loaded", flush=True)

# Диагностика. Скрипт умирал молча: ни traceback, ни кода выхода, ни строчки
# в логе — и место смерти было невидимо, потому что буферизованный stdout
# пропадал вместе с процессом. Корень найден и убран (reap_mineru убивал
# собственное дерево процессов, см. procutils.own_lineage), но тихая смерть
# от чего-то ещё не должна повторить ту же историю: пишем состояние в файл
# на каждом шаге, traceback — в файл, код выхода — в файл.
_DIAG = {"dir": None, "fh": None}


def diag_setup(outdir):
    d = Path(outdir) / "_chunks"
    d.mkdir(parents=True, exist_ok=True)
    _DIAG["dir"] = d
    # faulthandler держит файл открытым всё время работы: аварийный дамп
    # (segfault, abort) пишется прямо в него
    _DIAG["fh"] = open(d / "extract_faulthandler.log", "w", encoding="utf-8")
    faulthandler.enable(file=_DIAG["fh"])
    (d / "extract_exit_code.txt").write_text("RUNNING", encoding="utf-8")
    stage("старт, pid=%d" % os.getpid())


def stage(msg):
    """Отметка «докуда дошли». Читается, когда процесс умер без следов."""
    print(">>", msg, flush=True)
    d = _DIAG["dir"]
    if d:
        (d / "extract_state.txt").write_text(msg + "\n", encoding="utf-8")


def diag_finish(code, exc_text=None):
    d = _DIAG["dir"]
    if d:
        (d / "extract_exit_code.txt").write_text(str(code), encoding="utf-8")
        if exc_text:
            (d / "extract_error.log").write_text(exc_text, encoding="utf-8")
            print(f"!! traceback записан в {d / 'extract_error.log'}",
                  flush=True)
    if _DIAG["fh"]:
        _DIAG["fh"].flush()


def die(msg):
    print("!!", msg, flush=True)
    diag_finish(1, "die(): " + msg + "\n")
    sys.exit(1)


def run(cmd, **kw):
    print(">>", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(list(map(str, cmd)), **kw)


def find_md(root):
    mds = sorted((p for p in root.rglob("*.md")
                  if not any(s in p.name for s in (".prepared", ".clean", ".removed_"))),
                 key=lambda p: p.stat().st_size, reverse=True)
    return mds[0] if mds else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir", help="итоговая папка extract (как у translate_book)")
    ap.add_argument("--pages-per-chunk", type=int, default=200,
                    help="страниц в части (200 ≈ 30-35 мин на RTX 5060 Ti)")
    ap.add_argument("--vram-limit", type=int, default=0,
                    help="ограничить аппетит MinerU (ГБ VRAM); спасает от зависания "
                         "системы на плотных страницах, напр. 8")
    ap.add_argument("--mineru-timeout", type=int, default=3600,
                    help="таймаут одной части, сек (0 = без таймаута)")
    ap.add_argument("--no-lock", action="store_true",
                    help="не брать глобальный замок конвейера")
    a = ap.parse_args()
    diag_setup(a.outdir)

    if not a.no_lock:
        # под translate_book пройдёт мгновенно (env FREETRANSLATE_LOCK)
        stage("беру замок конвейера")
        PipelineLock(note=f"extract_chunked:{Path(a.pdf).name}").acquire()

    try:
        import fitz  # pymupdf — ставится вместе с mineru
    except ImportError:
        die("нужен pymupdf: pip install pymupdf")
    stage("проверяю mineru в PATH")
    if not shutil.which("mineru"):
        die("'mineru' not found in PATH (pip install \"mineru[core]\")")

    pdf = Path(a.pdf).resolve()
    if not pdf.exists():
        die(f"нет такого файла: {pdf}")
    outdir = Path(a.outdir).resolve()
    parts_dir = outdir / "_chunks"
    parts_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf)
    total = len(doc)
    n = a.pages_per_chunk
    ranges = [(s, min(s + n, total)) for s in range(0, total, n)]
    stage(f"{total} страниц -> {len(ranges)} частей по <= {n}")

    # 1) нарезать PDF на части (пропуская уже существующие)
    part_pdfs = []
    for i, (s, e) in enumerate(ranges, 1):
        pp = parts_dir / f"part{i:02d}.pdf"
        part_pdfs.append((i, pp))
        if pp.exists():
            continue
        nd = fitz.open()
        nd.insert_pdf(doc, from_page=s, to_page=e - 1)
        nd.save(pp)
        nd.close()
        print(f">> нарезана {pp.name}: страницы {s + 1}-{e}", flush=True)
    doc.close()

    # 2) прогнать mineru по частям (возобновляемо)
    part_mds = []
    for i, pp in part_pdfs:
        pout = parts_dir / f"out{i:02d}"
        md = find_md(pout) if pout.exists() else None
        if md:
            print(f">> часть {i}: markdown уже есть, пропуск", flush=True)
        else:
            pout.mkdir(parents=True, exist_ok=True)
            stage(f"часть {i}/{len(part_pdfs)}: запускаю mineru")
            unload_llm()  # also mandatory when the chunker is run standalone
            rc = run_mineru(["-p", pp, "-o", pout], pout / "mineru.log",
                            timeout=a.mineru_timeout, vram_limit=a.vram_limit)
            if rc == TIMEOUT_RC:
                # зависание VLM стохастическое — один авторетрай части
                print(f"?? часть {i} зависла — одна повторная попытка",
                      flush=True)
                rc = run_mineru(["-p", pp, "-o", pout], pout / "mineru.log",
                                timeout=a.mineru_timeout,
                                vram_limit=a.vram_limit)
            if rc:
                die(f"mineru упал на части {i} (код {rc}) — перезапустите ту "
                    "же команду, готовые части не потеряются")
            md = find_md(pout)
            if md is None:
                die(f"часть {i}: mineru не выдал markdown")
        # Page-scoped notes must be recovered before content-list sidecars and
        # original page ranges are separated by the merge.
        part_mds.append((i, prepare(md)))

    # 3) слить: один markdown + общая папка images
    stage("сливаю части в один markdown")
    book_dir = outdir / pdf.stem
    img_dir = book_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    merged = []
    for i, md in part_mds:
        text = md.read_text(encoding="utf-8")
        # перенести картинки этой части, при совпадении имён — префикс части
        renames = {}
        for src_dir in [p for p in md.parent.iterdir()
                        if p.is_dir() and "image" in p.name.lower()]:
            for f in src_dir.iterdir():
                if not f.is_file():
                    continue
                name = f.name
                if (img_dir / name).exists() and \
                   not filecmp.cmp(f, img_dir / name, shallow=False):
                    name = f"p{i:02d}_{f.name}"
                    renames[f.name] = name
                shutil.copy2(f, img_dir / name)
        for old, new in renames.items():
            text = text.replace(old, new)
        # пути к картинкам могли быть вида "some_dir/имя" — нормализуем на images/
        text = re.sub(r"!\[([^\]]*)\]\((?:[^)/\\]+[/\\])*([^)/\\]+)\)",
                      r"![\1](images/\2)", text)
        merged.append(text.strip())
        print(f">> часть {i}: {len(text)} символов, слита", flush=True)

    out_md = book_dir / f"{pdf.stem}.md"
    out_md.write_text("\n\n".join(merged) + "\n", encoding="utf-8")
    print(f"\nDONE: {out_md}  ({out_md.stat().st_size} bytes, "
          f"картинок: {len(list(img_dir.iterdir()))})", flush=True)
    print("Теперь запустите обычную команду translate_book.py — "
          "извлечение будет пропущено.", flush=True)
    print(f"Папку {parts_dir} можно удалить после проверки результата.",
          flush=True)
    stage("готово")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        diag_finish(e.code if e.code is not None else 0)
        raise
    except BaseException:                                   # noqa: BLE001
        # KeyboardInterrupt тоже сюда: «оборвали руками» и «умер сам» надо
        # различать по файлу, а не по памяти
        diag_finish(1, traceback.format_exc())
        raise
    else:
        diag_finish(0)
