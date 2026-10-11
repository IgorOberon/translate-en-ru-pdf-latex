"""Book-supplied, checked editorial data. No built-in author/term substitutions."""
import re
import json
from pathlib import Path
from provenance import sha_text
from request_plan import PROTECTED


def ocr_findings(text, waivers=()):
    """Conservative review flags, not deletions or inferred source corrections."""
    # Ignore protected math/code and paired Markdown emphasis for this heuristic.
    prose = re.sub(r"```.*?```|`[^`]*`|\$\$.*?\$\$|\$[^$\n]*\$|\*[^*\n]+\*", "", text, flags=re.S)
    patterns = {
        "stray-star": r"(?<=\S)\s+\*(?=\s|$)",
        "isolated-apostrophe": r"(?<!\w)'(?!\w)",
        "mixed-dash-plus": r"--\+",
        "ambiguous-reference": r"\b(?:vergl|vgl|cf)\.\s*[58]\s*\.\s*\d+\.",
        "broken-page-word": r"[A-Za-zÄÖÜäöüß]-\s*$",
        "ocr-dash-noise": r"(?<!\w)(?:={2,}|=-+|-+=|=[“„])",
        "ocr-abbreviation": r"\b3\.\s*B\.",
        "suspect-internal-stop": r"\b(?:sein|ihr|mein|dein|unser|euer)\.\s+(?=[A-ZÄÖÜ])",
    }
    result = []
    for kind, pattern in patterns.items():
        for m in re.finditer(pattern, prose):
            waived = any(w.get("kind") == kind and w.get("source_sha256") == sha_text(text)
                         and w.get("reason") for w in waivers)
            result.append({"kind": kind, "literal": m[0], "source_sha256": sha_text(text),
                           "source": text, "status": "reviewed" if waived else "warning",
                           "action": "verify scan; no automatic deletion"})
    extras = []
    if prose.count("[") != prose.count("]"):
        extras.append(("unbalanced-square-bracket", "[ / ]"))
    extras.extend(("long-quoted-span", m[0]) for m in PROTECTED.finditer(prose)
                  if len(m[0]) > 900 and m[0][0] in '«“„"')
    for kind, literal in extras:
        waived = any(w.get("kind") == kind and w.get("source_sha256") == sha_text(text)
                     and w.get("reason") for w in waivers)
        result.append({"kind": kind, "literal": literal, "source_sha256": sha_text(text),
                       "source": text, "status": "reviewed" if waived else "warning",
                       "action": "verify scan; no automatic deletion"})
    return result


def review_ledger(root, manifest, blocks):
    """Optional source-bound editorial findings; unresolved/stale data fails closed."""
    path = Path(root) / "editorial.findings.json"
    if not path.exists():
        return {"status": "not_run", "findings": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("editorial findings belong to a different manifest")
    seen, pending = set(), []
    for row in data["findings"]:
        if not row.get("id") or row["id"] in seen or row.get("status") not in ("unresolved", "resolved"):
            raise ValueError("invalid/duplicate editorial finding")
        seen.add(row["id"])
        matches = [b for b in blocks if sha_text(b) == row.get("source_sha256")]
        if not matches or not row.get("source_quote") or not any(row["source_quote"] in b for b in matches):
            raise ValueError("editorial finding source hash/quote mismatch")
        if row["status"] == "resolved" and not row.get("resolution"):
            raise ValueError("resolved finding lacks review evidence")
        if row["status"] == "unresolved":
            pending.append(row)
    return {"status": "failed" if pending else "passed", "findings": pending}


def term_guard_findings(source, target, rules):
    """Book-owned aligned-block constraints. They cannot certify semantics."""
    findings, seen = [], set()
    for rule in rules:
        if (not rule.get("id") or rule["id"] in seen or not rule.get("source_pattern")
                or not (rule.get("required_target_pattern") or rule.get("forbidden_target_pattern"))):
            raise ValueError("invalid/duplicate term guard")
        seen.add(rule["id"])
        flags = re.I if rule.get("ignore_case") else 0
        if not re.search(rule["source_pattern"], source, flags):
            continue
        if rule.get("source_exclude_pattern") and re.search(rule["source_exclude_pattern"], source, flags):
            continue
        required, forbidden = rule.get("required_target_pattern"), rule.get("forbidden_target_pattern")
        missing = bool(required and not re.search(required, target, flags))
        conflict = bool(forbidden and re.search(forbidden, target, flags))
        if missing or conflict:
            findings.append({"kind": "term-guard", "rule": rule["id"], "status": "failed",
                             "source_sha256": sha_text(source), "source": source, "target": target,
                             "missing_required": missing, "forbidden_present": conflict,
                             "action": "review/retranslate this context; no global replacement"})
    return findings


def source_review(blocks, cfg):
    profile = cfg.get("ocr_review") or {}
    findings = [dict(row, block=i) for i, block in enumerate(blocks)
                for row in ocr_findings(block, profile.get("waivers", []))]
    pending = [r for r in findings if r["status"] != "reviewed"]
    return {"schema": 1, "status": "failed" if pending and profile.get("strict") else "warning" if pending else "passed",
            "findings": findings, "semantic_review": "not_run"}


def terminology_findings(source, target, rules):
    """Aligned-context suggestions, never a claim of word-to-word correspondence."""
    findings = []
    for rule in rules:
        anchors = [rule.get("anchor", r"(?!x)x"), *rule.get("ocr_variants", [])]
        if not any(re.search(a, source) for a in anchors):
            continue
        competitor = rule.get("competitor")
        findings.append({"rule": rule.get("name", "unnamed"), "status": "warning",
                         "source": source, "target": target,
                         "ambiguous": bool(competitor and re.search(competitor, source)),
                         "action": "review aligned context; no automatic replacement"})
    return findings


def apply_corrections(sources, targets, rules, stage="postprocess"):
    """Whole target-block replacements with exact source and old/new checks.

    A deliberately narrow format avoids guessing which Russian occurrence a
    source term refers to. Matching the full new block makes replay idempotent.
    """
    result, journal, seen = list(targets), [], set()
    for rule in rules:
        required = {"id", "stage", "source_sha256", "source_anchor", "old", "new", "reason", "expected_matches"}
        if not required <= rule.keys() or rule["id"] in seen:
            raise ValueError("incomplete/duplicate correction ID")
        seen.add(rule["id"])
        if rule["stage"] != stage or rule["expected_matches"] != 1 or not rule["reason"]:
            raise ValueError(f"invalid correction stage/count/reason: {rule['id']}")
        matches = [i for i, s in enumerate(sources) if sha_text(s) == rule["source_sha256"]
                   and rule["source_anchor"] in s]
        if len(matches) != 1:
            raise ValueError(f"source anchor/hash mismatch: {rule['id']}")
        i = matches[0]
        if result[i] == rule["new"]:
            continue
        if result[i] != rule["old"]:
            raise ValueError(f"expected old text mismatch: {rule['id']}")
        journal.append({"id": rule["id"], "stage": stage, "block": i,
                        "source_sha256": rule["source_sha256"], "before": result[i],
                        "after": rule["new"], "reason": rule["reason"]})
        result[i] = rule["new"]
    return result, journal


def reference_findings(text, known_targets):
    """Diagnose internal targets; keep page/next-paragraph/external references literal."""
    rows = []
    for m in re.finditer(r"folg\.\s*§\.?\s*\d*|\bS\.\s*\d+|§§?\.?\s*\d+(?:\s*[–-]\s*\d+)?", text):
        literal = m.group()
        context = text[max(0, m.start() - 80):m.end() + 80]
        if literal.startswith("S."):
            kind, status = "page", "passed"
        elif literal.startswith("folg."):
            kind, status = "next_paragraph_uncertain", "warning"
        elif re.search(r"\b(?:Band|Bd\.|том|volume|vol\.)", context, re.I):
            kind, status = "external_or_uncertain", "warning"
        else:
            nums = list(map(int, re.findall(r"\d+", literal)))
            if len(nums) == 2:
                nums = list(range(nums[0], nums[1] + 1))
            kind = "internal"
            status = "passed" if all(n in known_targets for n in nums) else "warning"
        rows.append({"literal": literal, "offset": m.start(), "kind": kind, "status": status})
    return rows
