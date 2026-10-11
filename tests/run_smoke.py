#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_smoke.py — приёмка любых правок конвейера одной командой:
py_compile всех скриптов + все тест-наборы. Exit 1, если что-то красное.

  python tests/run_smoke.py
"""
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent

SUITES = [
    "test_mineru_structure.py",
    "test_installation.py",
    "test_dispatcher.py",
    "run_clean_markdown_tests.py",
    "test_glossary.py",
    "test_headings.py",
    "test_mask_math.py",
    "test_postfix_ru.py",
    "test_procutils.py",
    "test_repair_math.py",
    "test_rescue_plaques.py",
    "test_skeleton_folio.py",
    "test_skeleton_split.py",
    "test_translate_validator.py",
    "test_verifiers.py",
    "test_integrity_regressions.py",
    "test_packaging.py",
    "test_luna_pilot_regressions.py",
    "test_complex_ocr_regressions.py",
]


def main():
    failed = []

    files = sorted((ROOT / "scripts").glob("*.py")) \
        + sorted((ROOT / "skeleton").glob("*.py")) \
        + sorted(TESTS.glob("*.py"))
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            print("FAIL compile", f.name, "\n", e)
            failed.append(f"compile:{f.name}")
    print(f">> py_compile: {len(files)} файлов"
          + ("" if failed else " — все компилируются"))

    for s in SUITES:
        print(f"\n===== {s} =====", flush=True)
        rc = subprocess.run(
            [sys.executable, "-X", "utf8", str(TESTS / s)]).returncode
        if rc:
            failed.append(s)

    print("\n" + "=" * 50)
    if failed:
        print("SMOKE FAILED:", ", ".join(failed))
        sys.exit(1)
    print("SMOKE PASSED: компиляция и все наборы зелёные")


if __name__ == "__main__":
    main()
