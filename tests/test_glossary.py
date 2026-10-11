#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Матчеры check_glossary.py: немецкий термин и русская целевая форма.

Наивная версия этих двух функций дала бессмыслицу на первом же прогоне, и
каждый случай ниже — реальный промах, а не выдумка:

  · «das Einzelne» — термином становился артикль «das» (2905 вхождений);
  · «Nichts» со срезанной основой «Nicht» совпадал с отрицанием «nicht»
    (1508 вхождений вместо настоящих);
  · «Werden» — то же со вспомогательным глаголом «werden» (557);
  · «снимать» с обрубком основы по правилам существительного не покрывал
    «снимает» — глагол показывал 0 % соблюдения;
  · «определённость» против «определенность» — расхождение по ё давало
    16 % там, где термин соблюдён.

Запуск: python tests/test_glossary.py     (код 1 при провале)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_glossary import de_pattern, ru_pattern, ru_stem, yo  # noqa: E402

CHECKS = []


def de(term, text, want, why=""):
    rx = de_pattern(term)
    got = bool(rx and rx.search(text))
    CHECKS.append((f"de «{term}» {'находит' if want else 'НЕ находит'} "
                   f"«{text[:44]}»" + (f" — {why}" if why else ""),
                   got == want, f"got={got}"))


def ru(target, text, want, why=""):
    rx = ru_pattern([target])
    got = bool(rx and rx.search(yo(text)))
    CHECKS.append((f"ru «{target}» {'находит' if want else 'НЕ находит'} "
                   f"«{text[:44]}»" + (f" — {why}" if why else ""),
                   got == want, f"got={got}"))


def test_matchers():
    # --- немецкая сторона: артикли, регистр, композиты
    de("das Einzelne", "Das Einzelne ist bestimmt.", True)
    de("das Einzelne", "Das Ganze ist das Wahre.", False,
       "артикль сам по себе термином не является")
    de("Nichts", "Das Seyn und das Nichts sind dasselbe.", True)
    de("Nichts", "Es ist nicht so gemeint.", False,
       "отрицание «nicht» — не термин «Nichts»")
    de("Werden", "Ihre Wahrheit ist das Werden.", True)
    de("Werden", "Die Dinge werden bestimmt.", False,
       "вспомогательный глагол — не термин")
    de("Bestimmung", "Die Bestimmungen des Begriffs.", True, "склонение")
    de("Bestimmung", "Eine Grundbestimmung des Wesens.", True, "композит")
    de("Maaß", "Das Maaß ist die qualitative Quantität.", True)
    de("Katete", "Die Kathedrale und das Katheder.", False,
       "короткий термин не ловится внутри чужого слова")
    de("Idee", "Die Idee ist das Wahre an und für sich.", True)
    de("Idee", "Er identifizierte beide.", False)
    de("aufheben", "Diese Bestimmungen aufheben sich selbst.", True,
       "строчный термин — без учёта регистра")

    # --- русская сторона: склонение, спряжение, ё
    ru("понятие", "в понятии как таковом", True, "склонение")
    ru("понятие", "речь идёт о представлении", False)
    ru("становление", "их истина есть становления момент", True)
    ru("определённость", "эта определенность есть качество", True,
       "глоссарий с ё, текст без ё")
    ru("снимать", "рассудок снимает эту противоположность", True,
       "глагол спрягается, а не склоняется")
    ru("наличное бытие", "в наличном бытии вещи", True,
       "у словосочетания смотрим главное слово")
    ru("мера", "мера есть единство качества и количества", True)
    ru("суть дела", "самая суть дела состоит в том", True)

    # --- основы поодиночке
    for word, want in (("понятие", "поняти"), ("определённость", "определенн"),
                       ("снимать", "снима"), ("становление", "становл"),
                       ("бытие", "быти")):
        got = ru_stem(word)
        CHECKS.append((f"основа «{word}» -> «{want}»", got == want,
                       f"got={got}"))


def test_zzz_все_проверки_прошли():
    """Проверки выше копят результат в CHECKS, а не падают на месте: так
    виден ВЕСЬ список расхождений, а не первое. Здесь и стоит тот assert,
    без которого pytest считал бы набор зелёным при любых провалах."""
    fails = ["{}: {}".format(n, x) for n, ok, x in CHECKS if not ok]
    assert not fails, "провалов {}:\n  ".format(len(fails)) + "\n  ".join(
        fails[:10])


def main():
    test_matchers()
    bad = 0
    for name, ok, extra in CHECKS:
        print(("PASS " if ok else "FAIL ") + name
              + ("" if ok else f"\n      -> {extra}"))
        bad += not ok
    print(f"\n{len(CHECKS) - bad}/{len(CHECKS)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
