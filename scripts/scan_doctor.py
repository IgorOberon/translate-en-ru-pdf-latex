# -*- coding: utf-8 -*-
"""Доктор скана: один прогон всех проверок готического тома.

Зачем отдельная команда. Проверок набралось пять, и каждая ловит дефект,
который иначе проходит молча и всплывает уже в готовом PDF: не та модель OCR,
переснятая тетрадь, выброшенные обе копии страницы, заголовок, назначенный на
выброшенную полосу, сбитый порядок чтения. Агент, ведущий том, пропустит
любую из них, если они разбросаны по README. Здесь они собраны, и каждая
печатает вердикт.

Запускать ДВАЖДЫ: после OCR (что со сканом) и после сборки book.md
(что получилось). Код возврата 1, если есть на что смотреть.

Использование:
    python scripts/scan_doctor.py <work_dir> [--structure structure.json]
        [--window 40] [--min-ratio 0.6]
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ocr_md as B  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(script, *args):
    r = subprocess.run([PY, "-X", "utf8", os.path.join(HERE, script), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout or "", r.returncode


def head(title):
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def check_ocr_model(work_dir):
    """Длинное «ſ» есть только у deu_latf; deu_frak его не отдаёт."""
    head("1. Модель OCR")
    pages = os.path.join(work_dir, "pages")
    files = [f for f in os.listdir(pages) if re.fullmatch(r"p\d{4}\.txt", f)]
    if not files:
        print("  нет постраничного OCR")
        return True
    with_s = 0
    for f in files:
        t = open(os.path.join(pages, f), encoding="utf-8",
                 errors="replace").read()
        if "ſ" in t:
            with_s += 1
    frac = with_s * 100 // len(files)
    print(f"  полос с длинным «ſ»: {with_s}/{len(files)} ({frac}%)")
    if frac < 80:
        print("  !! похоже, часть полос распознана deu_frak — перегоните "
              "весь том с deu_latf (ocr_fraktur.py, БЕЗ --resume)")
        return False
    print("  ок: том распознан deu_latf")
    return True


def check_structural_flag(cfg):
    """Если структура задана картой, автопоиск заголовков надо гасить.

    Иначе он вдобавок находит их в КОЛОНТИТУЛАХ и плодит ложные главы:
    у Евклида так появились «Erstes Buch. Ziehe BE/CH:-DaBC==FGJA DEM»,
    «Drittes Buch. 53» и «Viertes Buch. 75» — прямо в оглавлении книги.
    """
    head("2. Автопоиск структурных заголовков")
    inject = cfg.get("inject") or {}
    flag = cfg.get("structural_from_inject_only", False)
    structural = 0
    for v in inject.values():
        for it in (v if isinstance(v, list) else [v]):
            if int(it.get("level", 9)) <= 3:
                structural += 1
    if structural and not flag:
        print(f"  !! в inject задано {structural} структурных заголовков, но "
              f"structural_from_inject_only не включён.")
        print("     Автопоиск найдёт те же слова в колонтитулах и добавит "
              "ложные главы. Поставьте \"structural_from_inject_only\": true")
        return False
    print(f"  ок: структурных заголовков в карте {structural}, "
          f"автопоиск {'выключен' if flag else 'не нужен'}")
    return True


def check_injects(work_dir, cfg):
    head("3. Заголовки на выброшенных полосах")
    drop = B.parse_ranges(cfg.get("drop_pages", ""))
    drop |= B.parse_ranges(cfg.get("drop_duplicates", ""))
    bad = [(k, v) for k, v in (cfg.get("inject") or {}).items()
           if int(k) in drop]
    if not bad:
        print("  ок: все заголовки стоят на оставленных полосах")
        return True
    for k, v in bad:
        items = v if isinstance(v, list) else [v]
        for it in items:
            print(f"  !! полоса {k}: «{it['text']}» — полоса выброшена. "
                  f"Начало раздела ищите на её ДВОЙНИКЕ и впишите его номер")
    return False


def check_dups(work_dir, window, ratio):
    head("4. Пересъёмки в скане")
    out, _ = run("find_dup_scans.py", work_dir, "--window", str(window),
                 "--min-ratio", str(ratio))
    for line in out.splitlines():
        if line.startswith(("полос к сравнению", "пар-дублей", "прогонов",
                            "  сканы", "в structure.json")):
            print("  " + line.strip())
    return "пар-дублей: 0" in out


def check_audit(work_dir, window, ratio):
    head("5. Приёмка дедупликации")
    out, rc = run("audit_dedup.py", work_dir, "--window", str(window),
                  "--min-ratio", str(ratio))
    for line in out.splitlines():
        if line.strip():
            print("  " + line.rstrip())
    return rc == 0


def check_order(work_dir):
    head("6. Порядок чтения")
    out, _ = run("check_page_order.py", work_dir, "--top", "8")
    for line in out.splitlines():
        if line.strip():
            print("  " + line.rstrip())
    print("  (признаки шумные: смотрите не проценты, а конкретные границы)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--structure", default=None)
    ap.add_argument("--window", type=int, default=40)
    ap.add_argument("--min-ratio", type=float, default=0.6)
    a = ap.parse_args()

    path = a.structure or os.path.join(a.work_dir, "structure.json")
    cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    if not cfg:
        print(f"!! нет {path} — структура тома не задана")

    ok = []
    ok.append(check_ocr_model(a.work_dir))
    ok.append(check_structural_flag(cfg))
    ok.append(check_injects(a.work_dir, cfg))
    ok.append(check_dups(a.work_dir, a.window, a.min_ratio))
    ok.append(check_audit(a.work_dir, a.window, a.min_ratio))
    check_order(a.work_dir)

    head("ВЕРДИКТ")
    names = ["модель OCR", "автопоиск заголовков", "заголовки на выброшенных",
             "пересъёмки", "приёмка дедупликации"]
    for name, good in zip(names, ok):
        print(f"  {'ок  ' if good else 'СМОТРЕТЬ'}  {name}")
    if all(ok):
        print("\nСкан чист — можно собирать книгу.")
        return 0
    print("\nЕсть на что смотреть: разберитесь до сборки, иначе дефект "
          "уедет в готовый PDF незаметно.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
