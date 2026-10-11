"""Read-only verification of packaged file hashes (stdlib only, no model calls)."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "package.manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if manifest.get("schema") != 1 or not isinstance(files, dict) or not files:
        raise ValueError("invalid package manifest")
    problems = []
    for name, expected in files.items():
        relative = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or relative.is_absolute()
                or ".." in relative.parts or not re.fullmatch(r"[0-9a-f]{64}", str(expected))):
            raise ValueError("unsafe path or invalid hash in manifest")
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("manifest path escapes package")
        if not path.is_file():
            problems.append("MISSING: " + name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append("CHANGED: " + name)
    return len(files), problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    try:
        count, problems = verify(args.root)
    except (OSError, ValueError) as exc:
        print("FAIL:", exc)
        return 1
    for problem in problems:
        print(problem)
    print(f"{'FAIL' if problems else 'OK'}: {count} packaged files checked")
    print("Extra files are not checked. Hashes detect changes, not publisher authenticity.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
