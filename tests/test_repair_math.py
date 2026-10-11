#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Правила repair-math и нормализация границ $…$ — разбор книги NFCM.

Материал не выдуман: все случаи взяты из «New Foundations for Classical
Mechanics» (Hestenes), 718 страниц геометрической алгебры, и из отчёта по её
переводу.

Самый дорогой случай — переключатель шрифта поверх математического акцента.
Он роняет XeTeX намертво: «! Internal error: bad native font flag in
'map_char_to_glyph'», rc=3, PDF не пишется, а в main.log ошибки НЕТ — лог
обрывается на текущей странице. Место находится только бисектом по body.tex;
на этой книге поиск стоил часов, а мест было 49.

Отдельная забота — случаи, где правило НЕ должно срабатывать: «\\mathbf{x}»
без акцента, «\\bfseries», законное «\\overset{\\rightarrow}{AB}» и любая
русская проза внутри (кириллический страж).

Запуск: python tests/test_repair_math.py     (код 1 при провале)
        python -m pytest tests/test_repair_math.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import clean_markdown as C          # noqa: E402
import audit_selfcheck as A         # noqa: E402
from mask_math import tighten_inline_math  # noqa: E402

CHECKS = []


def eq(name, got, want):
    CHECKS.append((name, got == want,
                   "получено «%s»\n         ждали  «%s»" % (got, want)))


def fix(src):
    return C.repair_math_artifacts(src)[0]


def test_switch_accent_crash_pattern():
    # форма B: переключатель объявлением внутри чужой группы
    eq("{\\bf \\dot{...}} -> boldsymbol",
       fix(r"${ \bf \dot { \theta } } ^ { 2 }$"),
       r"${ \boldsymbol{\dot{ \theta }} } ^ { 2 }$")
    # форма A: у переключателя своя скобка
    eq("\\mathbf{\\bar{...}} -> boldsymbol",
       fix(r"$\mathbf { \bar { \alpha } }$"),
       r"$\boldsymbol{ \bar { \alpha } }$")
    eq("\\mathsf{\\hat{...}} -> boldsymbol",
       fix(r"$\mathsf { \hat { \cal A } }$"),
       r"$\boldsymbol{ \hat { \cal A } }$")
    eq("\\pmb тоже переключатель",
       fix(r"$\pmb { \vec { v } }$"), r"$\boldsymbol{ \vec { v } }$")
    # акцент НЕ единственное содержимое: ручной проход тома это пропустил
    eq("акцент плюс индекс внутри переключателя",
       fix(r"$\mathbf { \vec { F }^{ \prime } }$"),
       r"$\boldsymbol{ \vec { F }^{ \prime } }$")
    # вложенные переключатели разбираются оба; внутренний \mathrm при этом
    # снимается как «прямой» (см. test_upright_switch)
    eq("вложенные переключатели",
       fix(r"$\pmb { \mathrm { \pmb { \hat { \varepsilon } } } }$"),
       r"$\boldsymbol{  \boldsymbol{ \hat { \varepsilon } }  }$")

    # --- НЕ ТРОГАТЬ
    eq("переключатель без акцента остаётся",
       fix(r"$\mathbf{x}$"), r"$\mathbf{x}$")
    eq("\\bfseries — не из списка, и бэкслеш цел",
       fix(r"$\bfseries x$"), r"$\bfseries x$")
    eq("акцент ПОВЕРХ переключателя — обратный порядок, законен",
       fix(r"$\hat{\pmb{\beta}}_3$"), r"$\hat{\pmb{\beta}}_3$")
    eq("кириллица внутри — это проза, \\boldsymbol её уронит",
       fix(r"\textbf { \bar { жирный текст } }"),
       r"\textbf { \bar { жирный текст } }")


def test_overset():
    eq("акцент поверх отношения — оставить отношение",
       fix(r"$\overset { \triangle } { < }$"), r"$<$")
    eq("акцент поверх \\geqslant",
       fix(r"$\overset { \cdot } { \geqslant }$"), r"$\geqslant$")
    eq("точка поверх цифры — цифра",
       fix(r"$\overset { \cdot } { 8 }$"), r"$8$")
    eq("точка поверх буквы — это \\dot",
       fix(r"$\overset { \cdot } { x }$"), r"$\dot{x}$")
    eq("точка поверх пустоты — пустая ГРУППА, не пустота",
       fix(r"$\overset { \cdot } { \ }$"), r"${}$")
    eq("\\mathbf{\\overset \\ddots} -> \\ddots",
       fix(r"$\mathbf { \overset \ddots }$"), r"$\ddots$")

    # --- НЕ ТРОГАТЬ
    eq("стрелка поверх пары букв — законный вектор",
       fix(r"$\overset{\rightarrow}{AB}$"), r"$\overset{\rightarrow}{AB}$")


def test_textbf_em():
    eq("\\textbf{\\em{X}} -> boldsymbol",
       fix(r"$\textbf { \em { X } }$"), r"$\boldsymbol{X}$")
    eq("\\textbf{\\em X} без скобок",
       fix(r"$\textbf { \em \alpha }$"), r"$\boldsymbol{\alpha}$")
    eq("кириллица внутри — не математика",
       fix(r"\textbf { \em жирный курсив }"),
       r"\textbf { \em жирный курсив }")


def test_eqno_and_mathscr():
    eq("номер уравнения под баром (цифры через пробелы)",
       fix(r"$\mathsf { \bar { ( 2 . 1 6 ) } }$"), r"$(2.16)$")
    eq("\\mathscr со строчной -> \\mathit (у rsfs нет строчных глифов)",
       fix(r"$\mathscr{r}$"), r"$\mathit{r}$")
    eq("\\mathscr с прописной законен",
       fix(r"$\mathscr{A}$"), r"$\mathscr{A}$")


def test_idempotent():
    src = (r"${ \bf \dot { \theta } } ^ { 2 }$ и $\overset { \cdot } { x }$ "
           r"и $\mathscr{r}$ и $\textbf { \em { X } }$")
    once = fix(src)
    eq("повторный проход ничего не меняет", fix(once), once)


def test_upright_switch():
    # \mathrm просит ПРЯМОЕ начертание; заменить его на \boldsymbol значило
    # бы соврать про жирность, а прямого глифа у строчной греческой нет —
    # честная починка снимает переключатель
    eq("\\mathrm снимается, а не бол+дится",
       fix(r"$\mathrm { \bar { \alpha } }$"), r"$ \bar { \alpha } $")
    eq("\\mathbf по-прежнему в \\boldsymbol",
       fix(r"$\mathbf { \bar { \alpha } }$"), r"$\boldsymbol{ \bar { \alpha } }$")


def test_prescan_grades_risk():
    """Роняет НЕ всякое сочетание, и гейт обязан это различать.

    Замерено микротестами на боевой преамбуле: \\mathbf{\\bar{\\alpha}} и
    {\\bf \\dot{\\cal E}} падают, а \\pmb{\\hat{\\varepsilon}},
    \\mathbf{\\bar{x}} и \\mathbf{\\hat{\\Gamma}} собираются. Без этого
    различия гейт кричал бы на местах, которые в готовой книге спокойно
    печатаются, и ему перестали бы верить.
    """
    def grade(line):
        r, o, n = A.audit_switch_accent(line)
        return len(r), len(o)

    eq("строчная греческая под \\mathbf — опасно",
       grade(r"\(\mathbf { \bar { \alpha } }\)"), (1, 0))
    eq("каллиграфия под \\bf — опасно",
       grade(r"\({ \bf \dot { \cal E } }\)"), (1, 0))
    eq("латиница под \\mathbf — соберётся",
       grade(r"\(\mathbf { \bar { x } }\)"), (0, 1))
    eq("ПРОПИСНАЯ греческая — соберётся",
       grade(r"\(\mathbf { \hat { \Gamma } }\)"), (0, 1))
    eq("\\pmb не меняет шрифт и не роняет",
       grade(r"\(\pmb { \hat { \varepsilon } }\)"), (0, 1))
    eq("\\mathrm со строчной греческой — опасно",
       grade(r"\(\mathrm { \bar { \alpha } }\)"), (1, 0))

    r, o, n = A.audit_switch_accent("\\section{A}\n$\\mathbf{x}$\n")
    eq("на чистом теле прескан молчит", n, 0)
    r, o, n = A.audit_switch_accent(
        "x\n\\(\\mathbf { \\bar { \\alpha } }\\)\n")
    eq("прескан называет номер строки", r[0].startswith("строка 2:"), True)


def test_tighten_dollars():
    eq("краевые пробелы срезаются",
       tighten_inline_math(r"$ \mathbf { a } $ — вектор")[0],
       r"$\mathbf { a }$ — вектор")
    eq("два спана и кириллица между ними",
       tighten_inline_math("текст $ a $ проза $ b $ хвост")[0],
       "текст $a$ проза $b$ хвост")
    # --- НЕ ТРОГАТЬ
    eq("латинская проза между спанами не уезжает в математику",
       tighten_inline_math("a $x$ b $y$ c")[0], "a $x$ b $y$ c")
    eq("ложная пара с кириллицей внутри",
       tighten_inline_math("$представляет собой$")[0],
       "$представляет собой$")
    eq("строка с выключной формулой пропускается",
       tighten_inline_math("$$ x = 1 $$")[0], "$$ x = 1 $$")
    eq("строка-картинка пропускается",
       tighten_inline_math("![рис]( a.png ) и $ y $")[0],
       "![рис]( a.png ) и $ y $")
    eq("экранированный доллар не считается за границу",
       tighten_inline_math(r"цена \$ 10 и $ z $")[0],
       r"цена \$ 10 и $z$")
    eq("нечётный доллар оставляем",
       tighten_inline_math("одинокий $ доллар")[0], "одинокий $ доллар")
    eq("пустой спан не схлопываем в $$",
       tighten_inline_math("$ $")[0], "$ $")


def test_zzz_все_проверки_прошли():
    """Проверки выше копят результат в CHECKS, а не падают на месте: так
    виден ВЕСЬ список расхождений, а не первое."""
    fails = ["{}: {}".format(n, x) for n, ok, x in CHECKS if not ok]
    assert not fails, "провалов {}:\n  ".format(len(fails)) + "\n  ".join(
        fails[:10])


def main():
    for t in (test_switch_accent_crash_pattern, test_overset, test_textbf_em,
              test_eqno_and_mathscr, test_idempotent, test_upright_switch,
              test_prescan_grades_risk,
              test_tighten_dollars):
        try:
            t()
        except Exception as e:                          # noqa: BLE001
            CHECKS.append((f"{t.__name__} не упал", False, repr(e)[:200]))
    bad = 0
    for name, ok, extra in CHECKS:
        print(("PASS " if ok else "FAIL ") + name
              + ("" if ok else f"\n      -> {extra}"))
        bad += not ok
    print(f"\n{len(CHECKS) - bad}/{len(CHECKS)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
