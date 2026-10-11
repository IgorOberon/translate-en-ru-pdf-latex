#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверяемая постобработка: типографика, редакционные данные и журнал.

Между run_doc_translate.py и assemble_ru_book.py. Сохраняет выравнивание,
проверяет хэши, пишет lineage со снимками; сырой MT-отчёт не изменяется.
--terms даёт только рекомендации по выровненным контекстам, не подмену слов.
--corrections применяет проверенные замены полных блоков с хэшем и якорем.
Исторические fix_terms/apply_gender_rules оставлены для совместимости
прямых импортов/регрессий, CLI их НЕ вызывает. --footnotes отклоняется,
поскольку прежний алгоритм разрушал выравнивание (см. docs/INTEGRITY.md).

Использование:
    python scripts/postfix_ru.py <work_dir> [--structure structure.json]
        [--terms term_rules.json] [--corrections FILE] [--dry-run] [--no-typography]

Коды выхода: 0 — готово; 2 — нечего обрабатывать.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from provenance import load_manifest, inside, check_result, record_edit, write_json
from editorial import terminology_findings, apply_corrections, term_guard_findings, ocr_findings
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STAT = Counter()


def bump(k, n=1):
    STAT[k] += n


# ---------------------------------------------------------------- типографика

def fix_typography(ru):
    """Знаки препинания русского набора вместо машинных.

    Порядок правил важен, и каждое исключение здесь оплачено: «значения + и -»
    это математический минус, а не пауза; одинокая лапка после слова —
    закрывающая ёлочка, перед словом — открывающая, а посреди мусора —
    просто сор распознавания.
    """
    n0 = ru
    # короткое тире между словами — это длинное тире русского набора
    ru = re.sub(r"(?<=[^\d\s])\s+[–—]\s+(?=\S)", " — ", ru)
    ru = re.sub(r"(?<=\s)-(?=\s)",
                lambda m: m.group(0) if "+" in ru[max(0, m.start() - 12):
                                                  m.start()] else "—", ru)
    # немецкие и английские кавычки → ёлочки
    ru = re.sub(r"„([^“”\n]{1,400})[“”]", r"«\1»", ru)
    if "„" in ru:
        ru = re.sub(r"„(?=[^\n]*»)", "«", ru)
        ru = ru.replace("„", "")
    if "“" in ru or "”" in ru:
        ru = re.sub(r"[*\s]*[“”]\s*[—–-]\s*[“”]", "", ru)
        ru = re.sub(r"(?<=[\wа-яёА-ЯЁ.,;:!?)])\s*[“”]", "»", ru)
        ru = re.sub(r"[“”](?=[\wа-яёА-ЯЁ])", "«", ru)
        ru = re.sub(r"[“”]", "", ru)
    ru = re.sub(r"“([^“”\n]{1,400})”", r"«\1»", ru)
    ru = re.sub(r"\"([^\"\n]{1,400})\"", r"«\1»", ru)
    # неразрывный пробел там, где разрыв строки читается как ошибка набора
    ru = re.sub(r"(?<=\bстр)\.\s+(?=\d)", ". ", ru)
    ru = re.sub(r"§\s*(?=\d)", "§ ", ru)
    if ru != n0:
        bump("типографика")
    return ru


# Абзац, начинающийся с литеры и скобки («y) В процессе размышления…»),
# pandoc принимает за нумерованный список и заворачивает в enumerate со
# счётчиком — в книге получается список ровно из одного пункта, да ещё с
# чужим номером (на томе 6 таких было 41). Литера тут не нумерация, а
# огрызок рубрики: экранируем знак, и текст печатается как есть.
FALSE_LIST = re.compile(r"^(\s{0,3})([0-9]{1,3}|[a-zA-Zа-яёА-ЯЁ])([.)])(\s+\S)")


def escape_false_lists(ru):
    m = FALSE_LIST.match(ru)
    if not m:
        return ru
    bump("список из одного пункта расформирован")
    return f"{m.group(1)}{m.group(2)}\\{m.group(3)}{m.group(4)}" + ru[m.end():]


def fix_seam_ellipsis(de, ru):
    """Compatibility entry point: punctuation alone cannot prove a translation seam."""
    return ru


def mark_tier_openers(ru, words):
    """Выделить зачин яруса издания («Прибавление.», «Примечание.»).

    В издании это отдельный ярус, набранный своим кеглем, но в извлечении он
    идёт в подбор и от корпуса параграфа ничем не отличается. Слова задаются
    томом: structure.json -> postfix.tier_openers.
    """
    if not words:
        return ru
    rx = re.compile(r"^((?:%s)(?:\s*[0-9IVXA-DА-Д]{1,4})?)\s*[.:]"
                    % "|".join(re.escape(w) for w in words))
    m = rx.match(ru)
    if not m:
        return ru
    bump("зачин яруса выделен")
    return "**" + m.group(1) + ".** " + ru[m.end():].lstrip()


# ------------------------------------------------------------------- сноски

SENT = re.compile(r"(?<=[.!?»])\s+(?=[«A-ZА-ЯЁ])")
FOOTNOTE_START = re.compile(r"^\s*(\*{1,3})\s*\)\s*")
# Настоящая отсылка — звёздочка со СКОБКОЙ: «philosophischer. *) Nicht nur».
# Голая звёздочка в тексте («all*», «B*», «Gu- *») — сор распознавания, и без
# требования скобки сноска цеплялась к нему.
FOOTNOTE_REF = re.compile(r"(?<=[\w.,;:!?»)])\s*(\*{1,3})\)")


class _Span:
    """Заглушка под re.Match: нужны только start() и end()."""

    def __init__(self, pos):
        self._p = pos

    def start(self):
        return self._p

    def end(self):
        return self._p


def _ref_by_sentence(out_de, out_ru, used):
    """Отсылку модель иногда роняет при переводе. В немецком блоке она есть —
    берём номер предложения, на котором она стоит, и ставим марку на то же
    предложение русского: порядок фраз перевод хранит."""
    for j in range(max(0, len(out_ru) - 6), len(out_ru)):
        if out_ru[j].startswith(("#", "<!--")) or FOOTNOTE_START.match(out_ru[j]):
            continue
        m = FOOTNOTE_REF.search(out_de[j])
        if not m:
            continue
        # start(), а не end(): марка сноски ставится сразу за точкой,
        # а не в начало следующей фразы
        de_cuts = [x.start() for x in SENT.finditer(out_de[j])]
        ru_cuts = [x.start() for x in SENT.finditer(out_ru[j])]
        if not ru_cuts:
            continue
        k = sum(1 for c in de_cuts if c < m.start())
        pos = ru_cuts[min(k, len(ru_cuts) - 1)]
        if (j, pos) in used:
            continue
        bump("отсылка к сноске восстановлена по немецкому")
        return (j, _Span(pos))
    return None


def link_footnotes(de_blocks, ru_blocks):
    """Сноска в издании набрана внизу полосы под линейкой, а в извлечении она
    обычный абзац со звёздочкой посреди прозы. Связываем её с отсылкой
    разметкой markdown — тогда pandoc сделает настоящий \\footnote.

    ВНИМАНИЕ: меняет число блоков (определения уезжают в конец), поэтому
    включается отдельным ключом и ломает выравнивание с исходником.
    """
    out_de, out_ru, defs, used = [], [], [], set()
    n = 0
    for d, r in zip(de_blocks, ru_blocks):
        if not FOOTNOTE_START.match(r) or r.startswith("#"):
            out_de.append(d)
            out_ru.append(r)
            continue
        stars = FOOTNOTE_START.match(r).group(1)
        # Сносок на полосе бывает несколько, и отсылки к ним идут в том же
        # порядке. Брать ближайшую назад нельзя: первая сноска забирала бы
        # отсылку второй. Берём самую раннюю ещё не занятую.
        tgt = None
        for j in range(max(0, len(out_ru) - 6), len(out_ru)):
            if out_ru[j].startswith(("#", "<!--")) or FOOTNOTE_START.match(out_ru[j]):
                continue
            for m in FOOTNOTE_REF.finditer(out_ru[j]):
                if m.group(1) == stars and (j, m.start()) not in used:
                    tgt = (j, m)
                    break
            if tgt:
                break
        if not tgt:
            tgt = _ref_by_sentence(out_de, out_ru, used)
        if not tgt:
            bump("сноска без отсылки — оставлена абзацем")
            out_de.append(d)
            out_ru.append(r)
            continue
        n += 1
        j, m = tgt
        used.add((j, m.start()))
        out_ru[j] = out_ru[j][:m.start()] + f"[^fn{n}]" + out_ru[j][m.end():]
        body = FOOTNOTE_START.sub("", r).strip()
        defs.append((d, f"[^fn{n}]: {body}"))
        bump("сноска связана с отсылкой")
    for d, text in defs:
        out_de.append(d)
        out_ru.append(text)
    return out_de, out_ru


# -------------------------------------------------------------- терминология

# Готовые парадигмы: правило в карте задаёт основу и имя парадигмы, а не
# двадцать форм руками.
PARADIGMS = {
    "noun_m": ["", "а", "у", "ом", "е", "ы", "ов", "ам", "ами", "ах"],
    "noun_f": ["а", "ы", "е", "у", "ой", "ою", "", "ам", "ами", "ах"],
    "noun_n_ie": ["е", "я", "ю", "ем", "и", "й", "ям", "ями", "ях"],
    "adj": ["ый", "ого", "ому", "ым", "ом", "ая", "ой", "ую", "ое", "ые",
            "ых", "ыми", "о", "а", "у", "ий", "его", "ему", "им", "ем"],
}


def expand_pairs(spec):
    """Запись правила -> список пар (что заменить, на что).

    Формы задаются либо парадигмой:
        {"from": "разум", "to": "рассудок", "paradigm": "noun_m"}
    либо списком пар, когда парадигмы не хватает (чередование основы,
    словосочетание):
        {"pairs": [["существование", "наличное бытие"], ...]}
    """
    pairs = [tuple(p) for p in spec.get("pairs", [])]
    if spec.get("paradigm"):
        endings = PARADIGMS[spec["paradigm"]]
        a, b = spec["from"], spec["to"]
        pairs += [(a + e, b + e) for e in endings]
    return pairs


def compile_rules(rules):
    """[(имя, якорь, конкурент, регэксп, таблица, меняет_род)]"""
    out = []
    for spec in rules:
        pairs = expand_pairs(spec)
        if not pairs:
            continue
        # длинные формы раньше коротких, иначе «разум» съест «разумом»
        pairs = sorted(set(pairs), key=lambda p: -len(p[0]))
        # Регистр не различается: «Разум» в начале предложения — то же слово,
        # что «разум» в середине. Без этого правило молча пропускало каждое
        # первое слово фразы, а карта тома вынуждена была перечислять формы
        # дважды, с прописной и со строчной.
        rx = re.compile(r"\b(" + "|".join(re.escape(a) for a, _ in pairs)
                        + r")\b", re.IGNORECASE)
        # «(?!x)x» — заведомо непустой, но никогда не срабатывающий регэксп:
        # им обозначается «конкурента у этого термина нет»
        out.append((spec.get("name", spec.get("to", "?")),
                    re.compile(spec["anchor"]),
                    re.compile(spec.get("competitor") or r"(?!x)x"),
                    rx, {a.lower(): b for a, b in pairs}))
    return out


# Предлог «о/об» выбирается по первому звуку следующего слова, и замена
# термина этот звук меняет: «об объекте» -> «об предмете». Ошибка мелкая на
# вид, но она рассыпана по всей книге ровно там, где правило сработало.
OB_FIX = re.compile(r"\bоб(\s+)([бвгджзйклмнпрстфхцчшщ][а-яё]*)", re.I)
O_FIX = re.compile(r"\bо(\s+)(?=[аоуиэ])", re.I)
# «об» перед согласной законно в устойчивых оборотах и там, где предлог
# значит соприкосновение: «рука об руку», «удариться об стену».
OB_KEEP = {"руку", "стол", "стену", "стенку", "пол", "землю", "камень",
           "бок", "борт"}


def fix_prepositions(ru):
    """«о» или «об» — выбирается по первому звуку следующего слова.

    Это и обычная ошибка машинного перевода («речь идёт об существе»), и
    последствие замены термина: «об объекте» -> «об предмете», где звук
    поменялся, а предлог остался.
    """
    n0 = ru

    def ob(m):
        if m.group(2).lower() in OB_KEEP:
            return m.group(0)
        return ("О" if m.group(0)[:1].isupper() else "о") + m.group(1) + m.group(2)

    ru = OB_FIX.sub(ob, ru)
    ru = O_FIX.sub(lambda m: ("Об" if m.group(0)[:1].isupper() else "об")
                   + m.group(1), ru)
    if ru != n0:
        bump("предлог о/об согласован")
    return ru


def fix_terms(de, ru, rules):
    """Заменяем только там, где немецкий блок содержит якорь и НЕ содержит
    конкурента: иначе неизвестно, какой из двух терминов переводит слово."""
    for name, yes, no, rx, table in rules:
        if not yes.search(de) or no.search(de):
            continue

        def rep(m, _name=name, _table=table):
            bump("терм:" + _name)
            src = m.group(1)
            dst = _table[src.lower()]
            # «Разум» в начале предложения должен остаться заглавным
            if src[:1].isupper() and dst[:1].islower():
                dst = dst[:1].upper() + dst[1:]
            return dst

        ru = rx.sub(rep, ru)
    return ru


# --------------------------------------------------- терминология со сменой рода
#
# Это самое опасное место всей пост-обработки. На томе 6 такие правила трижды
# дали тихую порчу русского языка, и каждый раз её замечала не сборка, а
# отдельная проверка:
#
#   · «логический» -> «логическее» вместо «логическое» (после заднеязычных и
#     шипящих средний род на «-ое»);
#   · «представляет собой отражение» -> «представляет собой рефлексия»
#     (винительный среднего рода совпадает с именительным, женского — нет);
#   · «разумный вывод возможен» -> «разумное умозаключение возможен»
#     (смена рода не достала до сказуемого).
#
# Отсюда правило, которому подчинено всё ниже: ЕСЛИ СОГЛАСОВАТЬ ОПРЕДЕЛЕНИЕ
# ИЛИ СКАЗУЕМОЕ НЕЛЬЗЯ — ЗАМЕНА ПРОПУСКАЕТСЯ ЦЕЛИКОМ. Наполовину сделанная
# замена хуже несделанной: несделанную видно по глоссарию, а сделанную
# наполовину — только глазами.

PRON_M2N = {
    "этот": "это", "тот": "то", "такой": "такое", "какой": "какое",
    "данный": "данное", "каждый": "каждое", "всякий": "всякое",
    "один": "одно", "любой": "любое", "который": "которое", "иной": "иное",
    "свой": "своё", "наш": "наше", "ваш": "ваше", "весь": "всё",
    "сам": "само", "самый": "самое", "первый": "первое", "второй": "второе",
}
IRREG_M2N = {"третий": "третье", "весь": "всё", "чей": "чьё"}
ADJ_M2N = {"ый": "ое", "ий": "ее", "ой": "ое"}
# После ЗАДНЕЯЗЫЧНОЙ основы средний род на «-ое»: «логический» ->
# «логическое», а не «логическее» (это и была регрессия тома 6).
#
# Шипящие сюда НЕ входят, хотя в исходном правиле тома 6 они стояли: после
# них как раз «-ее» — «общий» -> «общее», «свежий» -> «свежее», «горячий» ->
# «горячее». С ними в списке правило чинило одну ошибку и заводило другую.
HARD_STEM = ("к", "г", "х")

# Винительный падеж среднего рода совпадает с именительным, женского — нет.
# Под управлением винительного замена среднего на женский даёт «представляет
# собой рефлексия». Такие места не трогаем вовсе.
ACC_GOVERNOR = {"собой", "собою", "через", "сквозь", "про", "в", "на", "за",
                "под", "об", "о"}
# «находят своё отражение» — тоже винительный, только управляет им глагол.
# Притяжательное перед словом — надёжный признак дополнения.
POSSESSIVE_NEUT = {"своё", "свое", "наше", "ваше", "моё", "мое", "твоё",
                   "твое", "его", "их", "её", "ее"}

# Сказуемое мужского рода, которое смена рода обязана утянуть за собой.
# Прошедшее время на «-л» переводится в средний по правилу; краткое
# прилагательное — нет (беглая гласная: «возможен» -> «возможно», но
# «ясен» -> «ясно»), поэтому для него закрытый список, а всё, что в него не
# попало, служит СИГНАЛОМ ОТКАЗА: замену на таком месте не делаем.
PAST_M = re.compile(r"^([а-яё]{2,})л(ся)?$")
SHORT_ADJ_M2N = {
    "возможен": "возможно", "невозможен": "невозможно",
    "необходим": "необходимо", "равен": "равно", "таков": "таково",
    "ясен": "ясно", "известен": "известно", "определён": "определено",
    "определен": "определено", "положен": "положено", "снят": "снято",
    "дан": "дано", "нужен": "нужно", "важен": "важно", "верен": "верно",
    "истинен": "истинно", "тождествен": "тождественно",
    "конечен": "конечно", "бесконечен": "бесконечно",
}
# Похоже на краткое прилагательное мужского рода, но в списке его нет.
SHORT_ADJ_LOOKS_M = re.compile(r"^[а-яё]{4,}(?:ен|ён|им|ым|ов|ин)$")
LOOKAHEAD_WORDS = 3


def keepcase(src, dst):
    return dst[:1].upper() + dst[1:] if src[:1].isupper() else dst


def adj_m2n(mod):
    """Мужской род прилагательного -> средний, с оглядкой на основу."""
    low = mod.lower()
    if low in IRREG_M2N:
        return keepcase(mod, IRREG_M2N[low])
    end = low[-2:]
    if end not in ADJ_M2N:
        return None
    if end == "ий" and low[:-2].endswith(HARD_STEM):
        return mod[:-2] + "ое"
    return mod[:-2] + ADJ_M2N[end]


def _modifier_m2n(mod):
    """Определение перед словом -> средний род, или None, если нельзя."""
    low = mod.lower()
    if low in PRON_M2N:
        return keepcase(mod, PRON_M2N[low])
    if low in IRREG_M2N:
        return keepcase(mod, IRREG_M2N[low])
    if low.endswith("ой"):
        # «представляет собой вывод»: на «-ой» кончаются и мужские
        # прилагательные, и творительный женского — различить нельзя
        return None
    if low[-2:] in ADJ_M2N and len(low) >= 5:
        return adj_m2n(mod)
    return mod          # не определение (предлог, глагол, запятая) — не трогаем


def _predicate_m2n(words):
    """Сказуемые мужского рода в окне после слова.

    -> (список правок, можно ли вообще менять). Второе False, если нашлось
    сказуемое, которое согласовать не умеем: тогда замену надо пропустить.
    """
    fixes = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in SHORT_ADJ_M2N:
            fixes.append((i, keepcase(w, SHORT_ADJ_M2N[low])))
            continue
        m = PAST_M.match(low)
        if m:
            neu = m.group(1) + "ло" + ("сь" if m.group(2) else "")
            fixes.append((i, keepcase(w, neu)))
            continue
        if SHORT_ADJ_LOOKS_M.match(low):
            return fixes, False
    return fixes, True


WORD_RE = re.compile(r"[А-Яа-яЁё]+")


def replace_m2n(ru, forms, counter_name):
    """Заменить мужское слово средним, согласовав определение и сказуемое.

    forms — {мужская форма: средняя форма}. Меняем только именительный и
    винительный: в косвенных падежах определение мужского и среднего рода
    совпадает, и согласовывать нечего (эти формы идут обычным правилом).
    """
    forms = {k.lower(): v for k, v in forms.items()}
    keys = sorted(forms, key=len, reverse=True)
    # Хвост входит в само совпадение: сказуемое надо переписать вместе со
    # словом, а за границей совпадения текст менять нельзя. Хвост берётся
    # только до ближайшего знака препинания — за точкой уже другая фраза, и
    # её сказуемое к нашему подлежащему отношения не имеет.
    rx = re.compile(r"(?:([А-Яа-яЁё]+)(\s+))?\b("
                    + "|".join(re.escape(k) for k in keys)
                    + r")\b((?:\s+[А-Яа-яЁё]+){0,%d})" % LOOKAHEAD_WORDS,
                    re.IGNORECASE)

    def rep(m):
        mod, sp, word, tail = m.group(1), m.group(2), m.group(3), m.group(4)
        new_mod = mod
        if mod:
            new_mod = _modifier_m2n(mod)
            if new_mod is None:
                return m.group(0)           # согласовать нельзя — не трогаем
        parts = tail.split()
        fixes, ok = _predicate_m2n(parts)
        if not ok:
            return m.group(0)
        for i, new in fixes:
            parts[i] = new
        new_tail = ("" if not parts else " " + " ".join(parts))
        bump("терм:" + counter_name)
        if fixes:
            bump("сказуемое согласовано по роду", len(fixes))
        return ((new_mod + sp if mod else "")
                + keepcase(word, forms[word.lower()]) + new_tail)

    return rx.sub(rep, ru)


PRON_N2F = {
    "это": "эта", "то": "та", "такое": "такая", "какое": "какая",
    "одно": "одна", "которое": "которая", "всё": "вся", "все": "вся",
    "наше": "наша", "ваше": "ваша", "своё": "своя", "свое": "своя",
    "каждое": "каждая", "всякое": "всякая", "самое": "самая", "само": "сама",
    "этого": "этой", "того": "той", "такого": "такой", "которого": "которой",
    "своего": "своей", "нашего": "нашей", "одного": "одной",
    "этому": "этой", "тому": "той", "такому": "такой", "которому": "которой",
    "своему": "своей", "нашему": "нашей", "одному": "одной",
    "этим": "этой", "тем": "той", "таким": "такой", "которым": "которой",
    "своим": "своей", "нашим": "нашей", "одним": "одной",
}
# Определение среднего рода, для которого правила пересчёта в женский нет.
# Встретили — замену пропускаем: «наше отражение» -> «наше рефлексия» хуже,
# чем оставленное «отражение».
ADJ_NEUT_ENDS = ("ое", "ее", "ого", "его", "ому", "ему", "ым", "им")
# Глаголы, управляющие винительным: «имеет отражение», «находят отражение».
# У среднего рода винительный совпадает с именительным, у женского — нет.
ACC_VERBS = {"имеет", "имеют", "имел", "имела", "находит", "находят",
             "находит", "даёт", "дает", "дают", "получает", "получают",
             "представляет", "представляют", "составляет", "составляют",
             "образует", "образуют", "означает", "означают", "есть"}


def replace_n2f(ru, cases, counter_name):
    """Средний род -> женский, по падежам, с оглядкой на винительный.

    cases — [(средняя форма, женская форма, {оконч. определения: женское})].
    Предложный падеж в список не входит намеренно: определение на «-ом/-ем»
    неотличимо от существительного («процессом отражения»), и правка портила
    бы текст.
    """
    for neu, fem, adj_map in cases:
        rx = re.compile(r"(?:([А-Яа-яЁё]+)(\s+))?\b" + re.escape(neu) + r"\b",
                        re.IGNORECASE)

        def rep(m, _fem=fem, _adj=adj_map):
            mod, sp = m.group(1), m.group(2)
            if mod:
                low = mod.lower()
                if low in ACC_GOVERNOR or low in POSSESSIVE_NEUT \
                        or low in ACC_VERBS:
                    # винительный: «представляет собой отражение»,
                    # «находят своё отражение» — женский род здесь потребовал
                    # бы другой формы, и замена дала бы рассогласование
                    return m.group(0)
                if low in PRON_N2F:
                    mod = keepcase(mod, PRON_N2F[low])
                else:
                    # окончания бывают и трёхбуквенные («ого», «ому»);
                    # смотреть только две последние буквы нельзя — иначе
                    # родительный и дательный с прилагательным проскакивают
                    # БЕЗ согласования, а это ровно то, чего нельзя допускать
                    end = next((e for e in (low[-3:], low[-2:]) if e in _adj),
                               None)
                    if end and len(low) >= 5:
                        mod = mod[:-len(end)] + _adj[end]
                    elif any(low.endswith(e) for e in ADJ_NEUT_ENDS):
                        return m.group(0)   # определение есть, правила нет
            bump("терм:" + counter_name)
            word = m.group(0)[len(mod) + len(sp):] if mod else m.group(0)
            return (mod + sp if mod else "") + keepcase(word, _fem)

        ru = rx.sub(rep, ru)
    return ru


GENDER_ENGINES = {"m2n": replace_m2n, "n2f": replace_n2f}


def apply_gender_rules(de, ru, rules):
    """Правила со сменой рода: те же якорь и конкурент, что у обычных."""
    for name, yes, no, engine, data in rules:
        if not yes.search(de) or no.search(de):
            continue
        ru = engine(ru, data, name)
    return ru


def compile_gender_rules(specs):
    out = []
    for spec in specs:
        eng = spec.get("gender")
        if eng not in GENDER_ENGINES:
            continue
        data = (spec["forms"] if eng == "m2n"
                else [tuple(c) if len(c) == 3 else (c[0], c[1], {})
                      for c in spec["cases"]])
        if eng == "n2f":
            data = [(a, b, dict(d)) for a, b, d in data]
        out.append((spec.get("name", "?"), re.compile(spec["anchor"]),
                    re.compile(spec.get("competitor") or r"(?!x)x"),
                    GENDER_ENGINES[eng], data))
    return out


# ------------------------------------------------------------------ main

def blocks_of(path):
    return [b for b in re.split(r"\n\s*\n",
            Path(path).read_text(encoding="utf-8"))
            if b.strip()]


def find_parts(work_dir):
    manifest = load_manifest(work_dir)
    return [(n, str(inside(work_dir, row["path"])), str(inside(work_dir, row["output"])))
            for n, row in enumerate(manifest["parts"], 1)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir")
    ap.add_argument("--structure", default=None)
    ap.add_argument("--terms", default=None,
                    help="JSON со списком правил терминологии; по умолчанию "
                         "берётся structure.json -> postfix.terms")
    ap.add_argument("--no-typography", action="store_true")
    ap.add_argument("--footnotes", action="store_true",
                    help="связать сноски с отсылками. МЕНЯЕТ ЧИСЛО БЛОКОВ — "
                         "после этого assemble_ru_book уже не сможет "
                         "восстановить заголовки по исходнику, поэтому "
                         "включать только на последнем проходе")
    ap.add_argument("--dry-run", action="store_true",
                    help="ничего не писать, только посчитать")
    ap.add_argument("--corrections", help="reviewed exact block replacements (JSON)")
    a = ap.parse_args()
    if a.footnotes:
        ap.error("--footnotes changes block alignment; use reviewed corrections on assembled text instead")

    cfg = {}
    sj = a.structure or os.path.join(a.work_dir, "structure.json")
    if os.path.exists(sj):
        cfg = json.load(open(sj, encoding="utf-8"))
    post = cfg.get("postfix") or {}
    rules_spec = post.get("terms") or []
    if a.terms and os.path.exists(a.terms):
        rules_spec = json.load(open(a.terms, encoding="utf-8"))
    rules = [r for r in rules_spec if not r.get("gender")]
    grules = [r for r in rules_spec if r.get("gender")]
    openers = post.get("tier_openers") or []
    print(f"правил терминологии: {len(rules)}"
          + (f", со сменой рода: {len(grules)}" if grules else "")
          + (f", зачинов яруса: {len(openers)}" if openers else ""))

    parts = find_parts(a.work_dir)
    if not parts:
        sys.exit(f"!! нет book.partN.md в {a.work_dir}")

    findings = []
    for _, src, dst in parts:
        check_result(src, dst)
    corrections = json.loads(Path(a.corrections).read_text(encoding="utf-8")) if a.corrections else []
    all_de = [b for _, src, _ in parts for b in blocks_of(src)]
    all_ru = [b for _, _, dst in parts for b in blocks_of(dst)]
    checked, correction_log = apply_corrections(all_de, all_ru, corrections)
    offset = 0
    for n, src, dst in parts:
        if not os.path.exists(dst):
            print(f"!! часть {n}: перевода нет — пропущена")
            continue
        check_result(src, dst)
        de, ru = blocks_of(src), blocks_of(dst)
        original_ru = list(ru)
        ru = checked[offset:offset + len(ru)]
        offset += len(ru)
        if len(de) != len(ru):
            sys.exit(f"!! часть {n}: блоки разошлись ({len(de)} против "
                     f"{len(ru)}). Правка по немецкому якорю невозможна.")
        out = []
        for d, r in zip(de, ru):
            if r.startswith("<!--"):
                out.append(r)
                continue
            findings.extend(terminology_findings(d, r, rules_spec))
            findings.extend(term_guard_findings(d, r, cfg.get("term_guards", [])))
            findings.extend(dict(f, target=r) for f in ocr_findings(r))
            if "…" in r or "..." in r:
                findings.append({"kind": "ellipsis", "source": d, "target": r,
                                 "status": "warning", "action": "review seam; punctuation retained"})
            r = fix_prepositions(r)
            r = mark_tier_openers(r, openers)
            if not a.no_typography:
                r = fix_typography(r)
            r = escape_false_lists(r)
            out.append(r)
        if a.footnotes:
            de, out = link_footnotes(de, out)
        if not a.dry_run:
            edits = [{"block": i, "before": before, "after": after,
                      "reason": "typography/profile or reviewed exact correction"}
                     for i, (before, after) in enumerate(zip(original_ru, out)) if before != after]
            if edits:
                record_edit(src, dst, "\n\n".join(out) + "\n", edits,
                            config={"postfix": post, "corrections": corrections})
        print(f"часть {n}: блоков {len(out)}"
              + (" (не записано, --dry-run)" if a.dry_run else ""))

    if not a.dry_run:
        write_json(Path(a.work_dir) / "editorial.review.json", {
            "schema": 1, "status": "warning" if findings else "passed",
            "findings": findings, "corrections": correction_log, "semantic_review": "not_run"})
    print("\n--- что сделано ---")
    for k, v in STAT.most_common():
        print(f"  {v:6d}  {k}")
    if not STAT:
        print("  ничего")
    return 0


if __name__ == "__main__":
    sys.exit(main())
