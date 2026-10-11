#!/usr/bin/env python3
"""Fix pymupdf4llm math output: group Unicode math chars + HTML tags into coherent LaTeX math spans.
Approach: detect "math runs" (sequences of Unicode math chars, digits, HTML tags, operators)
and wrap the entire run in $...$, converting contents to proper LaTeX."""
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# Corrupted plane-1 range (pymupdf4llm bug)
CORRUPTED_RANGE = range(0xD6FC, 0xD800)

# Characters that belong INSIDE a math expression (keep in run)
MATH_INNER_CHARS = set(
    '0123456789.,;:()[]{}<>+-=*/^|_ \t\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6'
    '\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03bf\u03c0\u03c1\u03c3'
    '\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9'
    '\u0391\u0392\u0393\u0394\u0395\u0396\u0397\u0398\u0399\u039a\u039b\u039c'
    '\u039d\u039e\u039f\u03a0\u03a1\u03a3\u03a4\u03a5\u03a6\u03a7\u03a8\u03a9'
    '\u2200\u2202\u2203\u2205\u2207\u2208\u2209\u220b\u2211\u221a\u221d\u221e'
    '\u222b\u222e\u2248\u2260\u2264\u2265\u2190\u2192\u2194\u21d2'
    '\u00d7\u00f7\u00b1\u2213\u00b0\u2032\u223c\u2282\u2283\u2286\u2287'
    '\u2227\u2228\u00ac\u211d\u2115\u2124\u211a\u2102\u27e8\u27e9'
    '\u2212\u2261\u2026\u22ef\u22ee\u00d7'
    '\u2011\u2012\u2013\u2014'
)

UNI_TO_LATEX = {
    # Greek
    "\u03b1": "\\alpha", "\u03b2": "\\beta", "\u03b3": "\\gamma",
    "\u03b4": "\\delta", "\u03b5": "\\epsilon", "\u03b6": "\\zeta",
    "\u03b7": "\\eta", "\u03b8": "\\theta", "\u03b9": "\\iota",
    "\u03ba": "\\kappa", "\u03bb": "\\lambda", "\u03bc": "\\mu",
    "\u03bd": "\\nu", "\u03be": "\\xi", "\u03c0": "\\pi",
    "\u03c1": "\\rho", "\u03c3": "\\sigma", "\u03c4": "\\tau",
    "\u03c5": "\\upsilon", "\u03c6": "\\phi", "\u03c7": "\\chi",
    "\u03c8": "\\psi", "\u03c9": "\\omega",
    "\u0393": "\\Gamma", "\u0394": "\\Delta", "\u0398": "\\Theta",
    "\u039b": "\\Lambda", "\u039e": "\\Xi", "\u03a0": "\\Pi",
    "\u03a3": "\\Sigma", "\u03a6": "\\Phi", "\u03a8": "\\Psi",
    "\u03a9": "\\Omega",
    # Math symbols
    "\u2200": "\\forall", "\u2203": "\\exists", "\u2205": "\\emptyset",
    "\u2207": "\\nabla", "\u2202": "\\partial",
    "\u2208": "\\in", "\u2209": "\\notin", "\u220b": "\\ni",
    "\u2211": "\\sum", "\u221a": "\\sqrt", "\u221e": "\\infty",
    "\u222b": "\\int", "\u222e": "\\oint",
    "\u2248": "\\approx", "\u2260": "\\neq", "\u2264": "\\le", "\u2265": "\\ge",
    "\u2190": "\\leftarrow", "\u2192": "\\rightarrow",
    "\u2194": "\\leftrightarrow", "\u21d2": "\\Rightarrow",
    "\u00d7": "\\times", "\u00f7": "\\div", "\u00b1": "\\pm",
    "\u2213": "\\mp", "\u221d": "\\propto", "\u223c": "\\sim",
    "\u2282": "\\subset", "\u2283": "\\supset",
    "\u2286": "\\subseteq", "\u2287": "\\supseteq",
    "\u2227": "\\land", "\u2228": "\\lor", "\u00ac": "\\neg",
    "\u211d": "\\mathbb{R}", "\u2115": "\\mathbb{N}",
    "\u2124": "\\mathbb{Z}", "\u211a": "\\mathbb{Q}",
    "\u2102": "\\mathbb{C}",
    "\u27e8": "\\langle", "\u27e9": "\\rangle",
    "\u2026": "\\dots", "\u22ef": "\\cdots", "\u22ee": "\\vdots",
    "\u2032": "'",
    "\u2212": "-",
}

GREEK_SYMBOL_CMD = {
    "\u03f5": "\\epsilon", "\u03d1": "\\vartheta", "\u03d5": "\\phi",
    "\u03f0": "\\varkappa", "\u03f1": "\\varrho", "\u03d6": "\\varpi",
}


def try_recover(ch):
    """Try to recover a corrupted plane-1 math char."""
    if ord(ch) not in CORRUPTED_RANGE:
        return None
    try:
        recovered = chr(ord(ch) + 0x10000)
        base = unicodedata.normalize("NFKC", recovered)
        if len(base) == 1 and base != recovered:
            if base in GREEK_SYMBOL_CMD:
                return GREEK_SYMBOL_CMD[base]
            name = unicodedata.name(base, "")
            if "GREEK" in name and "LETTER" in name:
                word = name.split()[-1].lower()
                return "\\" + (word.capitalize() if "CAPITAL" in name else word)
            if base.isascii() and base.isalnum():
                return base
    except (ValueError, OverflowError):
        pass
    return None


def char_to_latex(ch):
    """Convert a single char to its LaTeX math equivalent, or None."""
    if ch in UNI_TO_LATEX:
        return UNI_TO_LATEX[ch]
    rec = try_recover(ch)
    if rec:
        return rec
    return None


def is_math_trigger(ch):
    """Is this character a Unicode math symbol that triggers math mode?"""
    return ch in UNI_TO_LATEX or try_recover(ch) is not None


def is_inner_char(ch):
    """Can this character be inside a math run (alongside math symbols)?"""
    return ch in MATH_INNER_CHARS or ch.isascii() and ch.isalnum()


# Math span regex: $...$, $$...$$, \(...\), \[...\], and \$
MATH_DELIM_RE = re.compile(
    r'(?<!\\)\$\$.*?\$\$'
    r'|(?<!\\)\$(?!\$).*?(?<!\\)\$'
    r'|\\\(.*?\\\)'
    r'|\\\[.*?\\\]')


def convert_math_run(run):
    """Convert a math run (sequence of chars and HTML tags) to LaTeX math."""
    # First, convert HTML sub/sup tags to LaTeX
    run = re.sub(r'<sup>(.*?)</sup>', r'^{\1}', run)
    run = re.sub(r'<sub>(.*?)</sub>', r'_{\1}', run)
    
    # Convert Unicode math chars to LaTeX
    result = []
    for ch in run:
        latex = char_to_latex(ch)
        if latex:
            result.append(latex)
        else:
            result.append(ch)
    
    # Strip leading/trailing whitespace from the math expression
    inner = ''.join(result).strip()
    if inner and not inner.isspace():
        return f'${inner}$'
    return run


def fix_line(line):
    """Fix one line: find math runs outside existing math spans, group and convert."""
    if not line.strip():
        return line, 0
    stripped = line.strip()
    if stripped.startswith('```') or stripped.startswith('---'):
        return line, 0
    if line.startswith('    ') or line.startswith('\t'):
        return line, 0
    
    # Split line into: [text, math_span, text, math_span, ...]
    spans = list(MATH_DELIM_RE.finditer(line))
    
    if not spans:
        # No existing math spans — process the whole line
        return _fix_text_segment(line)
    
    result = []
    pos = 0
    total_changed = 0
    for m in spans:
        before = line[pos:m.start()]
        fixed_before, c = _fix_text_segment(before)
        result.append(fixed_before)
        total_changed += c
        # Process HTML tags inside math spans too (convert <sup>/<sub>)
        math_span = m.group(0)
        fixed_math = re.sub(r'<sup>(.*?)</sup>', r'^{\1}', math_span)
        fixed_math = re.sub(r'<sub>(.*?)</sub>', r'_{\1}', fixed_math)
        result.append(fixed_math)
        pos = m.end()
    
    after = line[pos:]
    fixed_after, c = _fix_text_segment(after)
    result.append(fixed_after)
    total_changed += c
    
    return ''.join(result), total_changed


def _fix_text_segment(text):
    """Find and convert math runs in a text segment (outside $...$)."""
    if not text:
        return text, 0
    
    result = []
    i = 0
    changed = 0
    
    while i < len(text):
        ch = text[i]
        if is_math_trigger(ch):
            # Find the full math run
            j = i
            # Scan forward: collect contiguous math trigger chars, inner chars, and HTML tags
            while j < len(text):
                cj = text[j]
                if is_math_trigger(cj) or is_inner_char(cj):
                    j += 1
                    continue
                # Check for HTML tag start
                if text[j:j+5] == '<sup>' or text[j:j+6] == '</sup>' or text[j:j+5] == '<sub>' or text[j:j+6] == '</sub>':
                    # Find end of tag
                    end_tag = text.index('>', j) + 1
                    j = end_tag
                    continue
                break
            
            run = text[i:j]
            converted = convert_math_run(run)
            result.append(converted)
            if converted != run:
                changed += 1
            i = j
        else:
            # Check for HTML tags even without math trigger
            tag_handled = False
            if text[i:i+5] == '<sup>':
                try:
                    end = text.index('</sup>', i) + 6
                    inner = text[i+5:end-6]
                    result.append(f'\\textsuperscript{{{inner}}}')
                    changed += 1
                    i = end
                    tag_handled = True
                except ValueError:
                    pass
            if not tag_handled and text[i:i+5] == '<sub>':
                try:
                    end = text.index('</sub>', i) + 6
                    inner = text[i+5:end-6]
                    result.append(f'\\textsubscript{{{inner}}}')
                    changed += 1
                    i = end
                    tag_handled = True
                except ValueError:
                    pass
            if not tag_handled:
                result.append(ch)
                i += 1
    
    return ''.join(result), changed


def fix_markdown(path_in, path_out):
    text = Path(path_in).read_text(encoding='utf-8')
    lines = text.split('\n')
    fixed_lines = []
    changed_lines = 0

    for line in lines:
        new_line, chg = fix_line(line)
        fixed_lines.append(new_line)
        if chg > 0:
            changed_lines += 1

    Path(path_out).write_text('\n'.join(fixed_lines), encoding='utf-8')
    print(f'Fixed {changed_lines} lines in {path_out}')
    return changed_lines


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: fix_unicode_math.py <input.md> <output.md>')
        sys.exit(1)
    fix_markdown(sys.argv[1], sys.argv[2])
