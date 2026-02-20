# AccessibilityTools

Tools for making LaTeX course materials accessible (PDF metadata, alt-text, HTML+MathML).

## Project structure

- `make_accessible.py` — for `.shn` files (coursetex preprocessor format)
- `make_accessible_tex.py` — for plain `.tex` files
- `metadata.cfg` — per-directory config for PDF metadata (author, subject, keywords)
- `docgui.cfg` — coursetex GUI config (unrelated to accessibility)

## Key conventions

- Both scripts share the same metadata config mechanism: `metadata.cfg` in the working directory
- Config format: plain text, one `keyword value` per line (author, subject, keywords)
- If `metadata.cfg` is missing, the scripts prompt the user and create one
- Alt-text markers use `***!!***Guess by make_accessible*.py:` prefix so humans can find/fix them
- Scripts are idempotent — safe to re-run on already-patched files
- `.bak` backups are created by default before modifying source files

## Running

```bash
python make_accessible.py --shn file.shn       # patch .shn source
python make_accessible.py --html file.shn       # generate HTML
python make_accessible_tex.py --pdf file.tex    # patch .tex source
python make_accessible_tex.py --html file.tex   # generate HTML
```
