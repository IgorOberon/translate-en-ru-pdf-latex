"""УСТАРЕЛО — используйте scripts/build_ocr_md.py.

Пересобрать book.md из готовых страниц OCR (без повторного распознавания) +
правка смещения. Не знает ни заголовков, ни склейки абзацев через страницы,
ни фикса длинного s — все дефекты провального прогона Logik 1812.
"""
import re
import sys

if "--i-know-its-deprecated" in sys.argv:
    sys.argv.remove("--i-know-its-deprecated")
else:
    sys.exit(
        "!! rebuild_book_md.py УСТАРЕЛ. Сборка book.md из постраничного OCR — "
        "это scripts/build_ocr_md.py (README, раздел «Готические тома»).\n"
        "   Воспроизвести старый прогон: добавьте --i-know-its-deprecated.")


def rebuild(input_pdf, out_dir, offset=0):
    import fitz
    doc = fitz.open(input_pdf)
    n = doc.page_count
    md = []
    for i in range(n):
        tpath = f"{out_dir}/pages/p{i+1:04d}.txt"
        try:
            text = open(tpath, encoding="utf-8").read()
        except FileNotFoundError:
            continue
        text = rebuild_clean(text)
        md.append(f"\n<!-- СТР. {i + 1 + offset} -->\n\n{text}")
    with open(f"{out_dir}/book.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"book.md: {n} стр., записано страниц {len(md)}")


def rebuild_clean(text):
    import re as _re
    paras = text.split("\n\n")
    out_paras = []
    for p in paras:
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        if not lines:
            continue
        joined = " ".join(lines)
        joined = _re.sub(r"-\s+", "-", joined)
        joined = _re.sub(r"[ \t]{2,}", " ", joined)
        out_paras.append(joined)
    return "\n\n".join(out_paras)


if __name__ == "__main__":
    rebuild(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)