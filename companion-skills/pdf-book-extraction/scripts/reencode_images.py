#!/usr/bin/env python3
"""Re-encode every image in a folder to baseline RGB JPEG.

Cures TeX-driver failures (xdvipdfmx / MiKTeX) on progressive, CMYK, or
otherwise exotic JPEGs that image viewers open fine but LaTeX cannot load.
Idempotent and safe to re-run; makes a one-time backup next to the folder.

Usage:
  pip install pillow
  python scripts/reencode_images.py build/images
"""
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("!! нужен Pillow:  pip install pillow")
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    folder = Path(sys.argv[1]).resolve()
    if not folder.is_dir():
        print(f"!! нет такой папки: {folder}")
        sys.exit(1)

    backup = folder.parent / (folder.name + "_orig")
    if not backup.exists():
        shutil.copytree(folder, backup)
        print(f">> резервная копия: {backup}")
    else:
        print(f">> резервная копия уже есть: {backup}")

    exts = {".jpg", ".jpeg", ".png"}
    files = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in exts]
    fixed = kept = failed = 0
    for p in files:
        try:
            with Image.open(p) as im:
                exotic = (im.mode != "RGB") or ("progression" in im.info) \
                         or ("progressive" in im.info) or (p.suffix.lower() == ".png")
                rgb = im.convert("RGB")
                rgb.save(p.with_suffix(".jpg"), "JPEG",
                         quality=92, optimize=True, progressive=False)
            fixed += 1 if exotic else 0
            kept += 0 if exotic else 1
        except Exception as e:
            failed += 1
            print(f"!! {p.name}: {e}")
    print(f"\nготово: перекодировано {len(files)} файлов "
          f"(были экзотическими: {fixed}, уже baseline: {kept}, ошибок: {failed})")
    print("теперь пересоберите книгу: xelatex дважды")


if __name__ == "__main__":
    main()
