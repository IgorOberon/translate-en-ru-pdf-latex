#!/usr/bin/env python3
"""Check that every figure referenced by the book exists and is a real image.

Compares references in body.tex (or a markdown file) against an images folder,
reports missing files, zero-byte files and fake JPEGs (wrong signature), and
writes the missing list to missing_images.txt next to the folder.

Usage:
  python scripts/check_images.py build/body.tex build/images
  python scripts/check_images.py extract/book/book.md extract/book/images
"""
import re
import sys
from pathlib import Path

print(">> check_images.py v1 loaded", flush=True)


def refs_from(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".tex",):
        raw = re.findall(r"\\includegraphics[^{]*\{([^}]+)\}", text)
    else:
        raw = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)
    return sorted({Path(r).name for r in raw})


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, folder = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.exists() or not folder.is_dir():
        print("!! проверьте пути: нужен body.tex/markdown и папка с картинками")
        sys.exit(1)

    names = refs_from(src)
    missing, empty, fake = [], [], []
    for n in names:
        f = folder / n
        if not f.exists():
            missing.append(n)
            continue
        b = f.read_bytes()
        if len(b) < 8:
            empty.append(n)
        elif f.suffix.lower() in (".jpg", ".jpeg") and not (
                b[0] == 0xFF and b[1] == 0xD8 and b[-2] == 0xFF and b[-1] == 0xD9):
            fake.append(n)

    total_files = len([p for p in folder.iterdir() if p.is_file()])
    print(f"ссылок в документе: {len(names)} | файлов в папке: {total_files}")
    print(f"ОТСУТСТВУЮТ: {len(missing)} | пустые: {len(empty)} | битая сигнатура: {len(fake)}")
    problems = missing + empty + fake
    if problems:
        out = folder.parent / "missing_images.txt"
        out.write_text("\n".join(problems) + "\n", encoding="utf-8")
        print(f"список проблемных -> {out}")
        for n in problems[:5]:
            print("  ", n)
        sys.exit(1)
    print("ВСЁ НА МЕСТЕ ✓")


if __name__ == "__main__":
    main()
