#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the skeleton's duplicate backstops: split_ru_md (дубль
нумерованного раздела виден, первое вхождение главнее) и
find_repeated_subheads (дубль, начинающийся с НЕнумерованных подзаголовков —
боевой случай 15.2 Тейлора). Exit 1 on failure."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skeleton"))
sys.path.insert(0, str(ROOT / "scripts"))
import translate_into_skeleton as sk  # noqa: E402

CHECKS = []


def check(name, ok, extra=""):
    print(("PASS" if ok else "FAIL"), name)
    if not ok and extra:
        print("   ", extra)
    CHECKS.append(ok)


CLEAN_MD = """\
# Глава 15

Вводный текст главы до первого раздела.

## 15.1 Относительность

Тело первого раздела.

## 15.2 Галилеева относительность

Тело второго раздела.
"""

DUP_NUMBERED_MD = """\
# Глава 15

Вводный текст.

## 15.2 Галилеева относительность

Первый вариант тела.

## 15.3 Постулаты

Тело третьего.

## 15.2 Галилеева относительность

Второй вариант тела (дубль).
"""

# боевой случай: вторая копия начинается с НЕнумерованных подзаголовков,
# номер раздела 15.2 в ней не повторяется — дедуп по номерам её не видит
DUP_SUBHEADS_BODY = """\
### Галилеево преобразование

Первый вариант описания преобразования.

### Галилеева инвариантность законов Ньютона

Первый вариант описания инвариантности.

### Галилеево преобразование

Второй вариант описания преобразования.

### Галилеева инвариантность законов Ньютона

Второй вариант описания инвариантности.
"""

LEGIT_REPEATS_BODY = """\
### Пример

Первый пример раздела.

### Пример

Второй пример раздела — заголовок «Пример» законно повторяется.
"""


def test_split():
    intro, parts, dups = sk.split_ru_md(CLEAN_MD)
    check("split: intro без заголовка главы",
          intro == "Вводный текст главы до первого раздела.", repr(intro))
    check("split: разделы разобраны", sorted(parts) == ["15.1", "15.2"],
          str(sorted(parts)))
    check("split: дублей нет", dups == [], str(dups))

    _i, parts2, dups2 = sk.split_ru_md(DUP_NUMBERED_MD)
    check("split: дубль номера замечен", dups2 == ["15.2"], str(dups2))
    check("split: первое вхождение главнее",
          parts2["15.2"] == "Первый вариант тела.", repr(parts2["15.2"]))


def test_repeated_subheads():
    rep = sk.find_repeated_subheads(DUP_SUBHEADS_BODY)
    heads = {h for h, _n in rep}
    check("subheads: дубль с ненумерованными подзаголовками пойман",
          len(rep) == 2
          and "галилеево преобразование" in heads
          and all(n == 2 for _h, n in rep), str(rep))
    check("subheads: чистое тело не срабатывает",
          sk.find_repeated_subheads(
              "### Галилеево преобразование\n\nОдин раз.\n") == [])
    check("subheads: короткий «Пример» законно повторяется",
          sk.find_repeated_subheads(LEGIT_REPEATS_BODY) == [],
          str(sk.find_repeated_subheads(LEGIT_REPEATS_BODY)))


def main():
    test_split()
    test_repeated_subheads()
    failed = CHECKS.count(False)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
