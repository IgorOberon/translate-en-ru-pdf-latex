"""Exact request export for an agent-backed translation experiment.

Uses the same byte input, fragment planner, glossary selection and messages as
translate.py. This is file exchange, not a model API or a synthetic translation.
Only run on masked input (formula-free source is checked too).
"""
import argparse
import json
from pathlib import Path
from provenance import load_manifest, inside, canonical_hash, sha_file, sha_text, write_json
from translate import split_blocks, is_translatable, build_messages
from request_plan import plan_fragments
from glossary_selection import load_profile, select_glossary
from mask_math import mask
from editorial import source_review, review_ledger


def export_requests(root, *, model, split_chars=900, source_lang="German", target_lang="Russian",
                    mode="hymt", glossary=None, glossary_profile=None):
    root = Path(root)
    if split_chars < 0:
        raise ValueError("split_chars must be nonnegative")
    manifest = load_manifest(root)
    if review_ledger(root, manifest, split_blocks((root / "book.md").read_text(encoding="utf-8")))["status"] == "failed":
        raise ValueError("unresolved editorial findings before agent export")
    profile_path = root / "structure.json"
    cfg = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    review = source_review(split_blocks((root / "book.md").read_text(encoding="utf-8")), cfg)
    if review["status"] == "failed":
        raise ValueError("strict OCR review failed; review source before agent export")
    glossary_path = Path(glossary) if glossary else root / "glossary.md"
    if glossary and not glossary_path.is_file():
        raise ValueError("explicit glossary does not exist")
    base = glossary_path.read_text(encoding="utf-8").strip() if glossary_path.exists() else ""
    profile = load_profile(glossary_profile)
    requests = {}
    for part in manifest["parts"]:
        source = inside(root, part["path"])
        text = source.read_bytes().decode("utf-8")  # no implicit CRLF normalization
        masked, mapping = mask(text)
        if mapping or masked != text:
            raise ValueError("unmasked math/code/URL found: mask before agent export")
        for index, block in enumerate(split_blocks(text)):
            if not is_translatable(block):
                continue
            for frag, row in enumerate(plan_fragments(block, split_chars)):
                selected = select_glossary(row["text"], base, profile)
                messages = build_messages(row["text"], mode, target_lang, selected, source_lang=source_lang)
                key = canonical_hash(messages)
                request = requests.setdefault(key, {"id": key, "source": row["text"], "messages": messages, "locations": []})
                request["locations"].append({"part": part["path"], "block": index, "fragment": frag,
                                             "source_sha256": sha_file(source), "oversized": row["oversized"]})
    return {"schema": 1, "model": model, "manifest_sha256": manifest["manifest_sha256"],
            "transport": "agent file exchange, not live model API", "requests": list(requests.values())}


def findings_from_answers(root, bundle, answers):
    """Bind agent uncertainties to actual request quotes and current source blocks.

    Free-form notes are not executable corrections. Any invalid ID/quote refuses
    the entire import; callers must retain the raw answers for a human review.
    """
    root = Path(root)
    manifest = load_manifest(root)
    if bundle["manifest_sha256"] != manifest["manifest_sha256"]:
        raise ValueError("foreign agent bundle")
    requests = {r["id"]: r for r in bundle["requests"]}
    findings = []
    for n, row in enumerate(answers.get("uncertainties", []), 1):
        request = requests.get(row.get("id"))
        quote = row.get("source_quote")
        if (not request or not quote or quote not in request["source"]
                or canonical_hash(request["messages"]) != request["id"] or not row.get("note")):
            raise ValueError("agent uncertainty needs a valid request ID, exact source_quote and note")
        for k, loc in enumerate(request["locations"]):
            source = inside(root, loc["part"])
            if sha_file(source) != loc["source_sha256"]:
                raise ValueError("agent source part changed")
            block = split_blocks(source.read_bytes().decode("utf-8"))[loc["block"]]
            if request["source"] not in block:
                raise ValueError("agent fragment not in its claimed source block")
            findings.append({"id": f"agent-{n}-{k}", "request_id": row["id"],
                             "source_sha256": sha_text(block), "source_quote": quote,
                             "note": row["note"], "status": "unresolved"})
    return {"schema": 1, "manifest_sha256": manifest["manifest_sha256"],
            "answers_sha256": canonical_hash(answers), "findings": findings}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir")
    ap.add_argument("output")
    ap.add_argument("--model", required=True)
    ap.add_argument("--split-chars", type=int, default=900)
    ap.add_argument("--source-lang", default="German")
    ap.add_argument("--target-lang", default="Russian")
    ap.add_argument("--mode", choices=["hymt", "generic", "polish"], default="hymt")
    ap.add_argument("--glossary")
    ap.add_argument("--glossary-profile")
    ap.add_argument("--review-answers", help="import exact-quote uncertainties, NOT translation text")
    ap.add_argument("--bundle", help="original request bundle for --review-answers")
    a = ap.parse_args()
    if Path(a.output).exists():
        ap.error("output exists; use a new bundle path to preserve model evidence")
    if a.review_answers:
        if not a.bundle:
            ap.error("--review-answers requires --bundle")
        data = findings_from_answers(a.work_dir,
                                    json.loads(Path(a.bundle).read_text(encoding="utf-8")),
                                    json.loads(Path(a.review_answers).read_text(encoding="utf-8")))
        write_json(a.output, data)
        print(f"Imported {len(data['findings'])} unresolved source-bound findings")
        return
    data = export_requests(a.work_dir, model=a.model, split_chars=a.split_chars,
                           source_lang=a.source_lang, target_lang=a.target_lang, mode=a.mode,
                           glossary=a.glossary, glossary_profile=a.glossary_profile)
    write_json(a.output, data)
    print(f"Exported {len(data['requests'])} exact requests")


if __name__ == "__main__":
    main()
