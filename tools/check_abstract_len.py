#!/usr/bin/env python3
"""Measure the paper abstract under the arXiv metadata form's character convention.

The arXiv submission form's abstract field accepts at most 1920 characters. The
convention measured here is the form's, not the PDF's: the text of the abstract
environment, stripped of leading and trailing whitespace, with each newline
counting as one character. TeX markup is NOT stripped -- the form receives the
characters you paste, backslashes and braces included.

Why this is a command and not a source comment: the comment above the abstract in
main.tex claimed 1894 characters (S batch) while the text it described measured
1917 after the T batch lengthened it. A hand-maintained length is a claim nobody
re-runs; this is re-runnable and is wired into the claims ledger.

Two figures are printed because the source may be wrapped:
  form   -- raw stripped length, newlines kept at one character each (the gate)
  flat   -- the same text with every whitespace run collapsed to one space
The two differ only by paragraph separators in flush-left-wrapped source. If the
source is indented, `form` counts the indentation and `flat` does not; keep the
abstract flush-left so the two cannot diverge by an amount that hides an overrun.

Usage:
    cd 新项目-failroute && .venv/bin/python tools/check_abstract_len.py
    .venv/bin/python tools/check_abstract_len.py --limit 1900
    .venv/bin/python tools/check_abstract_len.py --tex /path/to/main.tex
    printf '%s' 'candidate text' | .venv/bin/python tools/check_abstract_len.py --stdin

Exit code is the number of measured conventions that exceed the limit, so a
wrapper can fail on it directly.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TEX = os.path.join(ROOT, "paper", "arxiv", "main.tex")
LIMIT = 1920
# Deliberately spelled by concatenation: a literal pair of markers in this file
# would be found first by anything scanning the tree for the abstract span.
BEGIN = "\\begin" + "{abstract}"
END = "\\end" + "{abstract}"


def extract(tex: str) -> str:
    hits = [m for m in re.finditer(re.escape(BEGIN) + "(.*?)" + re.escape(END), tex, re.S)]
    if not hits:
        sys.exit("error: no abstract environment found -- cannot measure what is not there")
    if len(hits) > 1:
        sys.exit("error: %d abstract environments found; exactly one is measurable" % len(hits))
    return hits[0].group(1)


def measure(body: str) -> tuple[int, int]:
    form = len(body.strip())
    flat = len(re.sub(r"\s+", " ", body).strip())
    return form, flat


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", default=DEFAULT_TEX, help="LaTeX source to read (default: the paper)")
    ap.add_argument("--limit", type=int, default=LIMIT, help="character budget (default: 1920)")
    ap.add_argument("--stdin", action="store_true",
                    help="measure standard input as raw abstract text instead of reading --tex")
    args = ap.parse_args()

    if args.stdin:
        body = sys.stdin.read()
        where = "<stdin>"
    else:
        if not os.path.isfile(args.tex):
            sys.exit("error: LaTeX source missing: %s" % args.tex)
        body = extract(open(args.tex, encoding="utf-8").read())
        where = args.tex

    form, flat = measure(body)
    print("source              : %s" % where)
    print("form convention     : %d / %d   (%s)" % (form, args.limit,
                                                   "fits" if form <= args.limit else "OVER"))
    print("whitespace flattened: %d / %d   (%s)" % (flat, args.limit,
                                                   "fits" if flat <= args.limit else "OVER"))
    if form <= args.limit and flat <= args.limit:
        print("headroom            : %d characters" % (args.limit - max(form, flat)))
    return (1 if form > args.limit else 0) + (1 if flat > args.limit else 0)


if __name__ == "__main__":
    sys.exit(main())
