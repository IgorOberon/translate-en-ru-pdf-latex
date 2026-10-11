#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Где лежит конвейер и где лежат внешние программы.

Раньше корень был вписан в скрипты строкой `ROOT = r"D:\\0FREETRANSLATE"`, а
Tesseract — строкой `D:\\Tesseract-OCR\\tesseract.exe`. На этой машине всё
сходилось, на любой другой конвейер падал на первом же шаге: «нет файла»,
причём не там, где ошибка, а глубоко внутри стадии. Здесь всё это считается
от расположения самого файла и от PATH, так что папку можно просто
скопировать куда угодно.

Порядок поиска у каждого инструмента одинаков и намеренно такой:
  1. переменная окружения (последнее слово всегда за пользователем),
  2. PATH,
  3. обычные места установки для этой ОС.
Не нашли — возвращаем имя как есть: пусть вызывающий скрипт получит внятную
ошибку «не найден в PATH», а не молчаливый обход.
"""
import os
import shutil
import sys
from pathlib import Path

# scripts/paths.py -> корень конвейера
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
ASSETS = ROOT / "assets"
SKELETON = ROOT / "skeleton"

WINDOWS = os.name == "nt"


def venv_python():
    """Интерпретатор, которым надо запускать дочерние стадии.

    Именно venv конвейера, а не `python` из PATH: на Windows голый `python`
    сплошь и рядом оказывается заглушкой Microsoft Store, которая падает с
    кодом 49 и ничего не печатает. Если мы уже внутри venv — берём себя.
    """
    for cand in (ROOT / "venv" / "Scripts" / "python.exe",
                 ROOT / "venv" / "bin" / "python",
                 ROOT / ".venv" / "Scripts" / "python.exe",
                 ROOT / ".venv" / "bin" / "python"):
        if cand.is_file():
            return str(cand)
    return sys.executable


def _venv_bin():
    """Каталог исполняемых файлов venv конвейера, если он есть."""
    for d in (ROOT / "venv" / "Scripts", ROOT / "venv" / "bin",
              ROOT / ".venv" / "Scripts", ROOT / ".venv" / "bin"):
        if d.is_dir():
            return d
    return None


def _search(env_var, names, extra_dirs=()):
    val = os.environ.get(env_var)
    if val and Path(val).is_file():
        return val
    # venv конвейера ПЕРВЫМ: mineru и marker ставятся именно туда, а в PATH
    # их обычно нет — и «not found in PATH» встречало пользователя на
    # инструменте, который на самом деле стоит
    vb = _venv_bin()
    if vb:
        for n in names:
            for suffix in ((".exe", ".cmd", ".bat", "") if WINDOWS else ("",)):
                p = vb / (n + suffix)
                if p.is_file():
                    return str(p)
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    for d in extra_dirs:
        p = Path(d)
        if p.is_file():
            return str(p)
    return names[0]


def tesseract():
    """OCR фрактуры. Модель deu_latf ставится отдельно, в tessdata."""
    return _search(
        "TESSERACT_EXE", ["tesseract"],
        [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
         r"C:\Tesseract-OCR\tesseract.exe",
         r"D:\Tesseract-OCR\tesseract.exe",
         "/usr/bin/tesseract", "/usr/local/bin/tesseract"])


def lms():
    """CLI LM Studio: им грузится и проверяется модель перевода."""
    home = Path.home()
    return _search(
        "LMS_EXE", ["lms"],
        [home / ".lmstudio" / "bin" / ("lms.exe" if WINDOWS else "lms"),
         home / ".cache" / "lm-studio" / "bin" / "lms"])


def pandoc():
    return _search("PANDOC_EXE", ["pandoc"])


def xelatex():
    return _search("XELATEX_EXE", ["xelatex"])


def mineru():
    return _search("MINERU_EXE", ["mineru"])


def marker():
    return _search("MARKER_EXE", ["marker_single"])


def default_glossary():
    """Глоссарий по умолчанию — рядом с конвейером, а не по абсолютному пути."""
    for name in ("glossary_de.md", "glossary.example.md"):
        p = ROOT / name
        if p.is_file():
            return str(p)
    return str(ROOT / "glossary.example.md")


def describe():
    """Строки «что где нашлось» — для доктора окружения и отладки."""
    def mark(path, name):
        ok = Path(path).is_file() or shutil.which(name)
        return ("OK " if ok else "НЕТ"), path
    rows = [("корень конвейера", "OK ", str(ROOT)),
            ("python конвейера", *mark(venv_python(), "python")),
            ("tesseract", *mark(tesseract(), "tesseract")),
            ("pandoc", *mark(pandoc(), "pandoc")),
            ("xelatex", *mark(xelatex(), "xelatex")),
            ("mineru", *mark(mineru(), "mineru")),
            ("lms (LM Studio)", *mark(lms(), "lms"))]
    return rows


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for name, status, path in describe():
        print(f"  {status} {name:18s} {path}")
