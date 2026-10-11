#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synchronize the curated pipeline into a skill folder, retaining previous files.

No recursive deletes: destination-only resources are left alone. Each changed
file is backed up under .sync-backups/<run>/ before replacement. The same reviewed
inventory/secret gate as make_package.py is used, including new modules/docs.
"""
import argparse
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_package import NAME, SKILL_NAME, package_files, package_profile
from paths import ROOT
from provenance import inside, sha_file, write_json


def sync(destination, dry=False):
    destination = Path(destination).resolve()
    source = ROOT.resolve()
    if destination == source or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("skill destination must be outside the source checkout")
    profile = package_profile(source)
    files = package_files(source, profile=profile)
    run = uuid.uuid4().hex
    changed = []
    for name in files:
        src = inside(source, name)
        dst = inside(destination, name)
        if dst.is_file() and sha_file(src) == sha_file(dst):
            continue
        changed.append(name)
        if dry:
            continue
        if dst.exists():
            backup = inside(destination, ".sync-backups/" + run + "/" + name)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if not dry:
        manifest_path = destination / "package.manifest.json"
        if manifest_path.exists():
            backup = inside(destination, ".sync-backups/" + run + "/package.manifest.json")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, backup)
        write_json(destination / "package.manifest.json", {"schema": 1,
                   "name": SKILL_NAME if profile == "user" else NAME,
                   "profile": profile,
                   "files": {name: sha_file(inside(destination, name)) for name in files}})
        for name in files:
            if sha_file(inside(destination, name)) != sha_file(inside(source, name)):
                raise ValueError("sync changed during copy: " + name)
    print(("would update" if dry else "updated") + f": {len(changed)} files -> {destination}")
    for name in changed:
        print("  " + name)
    if changed and not dry:
        print(f"old changed files retained under .sync-backups/{run}; destination-only files unchanged")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest")
    ap.add_argument("--agent-skills", nargs="?", const=str(Path.home() / "agent-skills/translate-pdf-latex"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    targets = [Path(a.dest) if a.dest else Path.home() / ".claude/skills/translate-pdf-latex"]
    if a.agent_skills:
        targets.append(Path(a.agent_skills))
    for target in dict.fromkeys(targets):
        sync(target, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
