# -*- coding: utf-8 -*-
"""Сборка book.md из постраничного OCR фрактуры — со структурой книги.

Заменяет связку prepare_ocr_md.py + rebuild_book_md.py для готических томов.
Чем отличается от них (это и были причины провала прогона Logik 1812):

* Колонтитул и настоящий заголовок больше не путаются. Прежний
  strip_running_heads() резал по слову ("Kapitel", "Abschnitt", "Vorrede"),
  то есть выбрасывал ЗАГОЛОВКИ ГЛАВ вместе с колонтитулами, и книга уезжала
  в вёрстку без единой главы. Здесь строка сперва проверяется на заголовок и
  только потом — на колонтитул: «Erster Abschnitt.» вверху полосы это
  заголовок, а «152 - Erstes Buch. I. Abschnitt.» — колонтитул, потому что
  несёт номер страницы.
* Фронт-материя (страницы Google, библиотечные штампы, титул, издательская
  «Inhaltsanzeige») отрезается диапазоном страниц, а не совпадением префикса
  блока: прежний фильтр ловил только первый абзац дисклеймера, а остальное
  переводилось и открывало книгу.
* Переносы склеиваются с УДАЛЕНИЕМ дефиса (прежняя замена "-\\s+" -> "-"
  дефис сохраняла, и в переводчик уходило "unmittelba-ren").
* Абзац, разорванный границей страницы, снова становится одним абзацем.
* Длинное «ſ» и лигатуры фрактуры нормализуются: модель перевода не обязана
  знать, что "Diſcretion" — это "Discretion".

Номер печатной страницы сохраняется блоком-маркером <!--N-->. В нём нет букв,
поэтому translate.py пропускает такой блок нетронутым (is_translatable), и
привязка перевода к страницам оригинала переживает перевод.

Использование:
    python scripts/build_ocr_md.py <work_dir> [--offset -48]
        [--structure book_structure.json] [--parts 300] [--no-page-marks]
"""
import argparse
import bisect
import difflib
import itertools
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from provenance import create_manifest, archive_stale, write_json, sha_file, sha_text, atomic_text

# reconfigure, а не подмена sys.stdout обёрткой: модуль импортируют другие
# скрипты (make_searchable_pdf), и вторая обёртка поверх первой закрывает
# нижележащий буфер — «I/O operation on closed file» на первом же print
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- нормализация

LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "ﬆ": "st", "æ": "ae", "Æ": "Ae",
}


def normalize(text):
    """Фрактурные глифы -> обычный немецкий, который понимает переводчик."""
    text = text.replace("ſ", "s")
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    # Лигатура "ch" во фрактуре регулярно приходит как "<" ("Wissens<aft",
    # "dis<reter"). Заменяем только внутри слова, чтобы не тронуть кавычки.
    text = re.sub(r"(?<=[A-Za-zÄÖÜäöüß])<+(?=[A-Za-zÄÖÜäöüß])", "ch", text)
    # "ck" во фрактуре приходит как "F" между строчными ("zurüFgekehrt").
    text = re.sub(r"(?<=[a-zäöüß])F(?=[a-zäöüß])", "ck", text)
    # Заглавные I и J во фрактуре — один глиф; перед согласной это всегда I
    # ("Jnhalt" -> "Inhalt", "Jst" -> "Ist"), перед гласной остаётся J ("Jahr").
    text = re.sub(r"\bJ(?=[bcdfghjklmnpqrstvwxzß])", "I", text)
    return text


# ------------------------------------------------- длинное s, прочитанное как f

WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
F_RUN = re.compile(r"[fF]+")
MAX_F_RUNS = 3
LONG_S_RATIO = 5         # во сколько раз s-форма должна перевешивать f-форму
LONG_S_MIN = 10          # и сколько раз встретиться, чтобы ей верить


def _s_variants(word):
    """Слово с заменой части букв f на s (регистр сохраняется)."""
    runs = [m.span() for m in F_RUN.finditer(word)][:MAX_F_RUNS]
    if not runs:
        return
    for mask in itertools.product([0, 1], repeat=len(runs)):
        if not any(mask):
            continue
        out, prev = [], 0
        for (lo, hi), take in zip(runs, mask):
            out.append(word[prev:lo])
            chunk = word[lo:hi]
            out.append("".join("S" if ch == "F" else "s" for ch in chunk)
                       if take else chunk)
            prev = hi
        out.append(word[prev:])
        yield "".join(out)


def fix_long_s(text):
    """Чинит слова, где длинное «ſ» распозналось как «f» («fich» -> «sich»).

    Список правок не задаётся руками: он выводится из частот самой книги.
    Форма через s принимается, только если она в LONG_S_RATIO раз обычнее
    и встречается не реже LONG_S_MIN — поэтому настоящие немецкие слова на f
    («für», «fest», «Form») остаются нетронутыми: их s-двойников в книге нет.
    """
    freq = Counter(WORD_RE.findall(text))
    mapping = {}
    for word, cnt in freq.items():
        best, best_cnt = None, 0
        for cand in _s_variants(word):
            c = freq.get(cand, 0)
            if c > best_cnt:
                best, best_cnt = cand, c
        if best and best_cnt >= max(LONG_S_MIN, LONG_S_RATIO * cnt):
            mapping[word] = best
    if not mapping:
        return text, 0, {}
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, mapping), key=len,
                                             reverse=True)) + r")\b")
    n = [0]

    def sub(m):
        n[0] += 1
        return mapping[m.group(1)]

    return rx.sub(sub, text), n[0], mapping


# --------------------------------------------------- лигатура tz, читанная как ß

# Во фрактуре «tz» набирается лигатурой, и OCR регулярно читает её как «ß»
# («Zusaß» вместо «Zusatz», «geseßt» вместо «gesetzt»). Правило то же, что у
# fix_long_s: никаких ручных списков, решение по частотам самой книги. Форма
# с «ß» заменяется на форму с «tz», ТОЛЬКО если «tz»-двойник реально
# встречается в тексте — настоящие ß-слова («groß», «Straße», «nuß») не
# тронутся, их tz-двойников в книге нет.
def fix_tz_ligature(text):
    freq = Counter(WORD_RE.findall(text))
    mapping = {}
    for word, cnt in freq.items():
        if "ß" not in word:
            continue
        cand = word.replace("ß", "tz")
        if freq.get(cand, 0):
            mapping[word] = cand
    if not mapping:
        return text, 0, {}
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, mapping), key=len,
                                             reverse=True)) + r")\b")
    n = [0]

    def sub(m):
        n[0] += 1
        return mapping[m.group(1)]

    return rx.sub(sub, text), n[0], mapping


# -------------------------------------------------------------------- заголовки

ORD_N = r"(?:Erstes|Zweytes|Zweites|Drittes|Viertes|Fünftes)"
ORD_M = r"(?:Erster|Zweyter|Zweiter|Dritter|Vierter|Fünfter)"

# Заголовки уровня книги/отдела/главы. На них похожи колонтитулы
# ("Erstes Buch. I. Abschnitt." стоит наверху трёхсот полос), поэтому том,
# у которого структура задана картой inject, отключает их автопоиск флагом
# structural_from_inject_only.
STRUCTURAL = [
    (1, re.compile(rf"^\W{{0,4}}{ORD_N}\W{{0,3}}\s*Buch\b")),
    (2, re.compile(rf"^\W{{0,4}}{ORD_M}\W{{0,3}}\s*Abschnitt\b")),
    (3, re.compile(rf"^\W{{0,4}}{ORD_N}\W{{0,3}}\s*Kapitel\b")),
]
# Мелкие заголовки внутри главы. «Anmerkung» названия не имеет — подхватывать
# следующую строку нельзя, иначе в заголовок уедет первая строка примечания.
MINOR = [
    # «Anmerkung» приходит и как «Anmerkand 4.», и как «Anmerkung 1, ,» —
    # хвост и окончание слова допускаем любые
    (4, re.compile(r"^\W{0,4}Anmerk[a-zä]{0,6}\s*\d?[\s.,:;'\"|-]*$"), False),
    (4, re.compile(r"^\W{0,4}[ABC]\s*[.,]"), True),
]

MAX_HEAD_LEN = 90
TITLE_MAX_LEN = 46
MIN_ABC_TITLE = 8


def heading_match(line, allow_structural=True):
    """(уровень, длина префикса, подхватывать ли название) или (0, 0, False)."""
    s = line.strip()
    if not s or len(s) > MAX_HEAD_LEN:
        return 0, 0, False
    if allow_structural:
        for lvl, rx in STRUCTURAL:
            m = rx.match(s)
            if m:
                return lvl, m.end(), True
    for lvl, rx, wants_title in MINOR:
        m = rx.match(s)
        if m:
            return lvl, m.end(), wants_title
    return 0, 0, False


def good_abc_title(title):
    """«A. Die reine Quantität» — заголовок; «B. Kno», «A. SSSEELEN» — шум,
    «B. eine Masse als Gewicht» — строка абзаца, начатая с литеры пункта."""
    if len(title) < MIN_ABC_TITLE or not re.search(r"[a-zäöüß]{3,}", title):
        return False
    first = re.search(r"[A-Za-zÄÖÜäöüß]", title)
    return bool(first and first.group().isupper())


def is_title_line(line):
    """Строка-подзаголовок под «Erstes Kapitel»: короткая, не с новой мысли."""
    s = line.strip()
    if not s or len(s) > TITLE_MAX_LEN:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]{3,}", s):
        return False
    if HYPHEN_END.search(s):
        return False
    first = re.search(r"[A-Za-zÄÖÜäöüß]", s)
    return bool(first and first.group().isupper())


# ------------------------------------------------------------------ колонтитул

PAGE_NUM = re.compile(r"(?<!\d)\d{1,4}(?!\d)")
ROMAN_ONLY = re.compile(r"^[IVXLCivxlc]{1,7}$")

HEAD_WORDS = re.compile(
    r"(vorrede|borred|worred|worvede|vorved|einleitung|einfeitung|einseitung|"
    r"cinleitung|eilleitu|einleitn|inhaltsanzeige|fnhaltsanzeige|erstes buch|"
    r"das seyn|das sepn|das syn|quantit|huantit|qualit|hualit|maass|das maas|"
    r"das maaß|allgemeine eintheilung|abschnitt|abschni)", re.IGNORECASE)


# Служебные слова: в колонтитуле их не бывает (это заголовочная строка —
# «Erster Theil. Griechische Philosophie»), а в строке набора почти всегда
# есть. Без этой проверки правило по длине срезало строки доказательств
# вроде «- ED, daß der Rest CE << AB; CE messe. 144.6».
# Только те, что в заголовке не встречаются. Артикли и предлоги («des», «vom»,
# «der») сюда НЕ входят: «Philosophie des Sokrates» — вполне колонтитул.
FUNCTION_WORDS = {
    "ist", "sind", "war", "waren", "nicht", "sich", "dass", "daß", "auch",
    "aber", "oder", "wenn", "nur", "noch", "man", "wie", "als", "so",
    "dieser", "diese", "dieses", "welche", "welcher", "hat", "haben",
    "wird", "werden", "kann", "muss", "muß", "es", "ihn", "ihm", "ihr",
}


def has_function_word(s):
    return any(w.lower() in FUNCTION_WORDS
               for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", s))


def has_page_number(s):
    if PAGE_NUM.search(s):
        return True
    # одиночные i/v/x/l/c/d/m слишком часто выпадают шумом OCR, чтобы
    # считать их римским номером страницы
    return any(ROMAN_ONLY.match(t) and len(t) >= 2
               for t in re.findall(r"[A-Za-z]+", s))


EXTRA_HEAD_WORDS = []      # заполняется из structure.json (running_head_words)
CUT_FROM = ""              # заполняется из structure.json (cut_from)


def is_running_head(line):
    """Колонтитул наверху полосы. Вызывается ТОЛЬКО после проверки на заголовок."""
    s = line.strip()
    if not s:
        return False
    # фразы колонтитула, объявленные для тома: у каждого издания они свои,
    # и общим списком их не покрыть. Проверка раньше лимита длины: колонтитул
    # с OCR-порчей «A. Erste Stellung des Gevankens zur Objeckivität, '73»
    # длиннее 64 знаков, но это всё равно шапка полосы.
    low = s.lower()
    if any(w in low for w in EXTRA_HEAD_WORDS):
        return True
    if len(s) > 64:
        return False
    if len(re.findall(r"[A-Za-zÄÖÜäöüß]", s)) <= 2:
        return True
    if HEAD_WORDS.search(s) and (has_page_number(s) or len(s) <= 40):
        return True
    if has_page_number(s) and len(re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", s)) <= 3:
        return True
    # Колонтитул бывает длиннее трёх слов («140 Erster Theil. Griechische
    # Philosophie»), и по составу слов его не отличить. Отличает длина: это
    # ЗАГОЛОВОЧНАЯ строка, она заметно короче полной строки набора (55-70
    # знаков). Номер страницы + короткая строка вверху полосы = колонтитул.
    if (has_page_number(s) and len(s) <= RH_MAX_LEN
            and not has_function_word(s)):
        return True
    return False


def looks_like_junk(line):
    """Обрезок рамки, штамп, шум сканера: коротко и без нормального слова."""
    s = line.strip()
    return len(s) < 30 and not re.search(r"[a-zäöüß]{3,}", s)


# Номер параграфа во фрактуре: «§. 86.» Tesseract читает как «s. 86.»,
# «6. 84.», «8.5.», «Ss. 104.», «“A g. 96.» — глиф § вырождается, цифра нет.
# Такая строка короче 30 знаков и без трёхбуквенного слова, поэтому
# looks_like_junk молча выбрасывал её: у «Энциклопедии» так пропали ВСЕ 244
# номера, а вместе с ними и возможность сослаться на место в книге.
# Хвост строки тоже бывает засорён обрывками букв («s. 165. oo.», «s. 238. t»),
# поэтому после числа допускаем и короткие буквенные огрызки.
PARA_NUM = re.compile(r"^(.{0,8}?)(?<!\d)(\d{1,4})(?!\d)"
                      r"(?:[\W_]|\b[a-zA-Z]{1,2}\b){0,8}$")
# «§» вырождается ещё и в «ß» («ß. 217.») — начертания похожи
PARA_GLYPH = re.compile(r"[sSfF§$65803gGbß]")
PARA_MAXLEN = 18
PARAGRAPH_NUMBERS = False       # включается ключом --paragraph-numbers
PARAGRAPH_BARE = False          # structure.json: paragraph_bare_numbers
EDGE_LINES = 3                  # сколько строк у краёв полосы считаем краем


def paragraph_number(line, bare_ok=False):
    """Номер параграфа, если строка — это он, иначе None.

    bare_ok разрешает строку из ОДНОГО ЧИСЛА, без следов глифа «§». Это нужно
    «Энциклопедии» 1817: её скан хуже, и глиф теряется целиком — от «§. 15.»
    остаётся «15». Само по себе такое послабление опасно, потому что ровно
    так же выглядит колонцифра: на полосах 26–32 голые числа 12, 13, 15, 16,
    18 — это номера печатных страниц, а не параграфы. Отличить их по
    символам нельзя, и решает единственная геометрия, которую даёт простой
    текст: колонцифра стоит у края полосы, номер параграфа — в её середине.
    Поэтому bare_ok передаётся только для строк вдали от краёв, а окончательно
    кандидата всё равно проверяет фильтр монотонности.

    Четырёхзначное чтение не обрезается: это может быть год или иной текст.
    Исправление сомнительного номера требует проверенного книжного якоря.
    """
    s = line.strip()
    if not PARAGRAPH_NUMBERS or not s or len(s) > PARA_MAXLEN:
        return None
    m = PARA_NUM.match(s)
    if not m:
        return None
    prefix = m.group(1)
    if not PARA_GLYPH.search(prefix):
        # без глифа принимаем только голое число: префикс из одной пунктуации
        if not (bare_ok and PARAGRAPH_BARE
                and not re.search(r"[A-Za-zÄÖÜäöüß]", prefix)):
            return None
    n = int(m.group(2))
    # Never truncate a year/four-digit OCR reading to invent a paragraph.
    return n if 1 <= n <= 999 else None


# --------------------------------------------------------------- сборка страниц

TERMINAL = tuple(".!?:\"')")
# Знак переноса во фрактуре — двойной дефис, и Tesseract отдаёт его то как
# "-", то как "»"/"«". Замерено по тому корпусу: строка на "»" продолжается
# со строчной буквы в 202 случаях против 14, на "«" — 116 против 7, так что
# это перенос, а не кавычка. Пока "»" числился концом предложения, абзацы
# рвались на разворотах, а слова оставались разорванными («Darstel» Jung»).
# A word fragment must precede the glyph: a spaced sentence dash is punctuation.
HYPHEN_END = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])[-‐‑‒–—=⸗~»«]$")
HEAD_SCAN_LINES = 3          # сколько верхних строк смотрим на колонтитул
RH_MAX_LEN = 52              # длиннее — это уже строка набора, не колонтитул

# Нижний колонтитул фрактурных книг: внизу полосы «123 Erster Theil.
# Griechische Philosophie.» (номер страницы + заголовок отдела). OCR сливает
# его с текстом, и строка-футер может стоять в любом месте полосы, — отсекаем
# по контуру: мусор-префикс + заголовок-стойка + Griechische + Phil…
# (порча OCR обширная: Theil/Theit/Thell/Thril/Weil, Phikosophir и т.п.)
FOOTER_RE = re.compile(
    r"^\d{0,4}[\s\-~=|%)/’'\"*\u00BB\u00AB.]{0,8}"
    r"[A-Za-zÄÖÜäöüß]{0,14}?"
    r"[TW]?[hei1ltxrk]{0,6}[.,:;]?[\s’'\"\u00BB\u00AB]{0,4}"
    r"Griechische[\s.,:;]{0,4}Ph[i1][l1tk][aoe]", re.UNICODE)

# Нижний колонтитул Энциклопедии 1843/1847: «Encyklopädie. II. Thl. 2. Aufl. 273»
# и «Encyklopädie. 1. Thl. 2te Aufl. 15» (название издания + номер печатной
# страницы). OCR врёт в обозначении тома («I1», «I»), в суффиксе номера
# издания («2», «2te», «2e») и знаках препинания — терпим всё до «Aufl».
ENCYC_FOOTER = re.compile(
    r"^Encyklop[aä]die[\W]*[IVXLC1-4l]*[\W]*"
    r"Th[l1i!]*[\W]*\d+(?:[te]{1,2})?[\W]*"
    r"(?:Au|An)[flisnck]*[\W]*[0-9IVXLC]*[\W]*$", re.UNICODE)


def join_hyphen(prev, nxt):
    """Склейка через перенос: со строчной — слово срастается без дефиса,
    с заглавной — это составное слово, дефис остаётся ("Selbst-Bestimmung")."""
    # Suspended compounds (Halt- und Wesenloses) are not word hyphenation.
    # Keep the printed hyphen before a standalone conjunction, not e.g. "unter".
    if re.match(r"(?:und|oder|bzw\.)\s", nxt):
        return prev + " " + nxt
    stem = HYPHEN_END.sub("", prev)
    return stem + nxt if nxt[:1].islower() else stem + "-" + nxt


def join_lines(lines):
    """Строки одного абзаца -> один абзац."""
    out = ""
    for i, ln in enumerate(lines):
        if i == 0:
            out = ln
            continue
        if HYPHEN_END.search(out):
            out = join_hyphen(out, ln)
        else:
            out = out + " " + ln
    return re.sub(r"[ \t]{2,}", " ", out).strip()


BODY_LINE_MIN = 40           # длина строки, с которой начинается сплошной текст


def drop_display_heading(lines):
    """Срезать шапку шмуцтитула.

    На странице, где начинается отдел или глава, заголовок набран разрядкой и
    распознаётся обрывками («Erstes Kapitel», «Seynm», «Das Seyn.»). Сам
    заголовок мы ставим из карты structure.json, поэтому эти обрывки — лишние:
    иначе они висят отдельными абзацами прямо под заголовком. Отбрасываем всё
    до первой строки нормальной длины.
    """
    kept = []
    for i, ln in enumerate(lines):
        if len(ln) >= BODY_LINE_MIN:
            return kept + lines[i:]
        # номер параграфа стоит ровно здесь, между шмуцтитулом и текстом,
        # и он короткий — иначе §1 и §19 гибли вместе с обрывками заголовка
        if paragraph_number(ln) is not None:
            kept.append(ln)
    return lines


UNIT_START = re.compile(r"^\s*(?:Zusatz|Anmerkung)\b")


def prepare_ocr_page(raw, page_no, cfg):
    """Book-owned corrections before segmentation, with original-byte identity.

    Never guess a reference or delete a possible footnote. Explicit corrections
    are single-line, single-match, reasoned and bound to the original page hash.
    """
    text, journal, seen = raw, [], set()
    for rule in cfg.get("ocr_corrections", []):
        if rule["id"] in seen:
            raise ValueError("duplicate OCR correction ID")
        seen.add(rule["id"])
        if int(rule["page"]) != page_no:
            continue
        old, new = rule["old"], rule["new"]
        if (not old or any(c in old + new for c in "\r\n") or not rule.get("reason")
                or rule.get("source_sha256") != sha_text(raw)
                or text.count(old) != 1):
            raise ValueError(f"OCR correction identity/count/line mismatch: {rule['id']}")
        text = text.replace(old, new, 1)
        journal.append({**rule, "stage": "raw_page"})
    text = normalize(text)
    fixes = cfg.get("word_fixes") or {}
    if fixes:
        if any(not k or any(c in k + v for c in "\r\n") for k, v in fixes.items()):
            raise ValueError("word_fixes must preserve line boundaries")
        rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, fixes), key=len, reverse=True)) + r")\b")
        def replace(m):
            journal.append({"stage": "early_word_fix", "page": page_no,
                            "old": m[0], "new": fixes[m[0]],
                            "line": text.count("\n", 0, m.start()) + 1})
            return fixes[m[0]]
        text = rx.sub(replace, text)
    return text, journal


def page_items(raw, page_no, allow_structural=True, display_head=False, source_raw=None):
    """Страница -> список словарей {kind, level, text, page}."""
    lines = [l.strip() for l in normalize(raw).splitlines()]
    original_lines = (source_raw if source_raw is not None else raw).splitlines()
    # Shortness alone does not authorize deleting dates or prose on title pages.
    # Only anchored/exact heading deduplication below can remove a rubric.
    items = []
    buf = []

    def flush():
        if buf:
            items.append({"kind": "para", "level": 0,
                          "text": join_lines(buf), "page": page_no})
            del buf[:]

    i = 0
    body_seen = 0
    while i < len(lines):
        s = lines[i]
        if not s:
            flush()
            i += 1
            continue

        # Номер параграфа проверяем ПЕРВЫМ: «. s. 1.» на верхней строке полосы
        # is_running_head принимает за колонтитул и выбрасывает, а это единственное
        # место, где номер вообще есть.
        # вдали от краёв полосы голое число колонцифрой быть не может
        pn = paragraph_number(s, bare_ok=EDGE_LINES <= i < len(lines) - EDGE_LINES)
        if pn is not None:
            flush()
            items.append({"kind": "para", "level": 0, "text": f"§ {pn}.",
                          "page": page_no, "paranum": pn, "source_raw": original_lines[i],
                          "source_line": i + 1, "method": "ocr_glyph", "confidence": "candidate"})
            body_seen += 1
            i += 1
            continue

        # Колонтитул-шапка режется ДО автопоиска заголовков: на нечётных
        # полосах фрактурных книг колонтитул начинается как MINOR-заголовок
        # («A. Erste Stellung des Gedankens zur Objektivität. 61») — иначе
        # автопоиск делает из каждой нечётной полосы заголовок уровня 4.
        if body_seen == 0 and i < HEAD_SCAN_LINES and is_running_head(s):
            i += 1
            continue

        lvl, end, wants_title = heading_match(s, allow_structural)
        if lvl:
            title = s[end:].strip(" .,;:'\"|-—=")
            j = i + 1
            if wants_title:
                # «Erstes Kapitel» на своей строке, название — на следующей
                while len(title) < 3 and j < len(lines) and j - i <= 3:
                    nxt = lines[j]
                    if not nxt:
                        j += 1
                        continue
                    if not is_title_line(nxt):
                        break
                    title = nxt.strip(" .,;:'\"|-—=")
                    j += 1
            # шум перед заголовком («< . Anmerkung», «!B. Knotenlinie»)
            head = re.sub(r"^[^A-Za-zÄÖÜäöüß]+", "", s[:end]).strip(" .,;:'\"|-—=")
            if head[:1] in "ABC" and len(head) <= 2 and not good_abc_title(title):
                # «B. Kno» — обрезок строки, а не подзаголовок: пусть будет текстом
                buf.append(s)
                body_seen += 1
                i += 1
                continue
            flush()
            items.append({"kind": "head", "level": lvl, "page": page_no,
                          "text": f"{head}. {title}".strip(". ") if title else head,
                          "source_raw": original_lines[i], "source_line": i + 1,
                          "method": "ocr_heading", "confidence": "candidate"})
            body_seen += 1
            i = j
            continue

        if looks_like_junk(s):
            i += 1
            continue
        if FOOTER_RE.match(s):
            i += 1
            continue
        if ENCYC_FOOTER.match(s):
            i += 1
            continue
        if CUT_FROM and s.startswith(CUT_FROM):
            # хвост-таблица на последней полосе («Druckfehler...»): всё от
            # этой строки до конца полосы — не текст книги
            break

        if UNIT_START.match(s):
            flush()
        buf.append(s)
        body_seen += 1
        i += 1
    flush()
    return items


def filter_paragraph_numbers(items, expected=None):
    """Retain uncertain OCR candidates for review; never invent missing numbers.

    A book-owned expected sequence can explicitly permit numbering restarts.
    Without one, increasing order is only a hypothesis, not evidence to delete.
    """
    idx = [i for i, it in enumerate(items) if it.get("paranum")]
    if not idx:
        return items, 0
    nums = [items[i]["paranum"] for i in idx]
    if expected is not None:
        if nums == expected:
            return items, 0
        for i in idx:
            items[i]["uncertain_paragraph"] = items[i]["paranum"]
            items[i]["confidence"] = "unresolved"
        return items, len(idx)
    tails, prev, at = [], [-1] * len(nums), []
    for k, v in enumerate(nums):
        p = bisect.bisect_left(tails, v)
        if p == len(tails):
            tails.append(v)
            at.append(k)
        else:
            tails[p] = v
            at[p] = k
        prev[k] = at[p - 1] if p else -1
    keep, cur = set(), at[len(tails) - 1] if tails else -1
    while cur != -1:
        keep.add(cur)
        cur = prev[cur]
    # An ordering hypothesis may reject a candidate, never synthesize its number.
    drop = {idx[k] for k in range(len(nums)) if k not in keep}
    for i in drop:
        it = items[i]
        it["text"] = it.get("source_raw", it["text"])
        it["uncertain_paragraph"] = it.pop("paranum")
        it["confidence"] = "unresolved"
    return items, len(drop)


def apply_unit_anchors(items, raw, page, rules):
    """Checked scan decisions: split at an exact normalized anchor, never guess tiers."""
    journal = []
    for rule in rules:
        if rule.get("page") != page:
            continue
        anchor = rule.get("anchor", "")
        if (not rule.get("id") or not rule.get("reason") or not anchor
                or rule.get("source_sha256") != sha_text(raw)
                or rule.get("type") not in ("main", "remark", "addition", "paragraph")):
            raise ValueError("invalid unit anchor identity/type")
        matches = [(i, row["text"].index(anchor)) for i, row in enumerate(items)
                   if row["kind"] == "para" and anchor in row["text"]]
        if len(matches) != 1 or items[matches[0][0]]["text"].count(anchor) != 1:
            raise ValueError("unit anchor must match exactly once on its source page")
        i, at = matches[0]
        row = items[i]
        left, right = row["text"][:at].rstrip(), row["text"][at:]
        new = dict(row, text=right, unit_start=True, unit_anchor=rule["id"])
        if rule["type"] != "paragraph":
            new["unit"] = rule["type"]
        items[i:i + 1] = ([dict(row, text=left)] if left else []) + [new]
        journal.append({"unit_id": rule["id"], "page": page, "anchor": anchor,
                        "type": rule["type"], "reason": rule["reason"]})
    return items, journal


def assign_units(items):
    active = None
    for row in items:
        if row["kind"] == "head" or row.get("paranum"):
            active = None
        if row.get("unit"):
            active = row["unit"]
        elif UNIT_START.match(row["text"]):
            active = "addition" if re.match(r"^\s*Zusatz\b", row["text"]) else "remark"
            row["unit_start"] = True
        if active and row["kind"] == "para" and not row.get("paranum"):
            row["unit"] = active
    return items


def merge_split_paragraphs(items):
    """Абзац, разорванный концом страницы (или ложным пустым интервалом),
    снова становится одним: предыдущий не закончен, следующий с маленькой."""
    out = []
    for it in items:
        if (out and it["kind"] == "para" and out[-1]["kind"] == "para"
                and not it.get("paranum") and not out[-1].get("paranum")
                and not it.get("unit_start")
                and it.get("unit") == out[-1].get("unit")
                and not it.get("uncertain_paragraph") and not out[-1].get("uncertain_paragraph")
                and not re.match(r"^\s*(?:\*+\)|\[\^|Zusatz|Zuſatz|Zusaß|Anmerkung|§|#{1,6}\s)", it["text"])
                and not re.match(r"^\s*(?:\*+\)|\[\^|§|#{1,6}\s)", out[-1]["text"])
                # A unit starts a new paragraph; a clearly hyphenated continuation
                # on another page still belongs to it. Do not swallow a new para.
                and (not UNIT_START.match(out[-1]["text"])
                     or (it["page"] != out[-1]["page"] and HYPHEN_END.search(out[-1]["text"])))):
            prev, cur = out[-1]["text"], it["text"]
            if prev and cur:
                if HYPHEN_END.search(prev):
                    _keep_page(out[-1], it)
                    out[-1]["text"] = join_hyphen(prev, cur)
                    continue
                # продолжение абзаца часто начинается с мусора («- seyn
                # niehr...»), поэтому смотрим на первую БУКВУ, а не на
                # первый символ
                head = re.search(r"[A-Za-zÄÖÜäöüß]", cur)
                # Требование строчной буквы в продолжении годится для
                # английского, но не для немецкого: фраза через разворот почти
                # всегда продолжается существительным с прописной. На томе 6
                # склейка из-за этого не срабатывала 240 раз из 863, и модель
                # дописывала обрубкам точку, превращая их в самостоятельные
                # утверждения. Смотрим на КОНЕЦ предыдущего блока: если он
                # оборван на букве или запятой — это одна фраза.
                tail = prev.rstrip(" |'\"*_-–—=~»«.,")
                unfinished = (not prev.rstrip(" |'\"*_").endswith(TERMINAL)
                              and re.search(r"[A-Za-zÄÖÜäöüß]$", tail))
                starts_unit = re.match(
                    r"^\W{0,3}(Zusatz|Zuſatz|Zusaß|Anmerkung|§)", cur)
                if head and not starts_unit and (head.group().islower()
                                                 or unfinished):
                    _keep_page(out[-1], it)
                    out[-1]["text"] = prev + " " + cur
                    continue
        out.append(it)
    return out


def inject_paragraph_anchors(items, anchors):
    """Номера, которых распознавание не увидело вовсе, ставим по тексту.

    В structure.json: "paragraph_anchors": {"3": "Der Inhalt, der unser"}.
    Отрывок ищется по буквам (порча OCR не мешает); если он начинает абзац,
    номер встаёт перед ним, если сидит внутри — абзац делится.
    """
    def letters(s):
        return re.sub(r"[^a-zäöüßA-ZÄÖÜ]+", "", s).lower()

    out, placed = [], 0
    todo = {int(k): letters(v) for k, v in (anchors or {}).items()}
    for num, key in todo.items():
        matches = sum(letters(it["text"]).count(key) for it in items
                      if it["kind"] == "para" and not it.get("paranum")) if key else 0
        if matches != 1 or any(it.get("paranum") == num for it in items):
            raise ValueError(f"paragraph anchor must be unique and absent from numbering: {num}")
    for it in items:
        hit = None
        if it["kind"] == "para" and not it.get("paranum"):
            body = letters(it["text"])
            for num, key in sorted(todo.items()):
                if key and key in body:
                    hit = (num, key)
                    break
        if not hit:
            out.append(it)
            continue
        num, key = hit
        del todo[num]
        pos = letters(it["text"]).index(key)
        if pos == 0:
            out.append({"kind": "para", "level": 0, "text": f"§ {num}.",
                        "page": it["page"], "paranum": num, "source_anchor": key,
                        "method": "explicit_anchor", "confidence": "profile"})
            out.append(it)
        else:
            # переводим смещение из «только буквы» обратно в исходную строку
            seen, cut = 0, len(it["text"])
            for i, ch in enumerate(it["text"]):
                if re.match(r"[a-zäöüßA-ZÄÖÜ]", ch):
                    if seen == pos:
                        cut = i
                        break
                    seen += 1
            head = dict(it, text=it["text"][:cut].strip())
            tail = dict(it, text=it["text"][cut:].strip())
            tail.pop("extra_pages", None)
            out.append(head)
            out.append({"kind": "para", "level": 0, "text": f"§ {num}.",
                        "page": it["page"], "paranum": num, "source_anchor": key,
                        "method": "explicit_anchor", "confidence": "profile"})
            out.append(tail)
        placed += 1
    if todo:
        raise ValueError(f"paragraph anchors not found: {sorted(todo)}")
    return out, placed


def _letters(s):
    return re.sub(r"[^a-zäöüßA-ZÄÖÜ]+", "", s).lower()


def place_headings(heads, page_it, pno, lax=False):
    """Разложить заголовки полосы по своим местам внутри неё.

    Карта inject задаёт «полоса -> заголовок», и заголовок вставал перед
    ПЕРВЫМ блоком полосы. Но раздел начинается в середине полосы: на томе 6
    под девятью заголовками из двадцати четырёх лежало около 6,7 тыс. знаков
    чужого текста — хвост предыдущего раздела, уехавший в новую главу.

    Запись с "anchor" (отрывок титульной строки в OCR-написании) встаёт перед
    тем блоком, где этот отрывок нашёлся; если отрывок сидит внутри блока,
    блок делится. Поиск по одним буквам — порча OCR не мешает.

    Ненайденный якорь — ошибка, а не повод молча вернуться к старому
    поведению: молчаливая вставка не на место и есть тот дефект, ради
    которого якорь заводится. Смягчается ключом --lax-anchors.
    """
    if not heads:
        return page_it
    out = list(page_it)
    for h in heads:
        anchor = _letters(h.get("anchor") or "")
        h["source_anchor"] = h.get("anchor")
        h["method"] = "explicit_anchor" if anchor else "profile_page"
        h["confidence"] = "profile"
        if h.get("at_paragraph"):
            # место такому заголовку выбирается позже, по номеру параграфа:
            # § к этому времени ещё не отфильтрованы по монотонности, и
            # раздел вообще может начинаться не на той полосе, где его
            # объявили в карте
            out.insert(_after_leading_heads(out), h)
            continue
        if not anchor:
            at = _after_leading_heads(out)
            out.insert(at, h)
            # Only explicitly confirmed OCR aliases immediately after this
            # injected heading may be consumed; never fuzzy-delete nearby prose.
            aliases = {normalize(s).strip() for s in h.get("ocr_aliases", [])}
            while at + 1 < len(out) and out[at + 1]["kind"] == "para":
                candidate = out[at + 1]
                if candidate.get("paranum") or candidate["text"].strip() not in aliases:
                    break
                h.setdefault("consumed_ocr_aliases", []).append(out.pop(at + 1))
            continue
        at = None
        for k, it in enumerate(out):
            if it["kind"] != "para":
                continue
            body = _letters(it["text"])
            if anchor in body:
                at = (k, body.index(anchor))
                break
        if at is None:
            msg = (f"!! полоса {pno}: якорь заголовка «{h['text'][:50]}» "
                   f"не найден в тексте полосы")
            if not lax:
                sys.exit(msg + ". Проверьте написание отрывка по скану "
                         "(берётся как распознано, с порчей) или снимите "
                         "якорь. Обойти: --lax-anchors")
            print(msg + " — поставлен в начало полосы (--lax-anchors)")
            out.insert(_after_leading_heads(out), h)
            continue
        k, pos = at
        if pos == 0:
            out.insert(k, h)
            k += 1
        else:
            it = out[k]
            seen, cut = 0, len(it["text"])
            for i, ch in enumerate(it["text"]):
                if re.match(r"[a-zäöüßA-ZÄÖÜ]", ch):
                    if seen == pos:
                        cut = i
                        break
                    seen += 1
            head_part = dict(it, text=it["text"][:cut].strip())
            tail_part = dict(it, text=it["text"][cut:].strip())
            tail_part.pop("extra_pages", None)
            out[k:k + 1] = [head_part, h, tail_part]
            k += 1
        _drop_title_fragments(out, k, h["text"])
    return [it for it in out if it["text"].strip()]


def place_headings_at_paragraphs(items, lax=False, strict=True):
    """Переставить заголовки, привязанные к номеру параграфа.

    Для книг, целиком построенных на §§ (Энциклопедия Гегеля), номер — самый
    надёжный якорь из возможных: он напечатан в собственной Inhalts-Anzeige
    издания, он однозначен, и его уже восстановил конвейер. Отрывок текста
    для той же цели приходится списывать со скана вручную, и списать его
    можно с ошибкой.

    Идёт ПОСЛЕ фильтра монотонности и якорей: к этому моменту номера
    окончательные.
    """
    want = {}
    for it in items:
        if it["kind"] == "head" and it.get("at_paragraph"):
            want.setdefault(int(it["at_paragraph"]), []).append(it)
    if not want:
        return items, 0
    at = {}
    for i, it in enumerate(items):
        n = it.get("paranum")
        if n is not None and n not in at:
            at[n] = i
    lost = sorted(set(want) - set(at))
    if lost and strict:
        msg = (f"!! заголовки привязаны к параграфам {lost}, а таких номеров "
               f"в книге нет")
        if not lax:
            sys.exit(msg + ". Номер потерян распознаванием — поставьте его "
                     "через paragraph_anchors, либо смените привязку "
                     "заголовка на anchor/полосу. Обойти: --lax-anchors")
        print(msg + " — заголовки остались на своих полосах (--lax-anchors)")
    moved = [it for grp in want.values() for it in grp
             if int(it["at_paragraph"]) in at]
    if not moved:
        return items, 0
    rest = [it for it in items if it not in moved]
    out, done = [], 0
    for it in rest:
        n = it.get("paranum")
        if n is not None and n in want:
            # На одном параграфе может сойтись отдел и его первая рубрика
            # («А. Качество.» и «a. Бытие.» оба на §86). Наружный заголовок
            # обязан встать первым, иначе рубрика окажется над своим же
            # разделом. Сортировка устойчива, поэтому равные уровни
            # сохраняют порядок записи в карте.
            for h in sorted(want[n], key=lambda x: x["level"]):
                if h in moved:
                    # полосу заголовок наследует от своего параграфа: до
                    # перестановки она была случайной (полоса записи в карте
                    # или первая полоса книги для рубрик без полосы)
                    h["page"] = it["page"]
                    out.append(h)
                    done += 1
                    _drop_title_fragments(out, len(out) - 1, h["text"])
        out.append(it)
    return out, done


def _after_leading_heads(out):
    """Место сразу за уже стоящими в начале заголовками: несколько записей
    inject на одну полосу должны сохранить свой порядок."""
    i = 0
    while i < len(out) and out[i]["kind"] == "head":
        i += 1
    return i


def rubric_key(text):
    """Ignore only a rubric's letter prefix, not prose words."""
    text = re.sub(r"^\s*[a-zа-яё]\s*[.,]\s*", "", text.casefold())
    return re.sub(r"[\W_]+", "", text)


def _drop_title_fragments(out, at, title):
    """Убрать обрывки титульной строки, лежащие прямо перед заголовком.

    Шмуцтитул набран разрядкой, и OCR рассыпает его на короткие куски
    («Учение о сущности», «Явление.»), которые иначе висят отдельными
    абзацами вплотную к вставленному заголовку.

    Точного вхождения требовать нельзя: разрядку распознавание коверкает
    сильнее обычного текста («Exfste Stellung» вместо «Erste Stellung»).
    Поэтому сравниваем на схожесть, и порог высокий — короткая, но настоящая
    фраза автора похожа на заголовок раздела гораздо меньше, чем его же
    испорченный двойник.
    """
    key = _letters(title)
    i = at - 1
    while i >= 0 and key:
        it = out[i]
        if it["kind"] != "para" or it.get("paranum"):
            break
        body = _letters(it["text"])
        if re.search(r"\d", it["text"]) or has_function_word(it["text"]):
            break
        # Обрывок не длиннее самого заголовка (плюс запас на мусор
        # распознавания): титульная строка «Erste Stellung des Gedankens zur
        # Objektivität.» сама по себе длиннее BODY_LINE_MIN, и порога
        # «короче строки набора» тут мало.
        if not body or len(it["text"]) > max(BODY_LINE_MIN, len(title) + 8):
            break
        if not (rubric_key(it["text"]) == rubric_key(title)
                or (len(body) >= 25 and len(it["text"].split()) >= 4
                    and _best_window(body, key) >= 0.90)):
            break
        del out[i]
        i -= 1


def _best_window(needle, hay):
    """Насколько похож needle на самый похожий кусок hay такой же длины.

    Обрывок — это часть заголовка, а не весь заголовок: «Явление.» против
    «Б. Явление.» целиком даёт низкое сходство, а против своего куска — почти
    единицу.
    """
    n = len(needle)
    if not n or n > len(hay):
        return 0.0
    return max(difflib.SequenceMatcher(None, needle, hay[i:i + n]).ratio()
               for i in range(len(hay) - n + 1))


def _keep_page(target, src):
    """Склеенному абзацу достаётся страница первого куска, и полоса, чей текст
    целиком влился в предыдущий абзац, оставалась без колонцифры — на томе 6
    так потерялись 80 номеров из 414. Запоминаем их за блоком."""
    seen = target.setdefault("extra_pages", [])
    if src["page"] != target["page"] and (not seen or seen[-1] != src["page"]):
        seen.append(src["page"])


# ------------------------------------------------------------------------- main

def parse_ranges(spec):
    pages = set()
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            pages.update(range(lo, hi + 1))
        else:
            pages.add(int(part))
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--offset", type=int, default=0,
                    help="печатная страница = страница скана + offset")
    ap.add_argument("--structure", default=None,
                    help="JSON: drop_pages, inject (страница скана -> заголовок)")
    ap.add_argument("--parts", type=int, default=300,
                    help="блоков в одной части (лимит hy-mt2 на сессию)")
    ap.add_argument("--no-page-marks", action="store_true")
    ap.add_argument("--page-marks-min", type=int, default=1,
                    help="не ставить метку, если печатный номер меньше этого "
                         "(фронт-материя с римской нумерацией)")
    ap.add_argument("--figures", default=None,
                    help="figures.json: {полоса: [{file, ...}]} — вырезанные "
                         "чертежи. Вставляются в конец своей полосы; без "
                         "этого ключа картинки в книгу не попадают вовсе")
    ap.add_argument("--pagemap", default=None,
                    help="pagemap.json от scripts/page_number_map.py: номера "
                         "берутся оттуда, а не считаются от --offset. Нужен, "
                         "когда скан не ложится на книгу ровно (пересъёмки, "
                         "пропуски) — тогда единый офсет врёт, а полосы без "
                         "подтверждённого номера остаются без метки")
    ap.add_argument("--no-long-s-fix", action="store_true",
                    help="не чинить слова, где «ſ» распозналось как «f»")
    ap.add_argument("--lax-anchors", action="store_true",
                    help="не падать, если якорь заголовка (inject.anchor) не "
                         "нашёлся: поставить заголовок в начало полосы, как "
                         "делалось до появления якорей")
    a = ap.parse_args()
    if not a.structure and (Path(a.work_dir) / "structure.json").is_file():
        a.structure = str(Path(a.work_dir) / "structure.json")

    cfg = {}
    if a.structure and os.path.exists(a.structure):
        cfg = json.load(open(a.structure, encoding="utf-8"))
    # drop_pages — выброшенное намеренно (титул, издательское оглавление,
    # пустые); drop_duplicates — пересъёмки. Для сборки это одно и то же, но
    # приёмке разница важна: у пересъёмки ОБЯЗАН быть уцелевший двойник, а у
    # намеренно выброшенной страницы его быть и не должно.
    drop = parse_ranges(cfg.get("drop_pages", ""))
    drop |= parse_ranges(cfg.get("drop_duplicates", ""))
    inject = {}
    for k, v in (cfg.get("inject") or {}).items():
        inject[int(k)] = v if isinstance(v, list) else [v]
    allow_structural = not cfg.get("structural_from_inject_only", False)
    globals()["EXTRA_HEAD_WORDS"] = [w.lower() for w in
                                     cfg.get("running_head_words", [])]
    globals()["CUT_FROM"] = cfg.get("cut_from") or ""
    # Книги, построенные на нумерованных параграфах (Энциклопедия Гегеля):
    # строку «§. 86.» надо не выбрасывать как мусор, а сохранять.
    globals()["PARAGRAPH_NUMBERS"] = bool(cfg.get("paragraph_numbers", False))
    globals()["PARAGRAPH_BARE"] = bool(cfg.get("paragraph_bare_numbers", False))
    if PARAGRAPH_NUMBERS:
        print("номера параграфов: распознаются и сохраняются"
              + (" (принимается и голое число в середине полосы)"
                 if PARAGRAPH_BARE else ""))
    if EXTRA_HEAD_WORDS:
        print(f"колонтитулы тома: {len(EXTRA_HEAD_WORDS)} фраз")

    pages_dir = os.path.join(a.work_dir, "pages")
    files = sorted(f for f in os.listdir(pages_dir)
                   if re.fullmatch(r"p\d{4}\.txt", f))
    if not files:
        sys.exit(f"нет постраничного OCR в {pages_dir}")

    # Заголовок, назначенный на выброшенную полосу, иначе исчезает молча:
    # на Энциклопедии 1817 так пропал целый раздел «Философия духа» — его
    # полоса попала в диапазон пересъёмки, и части раздела повисли в
    # оглавлении под предыдущим. Переносим такой заголовок на ближайшую
    # оставленную полосу и говорим об этом вслух.
    kept_pages = [int(f[1:5]) for f in files if int(f[1:5]) not in drop]
    for pno in sorted(inject):
        if pno not in drop:
            continue
        nxt = next((q for q in kept_pages if q > pno), None)
        titles = ", ".join(s["text"] for s in inject[pno])
        if nxt is None:
            print(f"!! заголовок «{titles}» назначен на выброшенную полосу "
                  f"{pno}, и дальше оставленных полос нет — ПОТЕРЯН")
            continue
        print(f"!! полоса {pno} выброшена, заголовок «{titles}» временно "
              f"перенесён на полосу {nxt}. ПРОВЕРЬТЕ: если полосу выбросили "
              f"как пересъёмку, начало раздела лежит на её ДВОЙНИКЕ (обычно "
              f"±8/±12 полос, ищет find_dup_scans.py) — впишите его номер в "
              f"structure.json, иначе заголовок встанет посреди текста")
        inject.setdefault(nxt, [])
        inject[nxt] = inject[pno] + inject[nxt]
        del inject[pno]

    # Порядок полос в скане не всегда равен порядку чтения: на Энциклопедии
    # 1817 хвост «Философии природы» (полосы 316-317) отснят ПОСЛЕ начала
    # «Философии духа», и книга получала абзацы о растениях и болезнях внутри
    # раздела о духе. move_before переставляет такие полосы на своё место.
    order = [int(f[1:5]) for f in files]
    for target, spec in (cfg.get("move_before") or {}).items():
        moved = sorted(parse_ranges(spec))
        tgt = int(target)
        if tgt not in order:
            print(f"!! move_before: полосы {target} нет в скане — пропущено")
            continue
        order = [p for p in order if p not in moved]
        at = order.index(tgt)
        order = order[:at] + moved + order[at:]
        print(f"переставлено: полосы {spec} -> перед полосой {tgt}")
    by_page = {int(f[1:5]): f for f in files}

    figures, figdir = {}, "images"
    if a.figures and os.path.exists(a.figures):
        raw_fig = json.load(open(a.figures, encoding="utf-8"))
        figures = {int(k): v for k, v in raw_fig.items() if str(k).isdigit()}
        n_fig = sum(len(v) for v in figures.values())
        print(f"чертежей: {n_fig} на {len(figures)} полосах "
              f"(полосы {min(figures) if figures else '-'}.."
              f"{max(figures) if figures else '-'})")

    items = []
    n_pages = 0
    # Рубрики, у которых полосы нет вовсе. Издание печатает их в собственной
    # Inhalts-Anzeige одним номером параграфа («a. Бытие — §86»), а в тексте
    # они набраны разрядкой и рассыпаны распознаванием на обрывки прозы
    # («a Seyn,»). Полосу для них выписывать неоткуда и незачем: место
    # задаёт параграф. На томе 6 таких рубрик 26, и ни одной из них в
    # structure.json не было — весь третий уровень рубрикации отсутствовал.
    for spec in (cfg.get("inject_at_paragraph") or []):
        items.append({"kind": "head", "level": int(spec["level"]),
                      "text": normalize(spec["text"]), "page": order[0],
                      "src": "inject", "ru": spec.get("ru"),
                      "at_paragraph": int(spec["at_paragraph"])})
    if items:
        print(f"рубрик, привязанных только к параграфу: {len(items)}")
    preparation = []
    unit_rules = cfg.get("unit_anchors", [])
    if len({r.get("id") for r in unit_rules}) != len(unit_rules):
        raise ValueError("duplicate unit anchor IDs")
    for pno in order:
        f = by_page[pno]
        if pno in drop:
            continue
        raw = Path(pages_dir, f).read_bytes().decode("utf-8")
        if not raw.strip():
            continue
        # Заголовок из карты выписывают, глядя на скан, поэтому в нём
        # остаётся длинное «ſ» («Philoſophie der Sophiſten»). Текст полос
        # нормализуется, а инжект шёл мимо — и в переводчик уезжало то,
        # чего он не понимает. Прогоняем через ту же нормализацию.
        heads = [{"kind": "head", "level": int(spec["level"]),
                  "text": normalize(spec["text"]), "page": pno,
                  "src": "inject", "anchor": spec.get("anchor"),
                  "at_paragraph": spec.get("at_paragraph"),
                  "ru": spec.get("ru"), "ocr_aliases": spec.get("ocr_aliases", [])}
                 for spec in inject.get(pno, [])]
        prepared, journal = prepare_ocr_page(raw, pno, cfg)
        preparation.extend(journal)
        page_it = page_items(prepared, pno, allow_structural,
                             display_head=pno in inject, source_raw=raw)
        page_it, units = apply_unit_anchors(page_it, raw, pno, unit_rules)
        preparation.extend(units)
        items.extend(place_headings(heads, page_it, pno, a.lax_anchors))
        # Чертежи этой полосы — в конец её текста. Точное место внутри полосы
        # OCR не даёт (рисунок стоит сбоку, текст его обтекает), но полосы
        # довольно, чтобы картинка попала к своему предложению.
        for fig in figures.get(pno, []):
            items.append({"kind": "figure", "level": 0, "page": pno,
                          "text": f"![]({figdir}/{fig['file']})"})
        n_pages += 1

    if PARAGRAPH_NUMBERS:
        if (cfg.get("paragraph_profile") or {}).get("sequence"):
            n_bad = 0  # explicit sequence may contain intentional numbering restarts
        else:
            items, n_bad = filter_paragraph_numbers(items, (cfg.get("paragraph_profile") or {}).get("sequence"))
        n_par = sum(1 for it in items if it.get("paranum"))
        print(f"номера параграфов: {n_par} принято, {n_bad} отброшено "
              "как нарушающие порядок")
    # Перестановка к своему параграфу идёт ДО склейки: заголовок, стоящий на
    # чужом месте в начале полосы, разрывает абзац, который иначе склеился бы
    # через разворот. Второй проход — после якорей параграфов, для номеров,
    # которых распознавание не дало и которые поставлены из карты.
    items, n_moved = place_headings_at_paragraphs(items, a.lax_anchors,
                                                  strict=False)
    items = merge_split_paragraphs(assign_units(items))
    if PARAGRAPH_NUMBERS:
        items, n_anchor = inject_paragraph_anchors(
            items, cfg.get("paragraph_anchors"))
        if n_anchor:
            print(f"номера параграфов: {n_anchor} поставлено по якорю из карты")
    items, n2 = place_headings_at_paragraphs(items, a.lax_anchors)
    n_moved += n2
    if n_moved:
        print(f"заголовков переставлено к своему параграфу: {n_moved}")
    items = [it for it in items if it["text"].strip()]

    # Автопоиск в тексте находит те же подзаголовки, что уже поставлены из
    # карты («B. Die Zeit.» инжектом и «B. Die Zeit» по тексту), — убираем
    # автопоисковый дубль, если его текст совпадает с инжектом на той же
    # полосе. Сравниваем по нормализованному тексту: инжект прошёл через
    # normalize(), текст полосы тоже; точка в конце нами же и съедается.
    inj_norm = {}
    for pno, specs in inject.items():
        inj_norm[pno] = {normalize(str(s["text"])).strip().lower().rstrip(".")
                         for s in specs}
    dedup = []
    for it in items:
        if (it["kind"] == "head" and it.get("src") != "inject"
                and it["page"] in inj_norm
                and it["text"].strip().lower().rstrip(".")
                in inj_norm[it["page"]]):
            continue
        dedup.append(it)
    items = dedup

    pagemap = {}
    if a.pagemap and os.path.exists(a.pagemap):
        with open(a.pagemap, encoding="utf-8") as f:
            raw = json.load(f)["map"]
        pagemap = {int(k): int(v) for k, v in raw.items()}
        print(f"карта страниц: подтверждённых номеров {len(pagemap)}")

    blocks = []
    cur_page = None
    n_marks = 0
    marked = set()      # печатная страница получает ровно один маркер
    ru_heads = {}       # номер блока -> готовый русский заголовок из карты
    for it in items:
        if not a.no_page_marks and it["page"] != cur_page:
            # маркер печатной страницы: без букв, поэтому переводчик его
            # пропускает нетронутым; для абзаца через разворот берётся
            # страница, на которой абзац начался
            printed = (pagemap.get(it["page"]) if pagemap
                       else it["page"] + a.offset)
            # фронт-материя в оригинале нумерована римскими цифрами и своими
            # сериями (Vorrede III–XIII, Einleitung I–XXVIII) — арабский
            # «-41» там был бы просто неправдой, поэтому меток нет
            if (printed is not None and printed >= a.page_marks_min
                    and printed not in marked):
                blocks.append(f"<!--{printed}-->")
                marked.add(printed)
                n_marks += 1
            cur_page = it["page"]
        it["output_block"] = len(blocks)
        if it["kind"] == "head":
            if it.get("ru"):
                # Название раздела — не проза, и машинному переводу его
                # доверять нельзя: на томе 6 шесть глав получили название
                # «/без_рассуждений», и оно же уехало в оглавление, в
                # закладки PDF и в колонтитул 83 страниц. Готовый русский
                # текст из карты запоминаем по НОМЕРУ БЛОКА: сборщик читает
                # части подряд, нумерация блоков у исходника и перевода
                # общая, поэтому индекс — единственная привязка, которая
                # переживает перевод.
                ru_heads[len(blocks)] = {"level": it["level"],
                                         "de": it["text"], "ru": it["ru"]}
            blocks.append("#" * it["level"] + " " + it["text"])
        else:
            blocks.append(it["text"])
        # полосы, целиком влившиеся в этот абзац при склейке, тоже должны
        # получить колонцифру — иначе ссылаться на оригинал будет не по чему
        for pg in it.get("extra_pages", ()):
            printed = pagemap.get(pg) if pagemap else pg + a.offset
            if (not a.no_page_marks and printed is not None
                    and printed >= a.page_marks_min
                    and printed not in marked):
                blocks.append(f"<!--{printed}-->")
                marked.add(printed)
                n_marks += 1
            cur_page = pg
    n_fig_out = sum(1 for it in items if it["kind"] == "figure")

    text = "\n\n".join(blocks)

    # word_fixes already ran once on normalized lines, BEFORE segmentation.
    # Reapplying here could chain A->B->C and cannot repair lost tier boundaries.
    if not a.no_long_s_fix:
        text, n_fixed, mapping = fix_long_s(text)
        top = sorted(mapping.items(), key=lambda kv: kv[0])[:8]
        print(f"длинное s: исправлено вхождений {n_fixed}, словоформ "
              f"{len(mapping)} (напр. {', '.join(f'{k}→{v}' for k, v in top)})")
        text, n_tz, tz_map = fix_tz_ligature(text)
        print(f"лигатура tz: исправлено вхождений {n_tz}, словоформ "
              f"{len(tz_map)} (напр. {', '.join(f'{k}→{v}' for k, v in sorted(tz_map.items())[:8])})")
        blocks = text.split("\n\n")

    applied_ids = {r["id"] for r in preparation if r.get("id")}
    if applied_ids != {r["id"] for r in cfg.get("ocr_corrections", [])}:
        raise ValueError("OCR correction page is missing/dropped; no silent skip")
    if {r["unit_id"] for r in preparation if "unit_id" in r} != {r["id"] for r in unit_rules}:
        raise ValueError("unit anchor page is missing/dropped")
    layout = {}
    for it in items:
        index = it["output_block"]
        pages = [pagemap.get(p) if pagemap else p + a.offset
                 for p in [it["page"], *it.get("extra_pages", [])]]
        layout[str(index)] = {"source_sha256": sha_text(blocks[index]),
                              "pages": list(dict.fromkeys(p for p in pages if p is not None and p >= a.page_marks_min)),
                              "unit": it.get("unit")}
    write_json(Path(a.work_dir) / "structure.trace.json", {
        "schema": 1, "items": items, "layout": layout,
        "page_boundary_policy": "per-block source page coverage, not exact translated offsets",
        "preparation": preparation,
        "uncertainties": [it for it in items if it.get("uncertain_paragraph")],
        "ocr_pages": {f: sha_file(Path(pages_dir) / f) for f in files}})
    out_md = os.path.join(a.work_dir, "book.md")
    atomic_text(out_md, text + "\n")

    # Спутник book.md: заголовки, которые НЕ надо переводить моделью.
    # Файл всегда переписывается вместе с book.md (в том числе пустым), иначе
    # он переживёт пересборку и станет ссылаться на съехавшие номера блоков.
    heads_path = os.path.join(a.work_dir, "headings.ru.json")
    with open(heads_path, "w", encoding="utf-8") as f:
        json.dump({"source": os.path.basename(out_md),
                   "blocks_total": len(blocks),
                   "headings": {str(k): v for k, v in sorted(ru_heads.items())}},
                  f, ensure_ascii=False, indent=1)
    if ru_heads:
        print(f"{heads_path}: готовых русских заголовков {len(ru_heads)} "
              "(сборщик возьмёт их вместо ответа модели)")

    heads = [it for it in items if it["kind"] == "head"]
    n_para = sum(1 for it in items if it["kind"] == "para")
    print(f"{out_md}: страниц {n_pages}, блоков {len(blocks)} "
          f"(абзацев {n_para}, заголовков {len(heads)}, "
          f"чертежей {n_fig_out})")
    for h in heads:
        print(f"  {'  ' * (h['level'] - 1)}[{h['level']}] с.{h['page'] + a.offset:>4}  "
              f"{h['text']}")

    n_parts = 0
    for n, i in enumerate(range(0, len(blocks), a.parts), start=1):
        chunk = blocks[i:i + a.parts]
        p = os.path.join(a.work_dir, f"book.part{n}.md")
        atomic_text(p, "\n\n".join(chunk) + "\n")
        print(f"  book.part{n}.md: {len(chunk)} блоков")
        n_parts = n

    # Лишние части от ПРЕЖНЕЙ сборки. Книга, пересобранная со склейкой
    # абзацев, укладывается в меньшее число частей: у «Энциклопедии» 1817
    # было пять, стало три. Прежние book.part4.md и book.part5.md остаются
    # на диске, и дальше по конвейеру их никто не отличает от новых —
    # переводчик честно их переводит, сборщик честно подшивает, и в книгу
    # уезжает кусок предыдущей редакции. Ни одна проверка этого не видит:
    # число блоков исходника и перевода сходится, потому что лишними
    # оказываются оба. Убираем сразу и говорим вслух.
    # Enumerate exact part filenames, even across gaps, and keep colliding archives.
    for path in Path(a.work_dir).glob("book*.part*.md"):
        m = re.fullmatch(r"book(?:\.ru)?\.part(\d+)\.md", path.name)
        if m and int(m[1]) > n_parts:
            archive_stale(path)
            archive_stale(str(path) + ".report.json")
            archive_stale(str(path) + ".lineage.json")
    manifest = create_manifest(a.work_dir, config={
        "parts": a.parts, "offset": a.offset, "page_marks": not a.no_page_marks,
        "lax_anchors": a.lax_anchors, "structure_trace_sha256": sha_file(Path(a.work_dir) / "structure.trace.json")
    }, structure=a.structure)
    print(f"manifest: {manifest['run_id']}")


if __name__ == "__main__":
    main()
