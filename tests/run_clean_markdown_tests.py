#!/usr/bin/env python3
"""Run the synthetic cases in tests/clean_markdown_cases.md against
scripts/clean_markdown.py (clean_text). Also checks idempotency:
cleaning the cleaned output must be a no-op. Exit 1 on any failure."""
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from clean_markdown import clean_text  # noqa: E402

CASE_RE = re.compile(r"^<!-- CASE: (.*?) -->$")


def parse_cases(path):
    cases, name, args, mode = [], None, {}, None
    inp, exp = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = CASE_RE.match(line)
        if m:
            head = m.group(1)
            parts = [p.strip() for p in head.split("|")]
            name, args = parts[0], {}
            for kv in parts[1:]:
                k, v = kv.split("=", 1)
                args[k.strip()] = float(v) if "." in v else int(v)
            inp, exp, mode = [], [], None
        elif line == "<!-- INPUT -->":
            mode = "in"
        elif line == "<!-- EXPECT -->":
            mode = "exp"
        elif line == "<!-- END -->":
            cases.append((name, args, "\n".join(inp) + "\n",
                          "\n".join(exp) + "\n"))
            mode = None
        elif mode == "in":
            inp.append(line)
        elif mode == "exp":
            exp.append(line)
    return cases


def main():
    cases = parse_cases(ROOT / "tests" / "clean_markdown_cases.md")
    failed = 0
    for name, args, inp, exp in cases:
        got, _report, *_rest = clean_text(inp, args)
        again, _r2, *_rest2 = clean_text(got, args)
        ok = got == exp
        idem = again == got
        status = "PASS" if ok and idem else "FAIL"
        extra = "" if idem else "  [NOT IDEMPOTENT]"
        print(f"{status}  {name}{extra}")
        if not ok:
            failed += 1
            for d in difflib.unified_diff(exp.splitlines(), got.splitlines(),
                                          "expected", "got", lineterm=""):
                print("   ", d)
        elif not idem:
            failed += 1
            for d in difflib.unified_diff(got.splitlines(), again.splitlines(),
                                          "first-pass", "second-pass",
                                          lineterm=""):
                print("   ", d)
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
