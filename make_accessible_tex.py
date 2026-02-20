#!/usr/bin/env python3
"""
make_accessible_tex.py - LaTeX PDF Accessibility + HTML/MathML Tool
                         (plain .tex version — no .shn preprocessor needed)

Applies PDF accessibility improvements to standard LaTeX files and
optionally generates self-contained HTML with MathML via Pandoc.

Usage:
    python make_accessible_tex.py --pdf   paper.tex
    python make_accessible_tex.py --html  paper.tex
    python make_accessible_tex.py --all   paper.tex
    python make_accessible_tex.py --batch [--pdf] [--html]  # all .tex in dir

What --pdf adds (idempotent — safe to re-run):
    \\usepackage[T1]{fontenc}        proper font encoding for text extraction
    \\usepackage{lmodern}            Latin Modern (looks like Computer Modern)
    \\usepackage[utf8]{inputenc}     UTF-8 source encoding
    \\usepackage[english]{babel}     document language declaration
    \\usepackage[...]{hyperref}      PDF metadata + blue clickable links
    \\usepackage{pdfcomment}         alt-text tooltips on images (if installed)
    \\pdftooltip{}{} wrappers       around every \\includegraphics call

Requirements:
    pandoc   (for --html, must be on PATH)
    pdflatex (to build the PDF afterward)
    pdfcomment LaTeX package (optional but recommended for alt-text tooltips)
"""

import re
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

AUTHOR   = 'Your Name'          # <-- change this
SUBJECT  = 'Your Subject'       # <-- change this
KEYWORDS = 'keyword1, keyword2' # <-- change this

# Marker prefix on auto-generated alt-text — search for this to find and fix.
ALT_MARKER = '***!!***Guess by make_accessible_tex.py:'

# ── Preamble patching ─────────────────────────────────────────────────────────

ACCESSIBILITY_PACKAGES = """\
\\usepackage[T1]{fontenc}
\\usepackage{lmodern}
\\usepackage[utf8]{inputenc}
\\usepackage[english]{babel}"""

def build_hyperref_block(title: str) -> str:
    return f"""\
\\usepackage[pdftex,
    pdftitle={{{title}}},
    pdfauthor={{{AUTHOR}}},
    pdflang={{en-US}},
    pdfsubject={{{SUBJECT}}},
    pdfkeywords={{{KEYWORDS}}},
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue,
    citecolor=blue,
    unicode]{{hyperref}}
\\IfFileExists{{pdfcomment.sty}}{{\\usepackage{{pdfcomment}}}}{{\\newcommand{{\\pdftooltip}}[2]{{#1}}}}"""

def already_patched(text: str) -> bool:
    return 'fontenc' in text and 'lmodern' in text and 'pdftitle' in text

def get_title(tex_path: Path, text: str) -> str:
    """Extract title from \\title{} command, falling back to filename."""
    m = re.search(r'\\title\{([^}]+)\}', text)
    if m:
        # Strip LaTeX formatting from the title for use in PDF metadata
        t = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', m.group(1))
        t = re.sub(r'\\[a-zA-Z]+\s*', '', t).strip()
        return t
    return tex_path.stem.replace('_', '\_')

def patch_preamble(text: str, title: str) -> str:
    """
    Insert accessibility packages into the LaTeX preamble.

    Strategy:
      1. If \\usepackage{graphicx} exists, insert before it.
      2. If \\usepackage{hyperref} exists (bare), replace it.
      3. Otherwise insert right after \\documentclass{...}.
    """
    hyperref_block = build_hyperref_block(title)

    # Case 1: graphicx already present — insert before it
    graphicx_pat = re.compile(r'(\\usepackage(?:\[[^\]]*\])?\{graphicx\})')
    bare_href_pat = re.compile(r'\\usepackage(?:\[[^\]]*\])?\{hyperref\}')

    if graphicx_pat.search(text):
        # Remove bare \usepackage{hyperref} if present (we'll add our own)
        text = bare_href_pat.sub('', text)
        text = graphicx_pat.sub(
            ACCESSIBILITY_PACKAGES + r'\n\1\n' + hyperref_block,
            text, count=1)

    # Case 2: hyperref present but no graphicx — replace it
    elif bare_href_pat.search(text):
        text = bare_href_pat.sub(
            ACCESSIBILITY_PACKAGES + '\n' + hyperref_block,
            text, count=1)

    # Case 3: nothing useful — insert after \documentclass line
    else:
        docclass_pat = re.compile(r'(\\documentclass(?:\[[^\]]*\])?\{[^}]+\})')
        text = docclass_pat.sub(
            r'\1\n' + ACCESSIBILITY_PACKAGES + '\n' + hyperref_block,
            text, count=1)

    return text

# ── Image alt-text wrapping ───────────────────────────────────────────────────

INCL_RE = re.compile(r'\\includegraphics(\[[^\]]*\])?\{([^}]+)\}')

def guess_alt(filename: str) -> str:
    """Make a rough alt-text guess from the image filename."""
    name = Path(filename).stem.lower()

    known = {
        'traystack':        'Photo of a spring-loaded cafeteria tray stack, '
                            'analogy for the stack data structure',
        'pathfinder':       'NASA Mars Pathfinder rover',
        'rs232_serialbits': 'RS-232 serial bit frame timing diagram',
        'rs232_db25pinout': 'DB-25 connector pinout for RS-232',
    }
    if name in known:
        return known[name]

    # Attempt a human-readable name from the filename
    readable = re.sub(r'[-_]', ' ', name)
    readable = re.sub(r'\d{4,}', '', readable).strip()   # strip long numbers
    if readable:
        return f'Figure: {readable}'
    return f'Figure ({Path(filename).name})'

def is_already_wrapped(text: str, match_start: int) -> bool:
    """Return True if this \\includegraphics is inside \\pdftooltip{...}."""
    preceding = text[:match_start]
    last_tt = preceding.rfind('\\pdftooltip{')
    if last_tt == -1:
        return False
    # Count brace depth from last_tt to match_start
    depth = 0
    for ch in text[last_tt:match_start]:
        if ch == '{': depth += 1
        elif ch == '}': depth -= 1
    return depth > 0   # still inside the first arg of \pdftooltip

def wrap_images(text: str) -> str:
    """Wrap every bare \\includegraphics with \\pdftooltip{}{}."""
    result = []
    prev = 0
    for m in INCL_RE.finditer(text):
        result.append(text[prev:m.start()])
        if is_already_wrapped(text, m.start()):
            result.append(m.group(0))
        else:
            opts  = m.group(1) or ''
            fname = m.group(2)
            alt   = f'{ALT_MARKER} {guess_alt(fname)}'
            result.append(f'\\pdftooltip{{\\includegraphics{opts}{{{fname}}}}}{{{alt}}}')
        prev = m.end()
    result.append(text[prev:])
    return ''.join(result)

# ── PDF accessibility entry point ─────────────────────────────────────────────

def apply_pdf_accessibility(tex_path: Path, make_backup: bool = True):
    print(f'\n[PDF] {tex_path.name}')
    text = tex_path.read_text()

    if already_patched(text):
        print('  preamble already patched — checking images only')
        new_text = wrap_images(text)
    else:
        title = get_title(tex_path, text)
        print(f'  title: {title}')
        new_text = patch_preamble(text, title)
        new_text = wrap_images(new_text)

    if new_text != text:
        if make_backup:
            bak = tex_path.with_suffix('.tex.bak')
            shutil.copy2(tex_path, bak)
            print(f'  backup → {bak.name}')
        tex_path.write_text(new_text)
        print('  written.')
    else:
        print('  no changes needed.')

# ── HTML + MathML generation ──────────────────────────────────────────────────

def extract_alt_map(tex_text: str) -> dict:
    alt_map = {}
    pat = re.compile(
        r'\\pdftooltip\{\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}\}\{([^}]+)\}')
    for m in pat.finditer(tex_text):
        alt_map[Path(m.group(1)).name] = m.group(2).strip()
    return alt_map

def preprocess_for_pandoc(tex_text: str) -> str:
    """Strip pdftooltip wrappers and other pdfcomment commands before Pandoc."""
    # Unwrap \pdftooltip{\includegraphics...}{alt} → \includegraphics...
    tex_text = re.sub(
        r'\\pdftooltip\{(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})\}\{[^}]+\}',
        r'\1', tex_text)
    # Remove pdfcomment-related lines Pandoc can't parse
    tex_text = re.sub(r'[^\n]*IfFileExists[^\n]*pdfcomment[^\n]*\n', '', tex_text)
    tex_text = re.sub(r'[^\n]*usepackage\{pdfcomment\}[^\n]*\n', '', tex_text)
    return tex_text

def postprocess_html(html: str, alt_map: dict) -> str:
    def add_alt(m):
        tag = m.group(0)
        src_m = re.search(r'src="([^"]+)"', tag)
        if not src_m or 'alt=' in tag:
            return tag
        fname = Path(src_m.group(1)).name
        alt = alt_map.get(fname, '')
        return tag.replace('<img ', f'<img alt="{alt}" ', 1) if alt else tag
    return re.sub(r'<img [^>]+>', add_alt, html)

def generate_html(tex_path: Path):
    print(f'\n[HTML] {tex_path.name}')
    if not shutil.which('pandoc'):
        print('  ERROR: pandoc not found on PATH', file=sys.stderr)
        return

    tex_text = tex_path.read_text()
    alt_map  = extract_alt_map(tex_text)
    clean    = preprocess_for_pandoc(tex_text)

    tmp = tex_path.with_suffix('.pandoc_tmp.tex')
    tmp.write_text(clean)

    html_path = tex_path.with_suffix('.html')
    title = get_title(tex_path, tex_text)

    result = subprocess.run([
        'pandoc',
        '--from=latex',
        '--to=html5',
        '--mathml',
        '--standalone',
        '--embed-resources',
        f'--metadata=title:{title}',
        '--metadata=lang:en-US',
        str(tmp),
        '-o', str(html_path),
    ], capture_output=True, text=True)

    tmp.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f'  pandoc error:\n{result.stderr}', file=sys.stderr)
        return

    html = html_path.read_text()
    html = postprocess_html(html, alt_map)
    html_path.write_text(html)
    print(f'  → {html_path.name}  ({len(alt_map)} images with alt text)')
    if result.stderr:
        print(f'  pandoc warnings: {result.stderr[:200]}')

# ── CLI ───────────────────────────────────────────────────────────────────────

def find_tex_files(directory: Path):
    """Find .tex files that look like top-level documents (have \\documentclass)."""
    results = []
    for p in sorted(directory.glob('*.tex')):
        text = p.read_text(errors='ignore')
        if '\\documentclass' in text:
            results.append(p)
    return results

def main():
    parser = argparse.ArgumentParser(
        description='Plain LaTeX accessibility tool (PDF + HTML/MathML)')
    parser.add_argument('files', nargs='*', help='.tex files to process')
    parser.add_argument('--pdf',      action='store_true',
                        help='Apply PDF accessibility changes')
    parser.add_argument('--html',     action='store_true',
                        help='Generate HTML+MathML via Pandoc')
    parser.add_argument('--all',      action='store_true',
                        help='Apply both --pdf and --html')
    parser.add_argument('--batch',    action='store_true',
                        help='Process all top-level .tex files in current directory')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip .bak backups when patching')
    args = parser.parse_args()

    do_pdf  = args.pdf  or args.all
    do_html = args.html or args.all

    if not do_pdf and not do_html:
        parser.print_help()
        print('\nSpecify at least one of --pdf, --html, or --all.')
        sys.exit(1)

    if args.batch:
        files = find_tex_files(Path('.'))
        if not files:
            print('No top-level .tex files found.')
            sys.exit(0)
    else:
        if not args.files:
            parser.error('Provide file(s) or use --batch')
        files = [Path(f) for f in args.files]

    for f in files:
        if not f.exists():
            print(f'WARNING: {f} not found — skipping', file=sys.stderr)
            continue
        if do_pdf:
            apply_pdf_accessibility(f, make_backup=not args.no_backup)
        if do_html:
            generate_html(f)

    print('\nDone.')

if __name__ == '__main__':
    main()
