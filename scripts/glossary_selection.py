"""Optional book-owned glossary groups; critical entries are never dropped."""
import json
from pathlib import Path
import re


def load_profile(path=None):
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("glossary profile requires schema: 1")
    entries = value.get("critical", [])
    if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
        raise ValueError("critical must be a list of glossary lines")
    for group in value.get("groups", []):
        re.compile(group["source_pattern"])
        if not isinstance(group["entries"], list) or not all(isinstance(x, str) for x in group["entries"]):
            raise ValueError("group entries must be glossary lines")
    return value


def select_glossary(source, base="", profile=None, all_groups=False):
    profile = profile or {}
    entries = [base.strip(), *profile.get("critical", [])]
    for group in profile.get("groups", []):
        if all_groups or re.search(group["source_pattern"], source):
            # Keep each entire group, including the paired/opposed renderings.
            entries.extend(group["entries"])
    return "\n".join(dict.fromkeys(e for e in entries if e))
