#!/usr/bin/env python3
r"""
make_accessible.py - ECE 474 Course Materials Accessibility Tool

Automates two tasks:
  1. PDF accessibility: adds font encoding, language, hyperref metadata,
     and \pdftooltip alt-text stubs around \includegraphics calls.
  2. HTML+MathML generation: runs coursetex then pandoc to produce
     self-contained HTML with MathML for equations.

Usage:
    python make_accessible.py --shn   Cprog.shn        # patch .shn source only
    python make_accessible.py --html  Cprog.shn        # HTML only (prompts for version)
    python make_accessible.py --html  --version n  Cprog.shn  # HTML, notes version
    python make_accessible.py --all   Cprog.shn        # both
    python make_accessible.py --batch [--shn] [--html] # all .shn files in dir

Requirements:
    coursetex (Perl preprocessor, must be on PATH)
    pandoc    (for HTML output)
    pdflatex  (for PDF output)
"""

import re
import subprocess
import sys
import os
import argparse
import shutil
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

AUTHOR   = "Blake Hannaford, University of Washington"
SUBJECT  = "ECE 474 Embedded Microcomputer Systems"
KEYWORDS = "embedded systems, microcontrollers, ECE 474"

# Per-file title lookup; falls back to filename stem.
TITLE_MAP = {
    '474_IntroW22':       'ECE 474: Course Introduction',
    'Cprog':              'ECE 474: Structure and Compilation of C Programs',
    'Hardware_IO':        'ECE 474: Hardware and Basic I/O',
    'Interrupts':         'ECE 474: Interrupts',
    'Schedulers':         'ECE 474: Schedulers',
    'SchedImplementation':'ECE 474: Scheduler Implementation',
    'Pointers':           'ECE 474: Pointers in C',
    'CritSect':           'ECE 474: Critical Sections',
    'Serial':             'ECE 474: Serial Communication',
    'USB':                'ECE 474: Introduction to USB',
    'ConstDef':           'ECE 474: C Constants and Preprocessor Directives',
    'Secure':             'ECE 474: Secure Coding',
    'MicroCos':           'ECE 474: Micro-C OS/II Overview',
}

# Default coursetex version to use when generating .tex for HTML conversion.
# 'n' (notes) gives the most complete prose output.
HTML_VERSION = 'n'

# Marker placed in auto-generated alt-text so humans can find and fix them.
ALT_MARKER = r'***!!***Guess by make_accessible.py:'

# ── Helpers ──────────────────────────────────────────────────────────────────

def pdf_title(shn_path: Path) -> str:
    stem = shn_path.stem
    if stem in TITLE_MAP:
        return TITLE_MAP[stem]
    # Try to pull a title from the header comment block
    with open(shn_path) as f:
        for line in f:
            m = re.match(r'%+\s*(.+)', line)
            if m:
                t = m.group(1).strip('%').strip()
                if t:
                    return f'ECE 474: {t}'
    return f'ECE 474: {stem}'


def backup(path: Path):
    bak = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, bak)
    print(f'  backup → {bak.name}')


def run(cmd, **kwargs):
    print(f'  $ {" ".join(cmd)}')
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f'  ERROR: command failed (exit {result.returncode})', file=sys.stderr)
    return result


# ── Part 1: PDF accessibility changes ────────────────────────────────────────

# The accessibility preamble block we insert.  {prefix} is either '<shn>' for
# .shn files or '' for plain .tex files.  {title} is filled per-file.
PREAMBLE_TEMPLATE = """\
{prefix}\\usepackage[T1]{{fontenc}}
{prefix}\\usepackage{{lmodern}}
{prefix}\\usepackage[utf8]{{inputenc}}
{prefix}\\usepackage[english]{{babel}}"""

HYPERREF_TEMPLATE = """\
{prefix}\\usepackage[pdftex,
{prefix}    pdftitle={{{title}}},
{prefix}    pdfauthor={{{author}}},
{prefix}    pdflang={{en-US}},
{prefix}    pdfsubject={{{subject}}},
{prefix}    pdfkeywords={{{keywords}}},
{prefix}    colorlinks=true,
{prefix}    linkcolor=blue,
{prefix}    urlcolor=blue,
{prefix}    citecolor=blue,
{prefix}    unicode]{{hyperref}}
{prefix}\\IfFileExists{{pdfcomment.sty}}{{\\usepackage{{pdfcomment}}}}{{\\newcommand{{\\pdftooltip}}[2]{{#1}}}}"""


def already_patched(text: str) -> bool:
    """True only if preamble AND the pdftooltip definition are both present."""
    return ('fontenc' in text and 'lmodern' in text
            and 'pdftitle' in text and 'pdfcomment' in text)


def patch_preamble(text: str, prefix: str, title: str) -> str:
    """
    Replace bare \\usepackage{hyperref} (possibly preceded by graphicx) with
    the full accessibility preamble.  Idempotent.
    """
    # Build replacement blocks
    preamble = PREAMBLE_TEMPLATE.format(prefix=prefix)
    hyperref = HYPERREF_TEMPLATE.format(
        prefix=prefix, title=title, author=AUTHOR,
        subject=SUBJECT, keywords=KEYWORDS)

    # Match: graphicx line, optional listings line, hyperref line
    # The prefix may be <shn>, <chn>, etc., or empty.
    pat = re.compile(
        r'(' + re.escape(prefix) + r'\\usepackage\{graphicx\}\n)'
        r'(' + re.escape(prefix) + r'\\usepackage\{hyperref\}\n)'
        r'(' + re.escape(prefix) + r'\\usepackage\{listings\}\n)?',
        re.MULTILINE
    )

    def replacer(m):
        listings = m.group(3) or ''
        return (preamble + '\n'
                + m.group(1)          # graphicx (keep)
                + hyperref + '\n'
                + listings)

    new_text, count = pat.subn(replacer, text, count=1)
    if count == 0:
        # Fallback 1: replace bare \usepackage{hyperref}
        bare_pat = re.compile(
            r'(' + re.escape(prefix) + r'\\usepackage\{hyperref\})',
            re.MULTILINE)
        new_text = bare_pat.sub(lambda m: hyperref, text, count=1)

    if new_text == text:
        # Fallback 2: no hyperref at all — insert after \documentclass line
        docclass_pat = re.compile(r'(\\documentclass(?:\[[^\]]*\])?\{[^}]+\})')
        new_text = docclass_pat.sub(
            lambda m: m.group(0) + '\n' + preamble + '\n' + hyperref,
            text, count=1)

    return new_text


# ── Image alt-text wrapping ──────────────────────────────────────────────────

# Matches \includegraphics[...]{filename} or \includegraphics{filename}
# capturing optional options and the filename.
INCL_RE = re.compile(
    r'\\includegraphics(\[[^\]]*\])?\{([^}]+)\}')


def guess_alt(filename: str, context: str = '') -> str:
    """Produce a rough alt-text guess from the image filename and context."""
    name = Path(filename).stem.lower()

    # Named figures we know about
    known = {
        'redditfollowadviceuw':
            'Screenshot of a Reddit post advising UW students to follow course advice',
        'traystack':
            'Photo of a spring-loaded cafeteria tray stack, '
            'analogy for the hardware stack data structure',
        'pathfinder':
            'Photo of the NASA Mars Pathfinder rover, illustrating '
            'the priority inversion bug in the 1997 Mars mission',
        'rs232_serialbits':
            'Timing diagram of an RS-232 serial bit frame showing '
            'start bit, data bits, parity, and stop bits',
        'rs232_db25pinout':
            'DB-25 connector pinout diagram for RS-232 serial interface',
        'includes_multi_protos':
            'Diagram showing a single .h header providing function '
            'prototypes to multiple .c source files',
        'c-building':
            'Flowchart of the C build process: preprocessor, compiler, linker',
    }
    if name in known:
        return known[name]

    # Numbered figures: guess from directory name
    parts = filename.replace('\\', '/').split('/')
    if len(parts) >= 2:
        folder = parts[-2]
        folder_guesses = {
            'hwio_figs':   'Hardware I/O diagram',
            'usb_figs':    'USB architecture diagram',
            'sched_figs':  'Scheduler diagram',
            'intro_figs':  'Introduction diagram',
            'cprog_figs':  'C programming diagram',
            'misc_figs':   'Diagram',
            'Serial_figs': 'Serial communication diagram',
        }
        base = folder_guesses.get(folder, 'Diagram')
        return f'{base} ({Path(filename).name})'

    return f'Figure ({Path(filename).name})'


def wrap_images(text: str) -> str:
    """
    Wrap every \\includegraphics that is not already inside \\pdftooltip.
    """
    # Find positions already inside \pdftooltip{...} so we skip them
    tooltip_ranges = set()
    for m in re.finditer(r'\\pdftooltip\{', text):
        tooltip_ranges.add(m.start())

    def replacer(m):
        # Check if this match is already inside a \pdftooltip first argument
        start = m.start()
        # Walk backward to see if we're inside \pdftooltip{
        preceding = text[:start]
        if '\\pdftooltip{' in preceding:
            last_tt = preceding.rfind('\\pdftooltip{')
            # crude check: if braces aren't balanced after last_tt, we're inside
            snippet = text[last_tt + len('\\pdftooltip{'):]
            depth = 1
            for ch in snippet:
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        break
                if snippet.index(ch if depth > 0 else ch) >= (start - last_tt - len('\\pdftooltip{')):
                    pass
            # Simpler heuristic: if the match appears to be inside \pdftooltip already, skip
            tt_inner_end = last_tt + len('\\pdftooltip{')
            # Find the closing } of the first arg
            depth = 1
            pos = tt_inner_end
            while pos < len(text) and depth > 0:
                if text[pos] == '{': depth += 1
                elif text[pos] == '}': depth -= 1
                pos += 1
            if last_tt < start < pos:
                return m.group(0)   # already wrapped

        opts = m.group(1) or ''
        fname = m.group(2)
        alt = f'{ALT_MARKER} {guess_alt(fname)}'
        return f'\\pdftooltip{{\\includegraphics{opts}{{{fname}}}}}{{{alt}}}'

    return INCL_RE.sub(replacer, text)


def apply_pdf_accessibility(shn_path: Path, make_backup: bool = True):
    print(f'\n[PDF] {shn_path.resolve()}')
    text = shn_path.read_text()

    if already_patched(text):
        print('  already patched — skipping preamble (will still check images)')
        new_text = text
    else:
        # Determine the stream prefix used in this file's preamble
        m = re.search(r'(<[a-z]+>)\\usepackage\{hyperref\}', text)
        prefix = m.group(1) if m else ''
        title = pdf_title(shn_path)
        print(f'  title: {title}')
        print(f'  stream prefix: "{prefix}"')
        new_text = patch_preamble(text, prefix, title)

    new_text = wrap_images(new_text)

    if new_text != text:
        if make_backup:
            backup(shn_path)
        shn_path.write_text(new_text)
        print(f'  written → {shn_path.resolve()}')
    else:
        print('  no changes needed.')


# ── Part 2: HTML + MathML generation ─────────────────────────────────────────

def extract_alt_map(tex_text: str) -> dict:
    """
    Extract {image_filename: alt_text} from \\pdftooltip calls so we can
    inject alt= attributes into the Pandoc HTML output.
    """
    alt_map = {}
    # Match \pdftooltip{\includegraphics[...]{filename}}{alt text}
    pat = re.compile(
        r'\\pdftooltip\{\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}\}'
        r'\{([^}]+)\}')
    for m in pat.finditer(tex_text):
        fname = Path(m.group(1)).name   # just the basename
        alt   = m.group(2).replace(r'*\#*\#', '*#*#').strip()
        alt_map[fname] = alt
    return alt_map


def preprocess_for_pandoc(tex_text: str) -> str:
    """
    Strip \\pdftooltip wrappers (Pandoc doesn't know them) and replace
    with plain \\includegraphics so Pandoc can convert images normally.
    The alt text is injected into the HTML in a post-processing step.
    Also strip .shn stream-tag lines that leak into generated .tex.
    """
    # Unwrap \pdftooltip{\includegraphics...}{alt} → \includegraphics...
    tex_text = re.sub(
        r'\\pdftooltip\{(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})\}\{[^}]+\}',
        r'\1', tex_text)
    # Strip pdfcomment / IfFileExists lines Pandoc can't handle gracefully
    tex_text = re.sub(r'.*IfFileExists.*pdfcomment.*\n', '', tex_text)
    tex_text = re.sub(r'.*usepackage\{pdfcomment\}.*\n', '', tex_text)
    return tex_text


def postprocess_html(html: str, alt_map: dict) -> str:
    """Add alt= attributes to <img> tags using our alt_map."""
    def add_alt(m):
        tag = m.group(0)
        # Find the src filename
        src_m = re.search(r'src="([^"]+)"', tag)
        if not src_m:
            return tag
        fname = Path(src_m.group(1)).name
        if 'alt=' in tag:
            return tag   # already has alt
        alt = alt_map.get(fname, '')
        if alt:
            return tag.replace('<img ', f'<img alt="{alt}" ', 1)
        return tag

    return re.sub(r'<img [^>]+>', add_alt, html)


def generate_html(shn_path: Path, stream: str = HTML_VERSION):
    print(f'\n[HTML] {shn_path.resolve()}')

    if not shutil.which('coursetex'):
        print('  ERROR: coursetex not found on PATH', file=sys.stderr)
        return
    if not shutil.which('pandoc'):
        print('  ERROR: pandoc not found on PATH', file=sys.stderr)
        return

    stem = shn_path.stem
    tex_path  = shn_path.parent / f'{stem}.{stream}.tex'
    html_path = shn_path.parent / f'{stem}.html'

    # Step 1: generate .tex from .shn  (run from the file's own directory so
    # coursetex can find any \input'd files and writes output there too)
    run(['coursetex', '--out', stream, shn_path.name],
        cwd=str(shn_path.resolve().parent))
    if not tex_path.exists():
        print(f'  ERROR: {tex_path} not generated', file=sys.stderr)
        return

    # Step 2: read .tex, extract alt map, pre-process for Pandoc
    tex_text = tex_path.read_text()
    alt_map  = extract_alt_map(tex_text)
    clean_tex = preprocess_for_pandoc(tex_text)

    preprocessed = tex_path.with_suffix('.pandoc.tex')
    preprocessed.write_text(clean_tex)

    # Step 3: run Pandoc → HTML with MathML
    result = run([
        'pandoc',
        '--from=latex',
        '--to=html5',
        '--mathml',                 # MathML for equations (no JS needed)
        '--standalone',             # full HTML document with <head>
        '--embed-resources',        # inline CSS/fonts so file is self-contained
        f'--metadata=title:{pdf_title(shn_path)}',
        f'--metadata=lang:en-US',
        str(preprocessed),
        '-o', str(html_path),
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f'  pandoc stderr:\n{result.stderr}', file=sys.stderr)
        preprocessed.unlink(missing_ok=True)
        return

    # Step 4: post-process HTML to add alt attributes
    html = html_path.read_text()
    html = postprocess_html(html, alt_map)
    html_path.write_text(html)

    preprocessed.unlink(missing_ok=True)   # clean up temp file
    print(f'  → {html_path.resolve()}  ({len(alt_map)} images with alt text)')


# ── CLI ──────────────────────────────────────────────────────────────────────

def all_shn_files(directory: Path):
    return sorted(p for p in directory.glob('*.shn')
                  if not p.stem.startswith('old') and 'backup' not in p.name)


def main():
    parser = argparse.ArgumentParser(
        description='ECE 474 course materials accessibility tool')
    parser.add_argument('files', nargs='*',
        help='.shn files to process (omit with --batch)')
    parser.add_argument('--shn', action='store_true',
        help='Patch the .shn source file with accessibility changes')
    parser.add_argument('--html', action='store_true',
        help='Generate HTML+MathML via Pandoc')
    parser.add_argument('--all', action='store_true',
        help='Apply both --shn and --html')
    parser.add_argument('--batch', action='store_true',
        help='Process all .shn files in current directory')
    parser.add_argument('--no-backup', action='store_true',
        help='Skip .bak backup files when patching')
    parser.add_argument('--version', default=None,
        help='coursetex version for HTML (s=slides, h=handout, n=notes, c=combined); prompted if omitted')
    args = parser.parse_args()

    do_shn  = args.shn  or args.all
    do_html = args.html or args.all

    if not do_shn and not do_html:
        parser.print_help()
        print('\nSpecify at least one of --shn, --html, or --all.')
        sys.exit(1)

    if do_html and args.version is None:
        v = input('coursetex version for HTML (s=slides, h=handout, n=notes, c=combined) [n]: ').strip()
        args.version = v if v else HTML_VERSION

    cwd = Path('.')
    if args.batch:
        files = all_shn_files(cwd)
        if not files:
            print('No .shn files found.')
            sys.exit(0)
    else:
        if not args.files:
            parser.error('Provide file(s) or use --batch')
        files = [Path(f) for f in args.files]

    for f in files:
        if not f.exists():
            print(f'WARNING: {f} not found — skipping', file=sys.stderr)
            continue
        if do_shn:
            apply_pdf_accessibility(f, make_backup=not args.no_backup)
        if do_html:
            generate_html(f, stream=args.version)

    print('\nDone.')


if __name__ == '__main__':
    main()
