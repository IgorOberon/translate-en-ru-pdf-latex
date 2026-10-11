#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Верификаторы: разбор пропавших глифов по шрифтам и раздел ответов.

Оба случая — замечания из отчёта по «New Foundations for Classical
Mechanics», раздел 8: аудит шумел там, где всё в порядке, и молчал о том,
что можно было назвать сразу.

Запуск: python tests/test_verifiers.py     (код 1 при провале)
        python -m pytest tests/test_verifiers.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import audit_selfcheck as A      # noqa: E402
import layout_report as L        # noqa: E402

CHECKS = []


def eq(name, got, want):
    CHECKS.append((name, got == want,
                   "получено «%s»\n         ждали  «%s»" % (got, want)))


def ok(name, cond, extra=""):
    CHECKS.append((name, bool(cond), extra))


def test_answers_section_excluded():
    """Приложение ответов выборочно ПО ПОСТРОЕНИЮ.

    «Ответы к нечётным задачам» приводит 1, 3, 7, 12 — и проверка нумерации
    честно рапортовала о пропусках, которых нет. Это была самая шумная
    ложная тревога аудита на той книге.
    """
    md = "\n".join([
        "# Глава 1", r"$$x\tag{1}$$", r"$$y\tag{2}$$", r"$$z\tag{5}$$",
        "# Ответы к нечётным задачам",
        r"$$a\tag{1}$$", r"$$b\tag{7}$$", r"$$c\tag{19}$$",
    ])
    findings, total = A.audit_eq_numbers(md)
    gaps = [f for f in findings if "нет (" in f]
    eq("настоящий пропуск в главе виден", len(gaps), 1)
    ok("пропуск назван верно", "(3), (4)" in gaps[0], gaps)
    eq("номера из раздела ответов не считаются", total, 3)
    ok("раздел ответов помечен, а не проверен",
       any("выборочна по построению" in f for f in findings), findings)

    for title in ("Ответы к задачам", "Указания", "Answers", "Hints",
                  "Solutions", "Приложение. Решения"):
        ok(f"«{title}» опознан как раздел ответов",
           A.is_answer_section(title))
    for title in ("Глава 3", "Введение", "Кинематика"):
        ok(f"«{title}» НЕ раздел ответов", not A.is_answer_section(title))


def test_missing_glyphs_by_font():
    """Диагноз ставится по ШРИФТУ, а не по списку символов.

    «нет о, нет е, нет с…» не говорит ни о чём; «776 кириллических в cmmi8»
    говорит, что русский текст затянуло внутрь $…$. Этим же способом на той
    книге нашли rsfs/\\mathscr.
    """
    log = "\n".join([
        "Missing character: There is no о in font cmmi8!",
        "Missing character: There is no е in font cmmi8!",
        "Missing character: There is no r in font rsfs10!",
        "Missing character: There is no ф in font TimesNewRoman!",
        "Output written on main.pdf (12 pages).",
    ])
    pages, over, under, missing, by_font = L.scan_log(log)
    eq("страницы прочитаны", pages, 12)
    eq("всего пропавших", sum(missing.values()), 4)
    eq("шрифтов", sorted(by_font), ["TimesNewRoman", "cmmi8", "rsfs10"])
    eq("cmmi8 сгруппирован", sum(by_font["cmmi8"].values()), 2)

    d = L.diagnose_font("cmmi8", by_font["cmmi8"])
    ok("кириллица в мат. шрифте названа своим именем", "внутрь $…$" in d, d)
    d = L.diagnose_font("rsfs10", by_font["rsfs10"])
    ok("rsfs назван строчными глифами", "СТРОЧНЫХ" in d, d)
    d = L.diagnose_font("TimesNewRoman", by_font["TimesNewRoman"])
    ok("кириллица в текстовом шрифте — другой диагноз",
       "нет кириллицы" in d, d)


def test_unpacking_arity_matches():
    """Все ли распаковки совпадают с тем, сколько функция возвращает.

    Поймано на живом: `scan_log` стала возвращать пятый элемент (разбор по
    шрифтам), а `full_audit.py` распаковывал четыре — и падал с
    «too many values to unpack» на первом же прогоне. py_compile такое не
    видит (синтаксис верен), тестов у full_audit нет, и поломка проехала бы
    до пользователя. Проверка статическая: сравниваем число возвращаемых
    имён с числом целей в каждом месте вызова.
    """
    import ast

    scripts = ROOT / "scripts"
    # функция -> сколько значений возвращает (по её собственному return)
    arity = {}
    for path in scripts.glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except SyntaxError as e:                        # noqa: PERF203
            ok(f"{path.name} парсится", False, str(e))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            sizes = {len(r.value.elts) for r in ast.walk(node)
                     if isinstance(r, ast.Return)
                     and isinstance(r.value, ast.Tuple)}
            if len(sizes) == 1:
                arity.setdefault(node.name, sizes.pop())

    bad = []
    for path in scripts.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Tuple)):
                continue
            name = node.value.func.id
            want = arity.get(name)
            got = len(node.targets[0].elts)
            if want is not None and want != got:
                bad.append(f"{path.name}:{node.lineno} {name}() отдаёт "
                           f"{want}, распаковано {got}")
    ok("распаковки совпадают с арностью", not bad, "; ".join(bad))


def test_no_syntax_warnings():
    """Ни один скрипт не должен сыпать SyntaxWarning при импорте.

    Такое предупреждение — не косметика: «invalid escape sequence '\\T'»
    значит, что строка задумана сырой, а написана обычной, и в ней уже
    завтра может оказаться `\\n` или `\\d`, который тихо изменит смысл.
    Нашлось на docstring с путём `D:\\Tesseract-OCR\\…`.
    """
    import warnings

    bad = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as e:                    # noqa: PERF203
                bad.append(f"{path.name}: {e}")
                continue
            for w in caught:
                if issubclass(w.category, SyntaxWarning):
                    bad.append(f"{path.name}: {w.message}")
    ok("скрипты компилируются без SyntaxWarning", not bad, "; ".join(bad))


def test_zzz_все_проверки_прошли():
    fails = ["{}: {}".format(n, x) for n, o, x in CHECKS if not o]
    assert not fails, "провалов {}:\n  ".format(len(fails)) + "\n  ".join(
        fails[:10])


def main():
    for t in (test_answers_section_excluded, test_missing_glyphs_by_font,
              test_unpacking_arity_matches, test_no_syntax_warnings):
        try:
            t()
        except Exception as e:                          # noqa: BLE001
            CHECKS.append((f"{t.__name__} не упал", False, repr(e)[:200]))
    bad = 0
    for name, o, extra in CHECKS:
        print(("PASS " if o else "FAIL ") + name
              + ("" if o else f"\n      -> {extra}"))
        bad += not o
    print(f"\n{len(CHECKS) - bad}/{len(CHECKS)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
