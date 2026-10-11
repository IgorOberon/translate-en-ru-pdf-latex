"""УСТАРЕЛО — используйте scripts/build_ocr_md.py.

Этот скрипт стоил провального выпуска Logik 1812: strip_running_heads() режет
блок по слову («Kapitel», «Abschnitt», «Vorrede»), то есть выбрасывает
ЗАГОЛОВКИ ГЛАВ вместе с колонтитулами. Книга уходила в вёрстку без единой
главы: оглавление собиралось из случайного мусора, а в колонтитуле всех
девятисот полос стояло «Оглавление». Заодно pre_clean() ловит Google-дисклеймер
только по префиксу первого абзаца, а склейка переносов сохраняла дефис.

Оставлен ради воспроизводимости старых прогонов. Для новых томов:
    python scripts/build_ocr_md.py <work_dir> --offset N --structure book.json

Подготовка OCR-текста к переводу:
1. Выкинуть Google-титульные страницы и пустые страницы.
2. Убрать колонтитулы-шапки (Vorrede/Einleitung/Kapitel... как standalone строка).
3. Разбить на части по ~300 блоков (echo-лимит hy-mt2), каждая со своим кэшем.

Использование:
    python prepare_ocr_md.py <book.md> <book_clean.md> [--parts 300]
"""
import argparse
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):      # не обёртка: она
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Предохранитель, а не просто пометка в docstring: 07.08.2026 агент запустил
# этот скрипт через час после того, как тот был помечен устаревшим, и второй
# том поехал по сломанному пути. Запуск без флага теперь останавливается.
if "--i-know-its-deprecated" in sys.argv:
    sys.argv.remove("--i-know-its-deprecated")
else:
    sys.exit(
        "!! prepare_ocr_md.py УСТАРЕЛ и удаляет заголовки глав вместе с "
        "колонтитулами (провал Logik 1812).\n"
        "   Для готических томов: python scripts/build_ocr_md.py <work_dir> "
        "--offset N --structure structure.json\n"
        "   (маршрут целиком — README.md, раздел «Готические тома»).\n"
        "   Воспроизвести старый прогон: добавьте --i-know-its-deprecated.")

RUNNING_HEADS = [
    "Vorrede", "Einleitung", "Inhalt", "Einleitn ng", "Jnhaltsanzeige",
    "Inhaltsanzeige", "Kapitel", "Abschnitt", "Anmerkung", "Vor-",
    "Jnhalts"[0:3],
    # Гегель: логика терминов в шапках
    "Seite", "Erster", "Zweiter", "Erste", "Zweite", "Vorerinnerung",
]
RUNNING_HEAD_RE = re.compile(
    r"^(Vorrede|Einleitung|Inhaltsanzeige|Inhalt|Kapitel|Abschnitt|"
    r"Anmerkung|Vorerinnerung|Allgemeine Eintheilung|Erster\b|Zweiter\b|"
    r"Dritte\b|Erste\b|Zweite\b).{0,40}$"
)
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")


def is_running_head(par):
    if RUNNING_HEAD_RE.match(par.strip()):
        return True
    if PAGE_NUM_RE.match(par.strip()) and len(par.strip()) <= 4:
        return True
    return False


def pre_clean(text):
    """parma-абзацы -> список; отбрасываем явные титулы и пустоту."""
    blocks = re.split(r"\n\n+", text.strip())
    out = []
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        low = blk.lower()
        if low.startswith(("google", "coogle", "uber dieses buch",
                            "dies ist ein digitales", "os iss", "library",
                            "bez," , "digitized")):
            continue
        if len(blk) < 30 and not re.search(r"[a-zäöüß]{4,}", blk):
            continue  # мусор/картинка
        out.append(blk)
    return "\n\n".join(out)


def strip_running_heads(text):
    blocks = re.split(r"\n\n+", text.strip())
    out = [b for b in blocks if not is_running_head(b)]
    return "\n\n".join(out)


def split_paras(text):
    return re.split(r"\n\n+", text.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book_md")
    ap.add_argument("book_clean_md")
    ap.add_argument("--parts", type=int, default=300)
    a = ap.parse_args()

    raw = open(a.book_md, encoding="utf-8").read()
    text = pre_clean(raw)
    text = strip_running_heads(text)
    paras = split_paras(text)
    # убрать дубли подряд (одна и та же строка колонтитула на 2 страницах)
    dedup = []
    for p in paras:
        if dedup and dedup[-1].strip() == p.strip():
            continue
        dedup.append(p)
    paras = dedup

    with open(a.book_clean_md, "w", encoding="utf-8") as f:
        f.write("\n\n".join(paras))
    print(f"{a.book_clean_md}: {len(paras)} блоков")

    # разбиение на ~parts блоков
    out_dir = os.path.dirname(a.book_clean_md)
    n = 0
    for i in range(0, len(paras), a.parts):
        n += 1
        chunk = "\n\n".join(paras[i : i + a.parts])
        p = os.path.join(out_dir, f"book.part{n}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(chunk)
        print(f"  {p}: {len(paras[i:i+a.parts])} блоков")


if __name__ == "__main__":
    main()