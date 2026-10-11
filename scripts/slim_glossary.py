#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slim_glossary.py — тонкий глоссарий-фид для модели из большого мастер-файла.

Боевой урок Тейлора: глоссарий на 200+ строк в system-промпте размывает
внимание 7B-модели — переводы терминов начинают плавать. Рабочая схема:
мастер-глоссарий (tsv/md) остаётся источником истины для аудита, а модели
на главу подаётся slim-фид <= ~100 строк: «всегда-классы» (имена, ловушки,
конвенции, производные термины, аббревиатуры — по пометке в note) плюс
строки, помеченные текущей главой.

Входы:
  glossary.tsv — 3 колонки TAB: source, target, note (note необязательна)
  glossary.md  — строки «english => русский» (note нет — фильтр по главе
                 недоступен, работает только обрезка --max-rules)

Usage:
  python scripts/slim_glossary.py glossary.tsv --chapter 12 --out slim.md
  python scripts/slim_glossary.py glossary.tsv --out slim.md     # без главы
  python scripts/slim_glossary.py glossary.md --max-rules 80     # в stdout
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_glossary import de_pattern          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ALWAYS_DEFAULT = r"имя|ловушк|конвенц|производн|аббр"
MD_LINE = re.compile(r"^\s*([^#=].*?)\s*=>\s*(.+?)\s*$")


def load_rows(path):
    """[(source, target, note)] в исходном порядке."""
    path = Path(path)
    rows = []
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".tsv":
        for ln in text.splitlines():
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            cols = ln.split("\t")
            if len(cols) < 2 or not cols[0].strip() or not cols[1].strip():
                continue
            rows.append((cols[0].strip(), cols[1].strip(),
                         cols[2].strip() if len(cols) > 2 else ""))
    else:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # шапка-комментарий
        for ln in text.splitlines():
            m = MD_LINE.match(ln)
            if m:
                rows.append((m.group(1), m.group(2), ""))
    return rows


def keep_present(rows, doc_path, min_hits=1):
    """Оставить только термины, которые в тексте действительно встречаются.

    Мастер-глоссарий пишется на серию томов, а модели в system-промпт уходит
    он целиком: лишние сотни строк размывают внимание 7B и провоцируют то, ради
    чего в translate.py появился валидатор утечки — модель печатает глоссарий
    вместо перевода.

    Прежняя проверка срезала у термина два последних знака и искала остаток
    ПОДСТРОКОЙ в тексте, приведённом к нижнему регистру. Так в книге
    «находились» термины, которых в ней нет: основа попадала внутрь другого
    слова. На томе 6 из 241 строки мёртвыми оказались 60 — они приехали из
    «Философии природы» (Katete, Radius, Meteorologie) и занимали контекст
    молча. Теперь термин ищется тем же матчером, что и в check_glossary.py:
    с учётом регистра для существительных, со склонением, и внутрь другого
    слова попадает только длинная основа — как часть немецкого композита.
    """
    text = Path(doc_path).read_text(encoding="utf-8")
    out = []
    for src, dst, note in rows:
        rx = de_pattern(src)
        if rx is None:
            continue
        n = len(rx.findall(text))
        if n >= min_hits:
            out.append((n, (src, dst, note)))
    # частые термины вперёд: при обрезке --max-rules уходит хвост, а не ядро
    out.sort(key=lambda kv: -kv[0])
    return [r for _, r in out]


def select(rows, chapter, always_re, max_rules):
    """(выбранные строки, статистика). Приоритет: всегда-классы, затем глава,
    затем прочее; внутри яруса — исходный порядок."""
    always = re.compile(always_re, re.I)
    ch_re = (re.compile(rf"(?:гл|глава|ch|chapter)\.?\s*{chapter}\b", re.I)
             if chapter else None)
    tiers = {"always": [], "chapter": [], "rest": []}
    for r in rows:
        note = r[2]
        if note and always.search(note):
            tiers["always"].append(r)
        elif ch_re and ch_re.search(note):
            tiers["chapter"].append(r)
        elif not ch_re:
            tiers["rest"].append(r)   # без --chapter берём всё (до обрезки)
    picked = tiers["always"] + tiers["chapter"] + tiers["rest"]
    dropped = max(0, len(picked) - max_rules)
    return picked[:max_rules], tiers, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glossary", help="мастер-глоссарий: .tsv или .md")
    ap.add_argument("--chapter", type=int, default=None,
                    help="номер главы: взять всегда-классы + строки с пометкой "
                         "«гл.N» в note")
    ap.add_argument("--classes", default=ALWAYS_DEFAULT,
                    help=f"регэксп всегда-классов по note (default: "
                         f"{ALWAYS_DEFAULT})")
    ap.add_argument("--max-rules", type=int, default=100,
                    help="потолок строк фида (default 100)")
    ap.add_argument("--present-in", default=None,
                    help="файл текста: оставить только термины, которые в нём "
                         "встречаются (режет мастер-глоссарий серии до тома)")
    ap.add_argument("--min-hits", type=int, default=1,
                    help="с --present-in: сколько раз термин должен "
                         "встретиться, чтобы попасть в фид. Единичное "
                         "вхождение ядром понятий книги не является, а место "
                         "в контексте занимает")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="потолок фида в ЗНАКАХ (0 — без потолка). Контекст "
                         "LM Studio делится между параллельными слотами, и "
                         "решает не число строк, а объём: при 8192 на 4 слота "
                         "на запрос приходится 2048 токенов, а глоссарий на "
                         "8,7 КБ — это около 3400")
    ap.add_argument("--out", default=None,
                    help="файл фида «en => ru» (по умолчанию — stdout)")
    a = ap.parse_args()

    rows = load_rows(a.glossary)
    if not rows:
        sys.exit(f"!! в {a.glossary} не найдено ни одной строки глоссария")
    n_all = len(rows)
    if a.present_in:
        rows = keep_present(rows, a.present_in, a.min_hits)
        print(f">> present-in {a.present_in}: {n_all} -> {len(rows)} строк",
              file=sys.stderr)
    picked, tiers, dropped = select(rows, a.chapter, a.classes, a.max_rules)

    seen, lines = set(), []
    for src, dst, _ in picked:
        if src.lower() in seen:
            continue
        seen.add(src.lower())
        lines.append(f"{src} => {dst}")

    # Потолок по объёму, а не по числу строк: контекст LM Studio делится
    # между параллельными слотами, и переполняет его не количество правил,
    # а их вес в токенах. Режем хвост — строки уже отсортированы по частоте,
    # так что уходят самые редкие термины, а ядро понятий остаётся.
    cut_chars = 0
    if a.max_chars:
        kept, size = [], 0
        for ln in lines:
            if size + len(ln) + 1 > a.max_chars:
                cut_chars += 1
                continue
            kept.append(ln)
            size += len(ln) + 1
        lines = kept

    body = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(body, encoding="utf-8")
    else:
        print(body, end="")

    hdr = (f">> slim_glossary: всего {len(rows)}, всегда-классы "
           f"{len(tiers['always'])}"
           + (f", глава {a.chapter}: {len(tiers['chapter'])}" if a.chapter
              else "")
           + f" -> в фид {len(lines)}"
           + (f", обрезано по объёму {cut_chars}" if cut_chars else "")
           + ((" (обрезано %d — поднимите --max-rules%s)"
               % (dropped, "" if a.chapter else " или задайте --chapter"))
              if dropped else ""))
    print(hdr, file=sys.stderr, flush=True)
    if a.out:
        print(f">> фид: {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
