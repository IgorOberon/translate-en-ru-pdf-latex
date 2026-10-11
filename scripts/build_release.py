"""Shared bounded LaTeX build, technical acceptance and atomic publication."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time

from provenance import canonical_hash, sha_file, write_json


def aux_state(build):
    build = Path(build)
    return canonical_hash({p.relative_to(build).as_posix(): sha_file(p)
                           for p in sorted(build.rglob("*"))
                           if p.suffix in (".aux", ".toc", ".out", ".lof", ".lot")})


def compile_latex(main, output=None, engine="xelatex", max_passes=4, runner=None):
    """output must be a new candidate directory; source paths remain relative to main."""
    runner = runner or subprocess.run
    main = Path(main).resolve()
    output = Path(output or main.parent).resolve()
    output.mkdir(parents=True, exist_ok=True)
    pdf = output / (main.stem + ".pdf")
    report = {"stage": "compile", "status": "failed", "passes": [],
              "source_sha256": sha_file(main), "started_ns": time.time_ns()}
    if pdf.exists():
        report["error"] = "candidate PDF already exists; use a fresh build directory"
        write_json(output / "compile.report.json", report)
        return report
    # \include writes chapter.aux under the output directory, not the source tree.
    pending, seen = [main], set()
    while pending:
        path = pending.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for kind, name in re.findall(r"\\(include|input)\{([^}]+)\}", path.read_text(encoding="utf-8")):
            child = (main.parent / name).with_suffix(".tex").resolve()
            if not child.is_relative_to(main.parent):
                continue
            if kind == "include":
                (output / child.relative_to(main.parent).parent).mkdir(parents=True, exist_ok=True)
            pending.append(child)
    previous = None
    source_files = {str(path): sha_file(path) for path in seen if path.is_file()}
    report["inputs_sha256"] = canonical_hash(source_files)
    for n in range(1, max_passes + 1):
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
               "-no-shell-escape", f"-output-directory={output}", main.name]
        try:
            with (output / f"pass-{n}.log").open("wb") as stream:
                result = runner(cmd, cwd=main.parent, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=600)
            rc = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["error"] = str(exc)
            break
        state = aux_state(output)
        report["passes"].append({"pass": n, "rc": rc, "aux_sha256": state})
        if rc:
            report["error"] = f"{engine} returned {rc}"
            break
        log = output / (main.stem + ".log")
        log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        rerun = re.search(r"Rerun to get|Label\(s\) may have changed|Please rerun", log_text, re.I)
        if state == previous and not rerun and pdf.is_file() and log.exists():
            if any(not Path(path).is_file() or sha_file(path) != digest for path, digest in source_files.items()):
                report["error"] = "TeX inputs changed during compilation"
                break
            report.update(status="passed", pdf_sha256=sha_file(pdf), stabilized=True)
            break
        previous = state
    else:
        report["error"] = "aux/toc did not stabilize within pass limit"
    if report["status"] != "passed":
        report.setdefault("error", "fresh PDF/log not produced")
    write_json(output / "compile.report.json", report)
    return report


def inspect_pdf(pdf, log, require_toc=False, source_text=""):
    """Technical checks only. Visual/semantic review are explicitly not_run."""
    pdf, log = Path(pdf), Path(log)
    result = {"stage": "technical_pdf", "status": "failed", "errors": [], "warnings": [],
              "visual_review": {"status": "not_run", "pages": []}, "semantic_review": "not_run"}
    errors = result["errors"]
    if not pdf.is_file() or not log.is_file():
        errors.append("PDF/log missing")
        return result
    text = log.read_text(encoding="utf-8", errors="replace")
    for pattern, name in [(r"(?m)^!|Emergency stop|Fatal error", "TeX error"),
                          (r"Missing character:", "Missing character"),
                          (r"undefined references|Reference .* undefined|Citation .* undefined", "unresolved references"),
                          (r"multiply defined", "duplicate labels")]:
        if re.search(pattern, text, re.I):
            errors.append(name)
    over = [float(n) for n in re.findall(r"Overfull \\[hv]box \((\d+(?:\.\d+)?)pt", text)]
    if over:
        result["warnings"].append({"kind": "overfull", "count": len(over), "max_pt": max(over),
                                   "review": "inspect affected pages in main.log"})
    try:
        import fitz
        from translate import added_cjk, leaks_instructions
        with fitz.open(pdf) as doc:
            if not len(doc):
                errors.append("empty PDF")
            content = "\n".join(page.get_text() for page in doc)
            if not content.strip():
                errors.append("no readable PDF text")
            if re.search(r"⟦M\d{6}⟧|(?<!\w)M\d{6}(?!\w)", content):
                errors.append("unexpanded mask in PDF")
            if "[рисунок не найден]" in content:
                errors.append("missing image placeholder")
            toc = doc.get_toc()
            if require_toc and (not toc or not (pdf.parent / (pdf.stem + ".toc")).is_file()):
                errors.append("required ToC/bookmarks missing")
            if any(not 1 <= row[2] <= len(doc) for row in toc):
                errors.append("invalid bookmark destination")
            titles = "\n".join(row[1] for row in toc)
            if leaks_instructions(source_text, titles) or added_cjk(source_text, titles):
                errors.append("unexpected script/control text in bookmarks")
            fonts = {font[0]: font for page in doc for font in page.get_fonts(full=True)}
            font_rows = []
            for xref, font in fonts.items():
                embedded = bool(doc.extract_font(xref)[3]) if xref else False
                font_rows.append({"name": font[3], "type": font[2], "embedded": embedded})
                if font[2] == "Type3" or not embedded:
                    errors.append(f"unembedded/Type3 font: {font[3]}")
            result.update(pages=len(doc), bookmarks=len(toc), fonts=font_rows,
                          pdf_sha256=sha_file(pdf), log_sha256=sha_file(log))
    except Exception as exc:
        errors.append(f"PDF inspection failed: {exc}")
    result["status"] = "failed" if errors else "passed"
    return result


def publish_candidate(pdf, destination, report):
    """Only a passed release report for these exact bytes can replace a final file."""
    if (report.get("status") != "passed" or report.get("profile") != "release"
            or report.get("pdf_sha256") != sha_file(pdf)
            or report.get("technical", {}).get("status") != "passed"
            or report.get("technical", {}).get("pdf_sha256") != sha_file(pdf)
            or report.get("compile", {}).get("status") != "passed"
            or report.get("compile", {}).get("pdf_sha256") != sha_file(pdf)):
        raise ValueError("candidate has not passed release acceptance")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".publish-", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    try:
        shutil.copyfile(pdf, tmp)
        if sha_file(tmp) != report["pdf_sha256"]:
            raise ValueError("candidate changed during publication")
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    write_json(str(destination) + ".release.json", report)
