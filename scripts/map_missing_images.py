#!/usr/bin/env python3
"""Map figures between two extractions of the same book.

When a book is re-extracted, most image hashes match the old ones, but a few
crops differ by a pixel and get new names — the translated body.tex then shows
framed "[рисунок не найден]" placeholders. This tool aligns the OLD reference
sequence (from body.tex or old markdown) with the NEW extraction's sequence,
using identical hashes as anchors, maps the gaps pairwise in document order,
and copies the new files into the build under their OLD names.

Usage:
  python scripts/map_missing_images.py build/body.tex \
      reextract/book/book.md reextract/book/images build/images
"""
import difflib
import re
import shutil
import sys
from pathlib import Path

print(">> map_missing_images.py v1 loaded", flush=True)


def refs_in_order(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".tex":
        raw = re.findall(r"\\includegraphics[^{]*\{([^}]+)\}", text)
    else:
        raw = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)
    return [Path(r).name for r in raw]


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    old_src, new_src = Path(sys.argv[1]), Path(sys.argv[2])
    new_dir, dst_dir = Path(sys.argv[3]), Path(sys.argv[4])
    for p, what in ((old_src, "старый body/md"), (new_src, "новый md"),
                    (new_dir, "папка новых картинок"), (dst_dir, "папка сборки")):
        if not p.exists():
            print(f"!! не найден {what}: {p}")
            sys.exit(1)

    old = refs_in_order(old_src)
    new = refs_in_order(new_src)
    print(f"старых ссылок: {len(old)} | новых: {len(new)}")

    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    mapped = skipped = already = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        gap_old, gap_new = old[i1:i2], new[j1:j2]
        if tag == "replace" and len(gap_old) == len(gap_new):
            for o, n in zip(gap_old, gap_new):
                dst = dst_dir / o
                srcf = new_dir / n
                if dst.exists():
                    already += 1
                    continue
                if srcf.exists():
                    shutil.copy2(srcf, dst)
                    mapped += 1
                    print(f"  {n[:12]}…  ->  {o[:12]}…")
                else:
                    skipped += 1
                    print(f"?? нового файла нет на диске: {n}")
        else:
            skipped += len(gap_old)
            for o in gap_old:
                if not (dst_dir / o).exists():
                    print(f"?? не сопоставлено (разные размеры пробела): {o}")

    print(f"\nсопоставлено и скопировано: {mapped}; уже были: {already}; "
          f"осталось без пары: {skipped}")
    print("дальше: check_images.py для контроля, затем 2 прохода xelatex")
    sys.exit(0 if skipped == 0 else 1)


if __name__ == "__main__":
    main()
