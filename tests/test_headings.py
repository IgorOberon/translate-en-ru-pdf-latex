#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Заголовки фрактурного маршрута: якоря (§3.5) и русский текст из карты (§3.4).

Что проверяется и почему именно это:

  1. Заголовок без якоря встаёт в начало полосы — прежнее поведение цело.
  2. Заголовок с текстовым якорем встаёт перед нужным блоком; если якорь
     сидит внутри блока, блок делится. Ради этого всё и затевалось: на томе 6
     под девятью заголовками из двадцати четырёх лежал хвост предыдущего
     раздела, около 6,7 тыс. знаков.
  3. Ненайденный якорь останавливает сборку, а не молча возвращает старое
     поведение: молчаливая вставка не на место и есть чинимый дефект.
  4. Заголовок, привязанный к номеру параграфа, встаёт перед своим §, а
     вложенные заголовки на одном § идут от наружного к внутреннему
     («А. Качество.» перед «a. Бытие.», а не наоборот).
  5. Обрывки титульной строки перед заголовком снимаются — включая
     испорченные распознаванием («Exfste» вместо «Erste»), — но настоящая
     короткая фраза автора остаётся.
  6. headings.ru.json, отставший от book.md, обнаруживается по немецкому
     тексту на месте, а не применяется к съехавшим номерам блоков.
  7. Ответ модели, который не может быть заголовком, останавливает сборку:
     том 6 получил шесть глав «/без_рассуждений» именно потому, что
     restore_headings молча цементировала первую строку ответа в \\chapter.

Запуск: python tests/test_headings.py    (код 1 при провале)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_ocr_md as B          # noqa: E402
import assemble_ru_book as A      # noqa: E402

CHECKS = []


def check(name, ok, extra=""):
    CHECKS.append((name, bool(ok), extra))


def para(text, page=1, num=None):
    it = {"kind": "para", "level": 0, "text": text, "page": page}
    if num is not None:
        it["paranum"] = num
    return it


def head(text, level=1, page=1, **kw):
    it = {"kind": "head", "level": level, "text": text, "page": page,
          "src": "inject"}
    it.update(kw)
    return it


def texts(items):
    return [it["text"] for it in items]


# ------------------------------------------------------------------ 1, 2, 3

def test_text_anchor():
    page = [para("Ende des vorigen Abschnitts, der hier ausläuft."),
            para("Die Zeit ist das Werden des Raums.")]

    out = B.place_headings([head("B. Die Zeit.")], list(page), 79)
    check("без якоря — заголовок в начале полосы",
          texts(out)[0] == "B. Die Zeit.", texts(out)[:1])

    out = B.place_headings(
        [head("B. Die Zeit.", anchor="Die Zeit ist das Werden")],
        list(page), 79)
    check("текстовый якорь — заголовок перед своим блоком",
          texts(out) == ["Ende des vorigen Abschnitts, der hier ausläuft.",
                         "B. Die Zeit.",
                         "Die Zeit ist das Werden des Raums."], texts(out))

    mid = [para("Hier endet der vorige Abschnitt. Die Zeit ist das Werden.")]
    out = B.place_headings(
        [head("B. Die Zeit.", anchor="Die Zeit ist das Werden")], mid, 79)
    check("якорь внутри блока — блок делится",
          texts(out) == ["Hier endet der vorige Abschnitt.",
                         "B. Die Zeit.",
                         "Die Zeit ist das Werden."], texts(out))

    try:
        B.place_headings([head("X.", anchor="ganz und gar nicht vorhanden")],
                         list(page), 79)
        check("ненайденный якорь останавливает сборку", False, "не упало")
    except SystemExit as e:
        check("ненайденный якорь останавливает сборку",
              "не найден" in str(e), str(e)[:80])

    out = B.place_headings([head("X.", anchor="nicht vorhanden")],
                           list(page), 79, lax=True)
    check("--lax-anchors — заголовок в начало полосы, без падения",
          texts(out)[0] == "X.", texts(out)[:1])


# --------------------------------------------------------------------- 4

def test_paragraph_anchor():
    items = [head("A. Qualität.", level=3, page=205, at_paragraph=86),
             head("a. Seyn.", level=4, page=1, at_paragraph=86),
             para("Vorhergehender Text.", page=204),
             para("§ 86.", page=205, num=86),
             para("Seyn ist der unbestimmte Begriff.", page=205)]
    out, n = B.place_headings_at_paragraphs(items)
    check("привязка к § — оба заголовка переставлены", n == 2, n)
    check("привязка к § — наружный заголовок перед внутренним",
          texts(out) == ["Vorhergehender Text.", "A. Qualität.", "a. Seyn.",
                         "§ 86.", "Seyn ist der unbestimmte Begriff."],
          texts(out))
    moved = [it for it in out if it["kind"] == "head"]
    check("привязка к § — полоса наследуется от параграфа",
          all(it["page"] == 205 for it in moved),
          [it["page"] for it in moved])

    lost = [head("C. Das Maaß.", level=3, at_paragraph=999),
            para("§ 86.", num=86)]
    try:
        B.place_headings_at_paragraphs(list(lost))
        check("привязка к отсутствующему § останавливает сборку", False,
              "не упало")
    except SystemExit as e:
        check("привязка к отсутствующему § останавливает сборку",
              "999" in str(e), str(e)[:80])
    _, n = B.place_headings_at_paragraphs(list(lost), strict=False)
    check("нестрогий проход не падает на отсутствующем §", n == 0, n)


# --------------------------------------------------------------------- 5

def test_drop_fragments():
    title = "A. Erste Stellung des Gedankens zur Objektivität. Metaphysik."
    out = [para("Exfste Stellung des Gedankens zur Objektivität."),
           head(title, level=3)]
    B._drop_title_fragments(out, 1, title)
    check("обрывок титула снят, несмотря на порчу распознавания",
          texts(out) == [title], texts(out))

    out = [para("Die Erscheinung."), head("B. Die Erscheinung.", level=3)]
    B._drop_title_fragments(out, 1, "B. Die Erscheinung.")
    check("короткий обрывок титула снят",
          texts(out) == ["B. Die Erscheinung."], texts(out))

    real = "Und damit ist der Uebergang vollzogen."
    out = [para(real), head("B. Die Erscheinung.", level=3)]
    B._drop_title_fragments(out, 1, "B. Die Erscheinung.")
    check("настоящая фраза автора не снята", texts(out)[0] == real, texts(out))

    out = [para("§ 86.", num=86), head("A. Qualität.", level=3)]
    B._drop_title_fragments(out, 1, "A. Qualität.")
    check("номер параграфа не снимается как обрывок", len(out) == 2, texts(out))


# ------------------------------------------------------------------ 6, 7

def test_assemble_side():
    with tempfile.TemporaryDirectory() as d:
        src = ["# Einleitung", "Der erste Absatz.", "# Vorbegriff"]
        json.dump({"source": "book.md", "blocks_total": 3,
                   "headings": {"0": {"level": 1, "de": "Einleitung",
                                      "ru": "Введение"}}},
                  open(os.path.join(d, "headings.ru.json"), "w",
                       encoding="utf-8"), ensure_ascii=False)
        heads = A.load_ru_headings(d, src)
        check("headings.ru.json прочитан", heads.get(0, {}).get("ru") == "Введение",
              heads)

        shifted = ["<!--1-->", "# Einleitung", "Der erste Absatz."]
        try:
            A.load_ru_headings(d, shifted)
            check("съехавшие номера блоков обнаружены", False, "не упало")
        except SystemExit as e:
            check("съехавшие номера блоков обнаружены",
                  "не про этот book.md" in str(e), str(e)[:80])

        out, _, _, from_map, bad, _ = A.restore_headings(
            src, ["что угодно", "Первый абзац.", "Предварительное понятие"],
            heads)
        check("русский заголовок взят из карты, а не из перевода",
              out[0] == "# Введение" and from_map == 1, out[:1])
        check("заголовок без карты берётся из перевода",
              out[2] == "# Предварительное понятие", out[2:])

        try:
            A.restore_headings(src, ["/без_рассуждений", "Абзац.", "Понятие"],
                               {})
            check("служебный мусор в заголовке останавливает сборку", False,
                  "не упало")
        except SystemExit as e:
            check("служебный мусор в заголовке останавливает сборку",
                  "служебный мусор" in str(e), str(e)[:60])

        out, _, _, _, bad, _ = A.restore_headings(
            src, ["/без_рассуждений", "Абзац.", "Понятие"], {}, lax=True)
        check("--lax-headings — на месте мусора немецкий оригинал",
              out[0] == "# Einleitung" and len(bad) == 1, out[:1])

        out, _, _, _, _, trimmed = A.restore_headings(
            src, ["Введение\nи ещё отсебятина", "Абзац.", "Понятие"], {})
        check("многострочный ответ обрезан до первой строки",
              out[0] == "# Введение" and trimmed == 1, (out[0], trimmed))


def test_zzz_все_проверки_прошли():
    """Проверки выше копят результат в CHECKS, а не падают на месте: так
    виден ВЕСЬ список расхождений, а не первое. Здесь и стоит тот assert,
    без которого pytest считал бы набор зелёным при любых провалах."""
    fails = ["{}: {}".format(n, x) for n, ok, x in CHECKS if not ok]
    assert not fails, "провалов {}:\n  ".format(len(fails)) + "\n  ".join(
        fails[:10])


def main():
    for t in (test_text_anchor, test_paragraph_anchor, test_drop_fragments,
              test_assemble_side):
        try:
            t()
        except Exception as e:                      # noqa: BLE001
            check(f"{t.__name__} не упал", False, repr(e)[:200])
    bad = 0
    for name, ok, extra in CHECKS:
        print(("PASS " if ok else "FAIL ") + name
              + ("" if ok else f"\n      -> {extra}"))
        bad += not ok
    print(f"\n{len(CHECKS) - bad}/{len(CHECKS)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
