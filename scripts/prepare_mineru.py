"""Loss-aware MinerU adapter: recover page notes and convert simple HTML tables.

Raw OCR remains immutable. Unsupported/ambiguous structures stop before MT;
never guess a note attachment or quietly flatten a complex table.
"""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from provenance import atomic_text, sha_file, sha_text, write_json

VERSION = "mineru-structure-v1"
SUP = re.compile(r"<sup>\s*(\d+|[*†‡])\s*</sup>", re.I)
TABLE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)
NOTE = re.compile(r"\[\^([^\]\s]+)\](:)?")


class SimpleTable(HTMLParser):
    """Deliberately bounded subset, not a general HTML-to-Markdown converter."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell, self.stack = [], None, None, []

    def handle_starttag(self, tag, attrs):
        if tag not in {"table", "thead", "tbody", "tfoot", "tr", "td", "th"}:
            raise ValueError(f"unsupported table markup <{tag}>: review extraction")
        attrs = dict(attrs)
        if any(attrs.get(k, "1") != "1" for k in ("rowspan", "colspan")):
            raise ValueError("merged table cells require explicit review (rowspan/colspan)")
        parent = self.stack[-1] if self.stack else None
        allowed = {"table": {None}, "thead": {"table"}, "tbody": {"table"},
                   "tfoot": {"table"}, "tr": {"table", "thead", "tbody", "tfoot"},
                   "td": {"tr"}, "th": {"tr"}}
        if parent not in allowed[tag]:
            raise ValueError("nested/malformed HTML table")
        self.stack.append(tag)
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"}:
            self.cell = []

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError("unbalanced HTML table")
        if tag in {"td", "th"}:
            value = " ".join("".join(self.cell).split())
            if "|" in value or "\n" in value or "<" in value:
                raise ValueError("ambiguous table cell: explicit normalization required")
            self.row.append(value)
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif data.strip():
            raise ValueError("text outside table cells")

    def markdown(self):
        if self.stack or not self.rows or not self.rows[0]:
            raise ValueError("empty/incomplete HTML table")
        cols = len(self.rows[0])
        if any(len(row) != cols for row in self.rows):
            raise ValueError("ragged HTML table")
        rows = [self.rows[0], ["---"] * cols, *self.rows[1:]]
        return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def pipe_tables(text):
    """Ordered cell grids (excluding Markdown header separators)."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    tables, rows = [], []
    for line in text.splitlines() + [""]:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            rows.append([c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]])
        else:
            if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c) for c in rows[1]):
                tables.append([rows[0], *rows[2:]])
            rows = []
    return tables


def table_signature(text):
    # Numeric and masked cells must stay in their original row/column, not
    # merely retain the same document-wide digit count.
    return [[[re.findall(r"\d+|⟦M\d{6}⟧", c) for c in row] for row in t]
            for t in pipe_tables(text)]


def assert_markdown_structure(source, target):
    if TABLE.search(target):
        raise ValueError("raw HTML table would lose structure in LaTeX")
    if Counter(NOTE.findall(source)) != Counter(NOTE.findall(target)):
        raise ValueError("footnote IDs/definitions changed during preparation or translation")
    if table_signature(source) != table_signature(target):
        raise ValueError("table rows/columns/numeric cells changed")


def assert_typeset_structure(markdown, tex):
    definitions = {m[1] for m in NOTE.finditer(markdown) if m[2]}
    refs = Counter(m[1] for m in NOTE.finditer(markdown) if not m[2])
    if set(refs) != definitions:
        raise ValueError("unresolved/orphan Markdown footnotes before typesetting")
    expected_notes = sum(refs.values())
    if expected_notes and len(re.findall(r"\\footnote\s*\{", tex)) < expected_notes:
        raise ValueError("footnotes lost during Pandoc conversion")
    if len(re.findall(r"\\begin\{(?:longtable|tabular|tabularx)\}", tex)) < len(pipe_tables(markdown)):
        raise ValueError("table structure lost during Pandoc conversion")


def normalize(raw, content, namespace):
    notes, text_items = {}, []
    for item in content:
        kind, page, text = item.get("type"), item.get("page_idx"), item.get("text", "")
        if kind == "page_footnote":
            match = SUP.match(text.strip())
            if not match or not isinstance(page, int):
                raise ValueError("page footnote has no unambiguous label/page")
            key = (page, match[1])
            body = text.strip()[match.end():].strip()
            if key in notes or not body or "\n" in body or SUP.search(body):
                raise ValueError("duplicate, multiline or ambiguous page footnote: review JSON")
            # Hash avoids collisions when page numbering restarts in chunks.
            ident = f"mu-{namespace}-p{page + 1}-n{len(notes) + 1}"
            notes[key] = {"id": ident, "body": body, "page_idx": page, "label": match[1]}
        elif kind == "text":
            text_items.append(item)
    edits, recovered = [], []
    for key, note in notes.items():
        candidates = [(item, m) for item in text_items if item.get("page_idx") == key[0]
                      for m in SUP.finditer(item.get("text", "")) if m[1] == key[1]]
        if len(candidates) != 1:
            raise ValueError(f"note page {key[0]+1}, label {key[1]}: reference is missing/ambiguous")
        item, match = candidates[0]
        anchor = item["text"]
        if raw.count(anchor) != 1:
            raise ValueError("footnote anchor not unique in raw Markdown; review extraction")
        if note["body"] in raw:
            raise ValueError("footnote body already in raw Markdown: review duplicate/attachment")
        start = raw.index(anchor)
        edits.append((start + match.start(), start + match.end(), f"[^{note['id']}]") )
        # Definitions next to their paragraph survive skeleton section splitting.
        edits.append((start + len(anchor), start + len(anchor),
                      f"\n\n[^{note['id']}]: {note['body']}"))
        recovered.append({k: v for k, v in note.items() if k != "body"} |
                         {"body_sha256": sha_text(note["body"])})
    text = raw
    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    if SUP.search(text):
        raise ValueError("unresolved numeric superscript: missing note data or exponent; review before MT")
    count = 0

    def table(match):
        nonlocal count
        parser = SimpleTable()
        parser.feed(match[0])
        parser.close()
        out = parser.markdown()
        count += 1
        return out

    text = TABLE.sub(table, text)
    if re.search(r"</?(?:table|tr|td|th)\b", text, re.I):
        raise ValueError("incomplete/unsupported HTML table remains")
    return text, {"footnotes": recovered, "tables_converted": count}


def prepare(md):
    """Always derive from raw bytes, never modify MinerU output or trust mtime."""
    md = Path(md)
    sidecar = md.with_name(md.stem + "_content_list.json")
    dst = md.with_suffix(".prepared.md")
    report_path = md.with_suffix(".prepare.json")
    raw = md.read_text(encoding="utf-8")
    report = {"schema": 1, "version": VERSION, "status": "failed",
              "source_sha256": sha_file(md),
              "content_list_sha256": sha_file(sidecar) if sidecar.exists() else None}
    try:
        content = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else []
        if not isinstance(content, list):
            raise ValueError("unsupported MinerU content-list schema")
        text, details = normalize(raw, content, report["source_sha256"][:12])
        atomic_text(dst, text)
        report.update(details, status="passed", output_sha256=sha_file(dst))
        write_json(report_path, report)
        print(f">> MinerU structure: {len(details['footnotes'])} notes, "
              f"{details['tables_converted']} HTML tables -> {dst}", flush=True)
        return dst
    except (ValueError, KeyError, TypeError) as exc:
        report["error"] = str(exc)
        write_json(report_path, report)
        raise ValueError(f"MinerU structure not accepted: {exc}; see {report_path}") from exc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("markdown", type=Path)
    prepare(ap.parse_args().markdown)
