# -*- coding: utf-8 -*-
"""Проверка порядка полос по стыкам текста на границе страниц.

Идея. Номера страниц во фрактуре распознаются слишком плохо, чтобы строить по
ним порядок чтения (проверено: подтверждается меньше четверти полос). Зато
почти каждая полоса обрывается на полуслове или на полуфразе, и следующая
её продолжает. Если полосы стоят верно, склейка «хвост + голова» даёт слово,
которое в книге встречается, и фраза течёт дальше; если полосы переставлены
(в сканах с пересъёмками это бывает), стык рвётся.

Считаются два признака:
  * ПЕРЕНОС — последняя строка кончается знаком переноса. Склеенное слово
    обязано найтись в словаре книги. Признак почти однозначный.
  * ФРАЗА — предыдущая полоса кончается без точки, а следующая начинается со
    строчной буквы. Признак слабее, но покрывает почти все границы.

Колонтитулы и шмуцтитульный шум снимаются той же логикой, что при сборке
(build_ocr_md.page_items), иначе «первым словом» окажется колонтитул.

Использование:
    python scripts/check_page_order.py <work_dir> [--structure structure.json]
        [--top 25]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ocr_md as B  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--structure", default=None)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()

    cfg = {}
    path = a.structure or os.path.join(a.work_dir, "structure.json")
    if os.path.exists(path):
        cfg = json.load(open(path, encoding="utf-8"))
    drop = B.parse_ranges(cfg.get("drop_pages", ""))
    inject = {int(k) for k in (cfg.get("inject") or {})}

    paras = {}
    for f in sorted(os.listdir(os.path.join(a.work_dir, "pages"))):
        m = re.fullmatch(r"p(\d{4})\.txt", f)
        if not m:
            continue
        p = int(m.group(1))
        if p in drop:
            continue
        raw = open(os.path.join(a.work_dir, "pages", f), encoding="utf-8",
                   errors="replace").read()
        items = B.page_items(raw, p, allow_structural=False,
                             display_head=p in inject)
        texts = [it["text"] for it in items if it["kind"] == "para"]
        if texts:
            paras[p] = texts

    order = sorted(paras)
    for target, spec in (cfg.get("move_before") or {}).items():
        moved = [p for p in sorted(B.parse_ranges(spec)) if p in paras]
        tgt = int(target)
        if tgt in order:
            order = [p for p in order if p not in moved]
            at = order.index(tgt)
            order = order[:at] + moved + order[at:]

    vocab = Counter()
    for texts in paras.values():
        vocab.update(w.lower() for t in texts
                     for w in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", t))

    hy_n, hy_ok, hy_bad = 0, 0, []
    ph_n, ph_ok, ph_bad = 0, 0, []
    for p, q in zip(order, order[1:]):
        prev, nxt = paras[p][-1], paras[q][0]
        if B.HYPHEN_END.search(prev):
            stem = re.sub(r"[^A-Za-zÄÖÜäöüß]", "",
                          B.HYPHEN_END.sub("", prev).split(" ")[-1])
            head = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", nxt.split(" ")[0])
            if len(stem) >= 2 and len(head) >= 2:
                hy_n += 1
                joined = (stem + head).lower()
                if vocab.get(joined, 0) >= 1:
                    hy_ok += 1
                else:
                    hy_bad.append((p, q, f"«{stem}-»+«{head}»={joined}"))
            continue
        first = re.search(r"[A-Za-zÄÖÜäöüß]", nxt)
        if prev.endswith(B.TERMINAL) or not first:
            continue
        ph_n += 1
        if first.group().islower():
            ph_ok += 1
        else:
            ph_bad.append((p, q, f"«...{prev[-30:]}» / «{nxt[:30]}...»"))

    print(f"оставленных полос: {len(order)}")
    if hy_n:
        print(f"границ с переносом слова: {hy_n}, склейка нашлась в книге: "
              f"{hy_ok} ({hy_ok * 100 // hy_n}%)")
    if ph_n:
        print(f"границ с оборванной фразой: {ph_n}, продолжение со строчной: "
              f"{ph_ok} ({ph_ok * 100 // ph_n}%)")
    print(f"\nПОДОЗРИТЕЛЬНЫЕ границы: перенос {len(hy_bad)}, "
          f"фраза {len(ph_bad)}")
    for p, q, why in hy_bad[:a.top]:
        print(f"  перенос {p} -> {q}: {why}")
    for p, q, why in ph_bad[:a.top]:
        print(f"  фраза   {p} -> {q}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
