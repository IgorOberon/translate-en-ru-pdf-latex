#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Соблюдение глоссария: считает, где предписанный перевод термина не встал.

Проверки соблюдения не было ни в одном скрипте конвейера. На томе 6 её
пришлось делать руками, и она сразу оказалась содержательной: прежний
глоссарий соблюдался на 61,5 %, суженный — на 71,2 %. Без этого числа
непонятно, работает глоссарий вообще или просто занимает контекст.

Как считается. Блоки исходника и перевода выровнены один к одному
(translate.py пишет ровно один выходной блок на каждый входной), поэтому для
каждого немецкого блока с термином известен его русский двойник. Термин
засчитан, если в русском блоке стоит любая словоформа предписанного перевода.

Немецкий термин ищется вместе со склонениями и композитами: «Bestimmung»
находится и в «Bestimmungen», и в «Grundbestimmung» — в немецком это тот же
термин, и переводить его надо так же. Но не внутри чего попало: короткие
основы (меньше MIN_STEM) ищутся только как отдельное слово, иначе «Maaß»
находится в «Maassregel», а «Katete» — в первом попавшемся слоге.

Русская сторона сравнивается по основе: цель «понятие» засчитывается и как
«понятия», и как «понятию». Варианты через «;» или скобки — любой из них.

Использование:
    python scripts/check_glossary.py <work_dir> --glossary FILE
        [--min-hits 20] [--floor 0.5] [--json OUT] [--top 15]

Код 1 — есть термин с >= --min-hits вхождений и соблюдением ниже --floor.
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_STEM = 6            # короче — только как отдельное слово
MD_LINE = re.compile(r"^\s*([^#=].*?)\s*=>\s*(.+?)\s*$")
RU_TAIL = re.compile(r"(ый|ий|ой|ая|яя|ое|ее|ые|ие|ость|ство|ние|ие|а|я|о|е|"
                     r"ь|й|ы|и|у|ю)$")


def load_glossary(path):
    """[(немецкий, [русские варианты])] в порядке файла."""
    text = open(path, encoding="utf-8-sig").read()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    rows = []
    if path.lower().endswith(".tsv"):
        for ln in text.splitlines():
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            c = ln.split("\t")
            if len(c) >= 2 and c[0].strip() and c[1].strip():
                rows.append((c[0].strip(), c[1].strip()))
    else:
        for ln in text.splitlines():
            m = MD_LINE.match(ln)
            if m:
                rows.append((m.group(1), m.group(2)))
    out = []
    for src, dst in rows:
        # «внешнее друг-другу; внеположность», «видимость (кажимость)»,
        # «образ, форма» — любой вариант считается соблюдением
        parts = re.split(r"[;,]| \(|\)", dst)
        variants = [p.strip() for p in parts if p.strip()]
        if variants:
            out.append((src.strip(), variants))
    return out


ARTICLE = re.compile(r"^(?:das|der|die|ein|eine|den|dem|des)\s+", re.I)
# Немецкие окончания склонения/спряжения, которые термин только ДОБАВЛЯЕТ.
DE_TAIL = r"(?:e|en|es|s|er|em|n|ns|nen|ung|ungen)?"


def de_pattern(term):
    """Немецкий термин со склонениями и в составе композитов.

    Ловушки, на которых наивная версия давала бессмыслицу:

    * «das Einzelne» — если брать первое слово, термином становится артикль
      «das», и он находится 2905 раз;
    * «Nichts» — если срезать окончание до основы «Nicht», термин совпадает с
      обычным отрицанием «nicht», и вхождений становится 1508 вместо
      настоящих;
    * «Werden» — то же со вспомогательным глаголом «werden».

    Отсюда два правила. Основа НЕ срезается (немецкое склонение окончания
    добавляет, а не убирает), и термин-существительное ищется С УЧЁТОМ
    РЕГИСТРА: в немецком существительное пишется с прописной, и «Werden»
    отличимо от «werden» без всякой морфологии.
    """
    t = ARTICLE.sub("", term.strip())
    core = re.split(r"[\s(,/]", t)[0]
    if len(core) < 4:
        return None
    body = re.escape(core) + DE_TAIL
    if not core[:1].isupper():
        # глагол или прилагательное: регистр ничего не различает
        if len(core) >= MIN_STEM + 1:
            return re.compile(r"(?<![A-Za-zÄÖÜäöüß])" + body, re.I)
        return re.compile(r"(?<![A-Za-zÄÖÜäöüß])" + body + r"(?![a-zäöüß])",
                          re.I)
    # Существительное. Регистр здесь несёт смысл, и флаг re.I отдавать
    # нельзя — иначе «Werden» совпадёт с глаголом «werden», а «Nichts» с
    # отрицанием «nichts». Но внутри композита то же слово стоит со строчной
    # («Grundbestimmung»), поэтому вариант со строчной прописывается отдельно
    # и только после буквы — то есть заведомо не в начале слова.
    if len(core) >= MIN_STEM + 1:
        low = re.escape(core[:1].lower() + core[1:]) + DE_TAIL
        pat = (r"(?<![A-Za-zÄÖÜäöüß])" + body
               + r"|(?<=[a-zäöüß])" + low)
    else:
        pat = r"(?<![A-Za-zÄÖÜäöüß])" + body + r"(?![a-zäöüß])"
    return re.compile(pat)


# Порядок важен: длинные окончания раньше коротких, иначе «определённость»
# теряет только «ь».
#
# У глагола срезается ровно «ть»: «снимать» -> «снима» покрывает и «снимает»,
# и «снимают». Срезать «ать» целиком нельзя — «сним» ловит ещё и «снимок».
#
# Голых «ие»/«ые» в списке нет намеренно: подавляющее большинство целей
# глоссария — существительные среднего рода на «-ие», и правило для
# множественного числа прилагательных съедало бы у них лишнюю букву
# («понятие» -> «понят», а это уже и «понятный»).
RU_SUFFIX = ("ание", "ение", "ость", "ство", "ться", "ть",
             "ый", "ий", "ой", "ая", "яя", "ое", "ее",
             "ь", "й", "а", "я", "о", "е", "ы", "и", "у", "ю")
RU_MIN_STEM = 4


def yo(s):
    """ё и е — одна буква для целей сверки.

    Глоссарий пишет «определённость», модель отвечает «определенность», и без
    этой нормализации термин показывает 16 % соблюдения там, где он соблюдён.
    """
    return s.replace("ё", "е").replace("Ё", "Е")


def ru_stem(word):
    w = yo(word.lower())
    for suf in RU_SUFFIX:
        if w.endswith(suf) and len(w) - len(suf) >= RU_MIN_STEM:
            return w[:-len(suf)]
    return w


def ru_pattern(variants):
    """Любая словоформа любого из предписанных переводов."""
    alts = []
    for v in variants:
        words = [w for w in re.split(r"[\s-]+", v.strip().lower()) if w]
        if not words:
            continue
        # у словосочетания смотрим главное слово (последнее): «наличное
        # бытие» в тексте склоняется и переставляется, а «бытие» остаётся
        head = words[-1]
        head = yo(head)
        alts.append(re.escape(head) if len(head) <= 3
                    else re.escape(ru_stem(head)) + r"\w{0,5}")
    if not alts:
        return None
    return re.compile(r"\b(?:" + "|".join(alts) + r")", re.I)


def blocks_of(path):
    return [b for b in re.split(r"\n\s*\n",
                                open(path, encoding="utf-8").read())
            if b.strip()]


def load_pairs(work_dir):
    pairs, n = [], 1
    while True:
        src = os.path.join(work_dir, f"book.part{n}.md")
        dst = os.path.join(work_dir, f"book.ru.part{n}.md")
        if not os.path.exists(src):
            break
        if not os.path.exists(dst):
            sys.exit(f"!! нет перевода части {n}")
        de, ru = blocks_of(src), blocks_of(dst)
        if len(de) != len(ru):
            sys.exit(f"!! часть {n}: блоки разошлись ({len(de)} против "
                     f"{len(ru)}) — сравнивать нечего")
        pairs.extend(zip(de, ru))
        n += 1
    if not pairs:
        sys.exit(f"!! нет book.partN.md в {work_dir}")
    return pairs


def measure(pairs, glossary):
    rows = []
    for term, variants in glossary:
        rx_de, rx_ru = de_pattern(term), ru_pattern(variants)
        if not rx_de or not rx_ru:
            continue
        hits = kept = 0
        misses = []
        for de, ru in pairs:
            m = rx_de.search(de)
            if not m:
                continue
            n = len(rx_de.findall(de))
            hits += n
            if rx_ru.search(yo(ru)):
                kept += n
            elif len(misses) < 3:
                # показываем МЕСТО совпадения, а не начало блока: иначе
                # в примере промаха стоит текст, к термину не относящийся
                a, b = max(0, m.start() - 45), min(len(de), m.end() + 45)
                misses.append(" ".join(de[a:b].split()))
        if hits:
            rows.append({"term": term, "target": "; ".join(variants),
                         "hits": hits, "kept": kept,
                         "share": round(kept / hits, 3), "misses": misses})
    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir")
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--min-hits", type=int, default=20,
                    help="термин реже этого числа вхождений не влияет на код "
                         "выхода: на редком термине доля — это шум")
    ap.add_argument("--floor", type=float, default=0.5)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    gloss = load_glossary(a.glossary)
    pairs = load_pairs(a.work_dir)
    rows = measure(pairs, gloss)
    if not rows:
        print("!! ни один термин глоссария в книге не встретился")
        return 1

    hits = sum(r["hits"] for r in rows)
    kept = sum(r["kept"] for r in rows)
    dead = [t for t, _ in gloss if not any(r["term"] == t for r in rows)]
    print(f"== глоссарий {a.glossary}: строк {len(gloss)}, "
          f"встретилось в книге {len(rows)}, мёртвых {len(dead)}")
    print(f"   вхождений {hits}, соблюдено {kept} "
          f"({100.0 * kept / max(1, hits):.1f} %)")

    bad = [r for r in rows
           if r["hits"] >= a.min_hits and r["share"] < a.floor]
    worst = sorted([r for r in rows if r["hits"] >= a.min_hits],
                   key=lambda r: r["share"])[:a.top]
    print(f"\n-- {len(worst)} худших из тех, что встречаются "
          f">= {a.min_hits} раз --")
    print(f"   {'термин':28s} {'перевод':28s} {'вхожд':>6s} {'доля':>6s}")
    for r in worst:
        print(f"   {r['term'][:27]:28s} {r['target'][:27]:28s} "
              f"{r['hits']:6d} {r['share']:6.2f}")
    if dead:
        print(f"\n-- мёртвые строки (термина в книге нет): {len(dead)} --")
        print("   " + ", ".join(dead[:25]) + ("…" if len(dead) > 25 else ""))
    if a.json:
        json.dump({"glossary": a.glossary, "share": kept / max(1, hits),
                   "hits": hits, "kept": kept, "dead": dead, "terms": rows},
                  open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\nмашинный отчёт: {a.json}")
    if bad:
        print(f"\n!! {len(bad)} терминов ниже порога {a.floor:.0%} "
              f"при >= {a.min_hits} вхождениях:")
        for r in bad[:10]:
            print(f"   {r['term']} -> {r['target']}: {r['share']:.0%} "
                  f"на {r['hits']} вхождениях")
            for m in r["misses"][:1]:
                print(f"      напр.: …{m}…")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
