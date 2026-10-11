#!/usr/bin/env python3
"""Synthetic tests for mask_math.py v2 recovery unmask. Exit 1 on failure."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mask_math import unmask, mask  # noqa: E402

MAPPING = {
    "⟦M000001⟧": "$a+b$",
    "⟦M000002⟧": "$$x^2$$",
    "⟦M000003⟧": "\\ref{eq:1}",
    "⟦M000004⟧": "$F'$",
    "⟦M000005⟧": "$z \\mapsto iz$",
}

CASES = [
    ("exact token",
     "текст ⟦M000001⟧ конец",
     "текст $a+b$ конец", 1, 0, 0),
    ("slash instead of closer",
     "текст ⟦M000002⟋ конец",
     "текст $$x^2$$ конец", 0, 1, 0),
    ("angle brackets",
     "текст ⟨M000003⟩, конец",
     "текст \\ref{eq:1}, конец", 0, 1, 0),
    ("single guillemets",
     "текст ‹M000004›-конец",
     "текст $F'$-конец", 0, 1, 0),
    ("square-and-circle",
     "текст ▦M000005◦ конец",
     "текст $z \\mapsto iz$ конец", 0, 1, 0),
    ("token glued to a word",
     "словоM000001⟧ конец",
     "слово$a+b$ конец", 0, 1, 0),
    ("unknown id stays untouched",
     "текст M123456 конец",
     "текст M123456 конец", 0, 0, 1),
    ("mixed: exact + damaged + unknown",
     "⟦M000001⟧ и ⟨M000002⟩ и M999999",
     "$a+b$ и $$x^2$$ и M999999", 1, 1, 1),
    ("spaces around token must not be eaten",
     "слева ⟨M000001⟩ справа",
     "слева $a+b$ справа", 0, 1, 0),
]


def main():
    failed = 0
    for name, src, want, we, wr, wu in CASES:
        got, e, r, u = unmask(src, MAPPING)
        ok = got == want and (e, r, u) == (we, wr, wu)
        print(("PASS" if ok else "FAIL"), name)
        if not ok:
            failed += 1
            print("   got :", repr(got), (e, r, u))
            print("   want:", repr(want), (we, wr, wu))

    # round-trip: mask -> unmask restores the original text
    src = "Пусть $x^2+y^2=r^2$ и уравнение $$e^{i\\pi}=-1$$ и ссылка \\ref{eq:5}."
    masked, mp = mask(src)
    back, e, r, u = unmask(masked, mp)
    ok = back == src and u == 0
    print(("PASS" if ok else "FAIL"), "mask/unmask round-trip")
    if not ok:
        failed += 1
        print("   got :", repr(back))

    # маркеры плашек: \plaquebegin/\plaqueend уходят в токены,
    # текст плашки между ними остаётся переводимым
    src = ("\\plaquebegin Второй закон Ньютона. Сила равна $m\\vec a$. "
           "\\plaqueend")
    masked, mp = mask(src)
    ok = ("\\plaque" not in masked
          and "Сила равна" in masked
          and unmask(masked, mp)[0] == src)
    print(("PASS" if ok else "FAIL"), "plaque markers masked, body kept")
    if not ok:
        failed += 1
        print("   got :", repr(masked))

    # контракт CLI: токен вне карты -> в stdout "unresolved: 1"
    # (на эту строку опирается приёмка обоих оркестраторов)
    import json
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "in.md").write_text("текст ⟦M000042⟧ конец", encoding="utf-8")
    (tmp / "map.json").write_text(json.dumps({"⟦M000001⟧": "$x$"}),
                                  encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "mask_math.py"),
         "unmask", str(tmp / "in.md"), str(tmp / "out.md"),
         str(tmp / "map.json")],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = (r.stdout or "") + (r.stderr or "")
    ok = "unresolved: 1" in out
    print(("PASS" if ok else "FAIL"), "CLI reports 'unresolved: 1' for unknown id")
    if not ok:
        failed += 1
        print("   got:", out.strip()[:200])

    total = len(CASES) + 3
    print(f"\n{total - failed}/{total} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
