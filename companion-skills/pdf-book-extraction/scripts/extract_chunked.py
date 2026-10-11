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
import filecmp
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

print(">> extract_chunked.py v2 loaded", flush=True)


def die(msg):
    print("!!", msg)
    sys.exit(1)


def run(cmd, **kw):
    print(">>", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(list(map(str, cmd)), **kw)


def find_md(root):
    mds = sorted(root.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
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
    a = ap.parse_args()

    try:
        import fitz  # pymupdf — ставится вместе с mineru
    except ImportError:
        die("нужен pymupdf: pip install pymupdf")
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
    print(f">> {total} страниц -> {len(ranges)} частей по <= {n}")

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
        print(f">> нарезана {pp.name}: страницы {s + 1}-{e}")
    doc.close()

    # 2) прогнать mineru по частям (возобновляемо)
    part_mds = []
    for i, pp in part_pdfs:
        pout = parts_dir / f"out{i:02d}"
        md = find_md(pout) if pout.exists() else None
        if md:
            print(f">> часть {i}: markdown уже есть, пропуск")
        else:
            pout.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ)
            if a.vram_limit:
                env["MINERU_VIRTUAL_VRAM_SIZE"] = str(a.vram_limit)
                print(f">> MINERU_VIRTUAL_VRAM_SIZE={a.vram_limit} (щадящий батч)")
            if run(["mineru", "-p", pp, "-o", pout], env=env).returncode:
                die(f"mineru упал на части {i} — перезапустите ту же команду, "
                    "готовые части не потеряются")
            md = find_md(pout)
            if md is None:
                die(f"часть {i}: mineru не выдал markdown")
        part_mds.append((i, md))

    # 3) слить: один markdown + общая папка images
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
        print(f">> часть {i}: {len(text)} символов, слита")

    out_md = book_dir / f"{pdf.stem}.md"
    out_md.write_text("\n\n".join(merged) + "\n", encoding="utf-8")
    print(f"\nDONE: {out_md}  ({out_md.stat().st_size} bytes, "
          f"картинок: {len(list(img_dir.iterdir()))})")
    print("Теперь запустите обычную команду translate_book.py — "
          "извлечение будет пропущено.")
    print(f"Папку {parts_dir} можно удалить после проверки результата.")


if __name__ == "__main__":
    main()
