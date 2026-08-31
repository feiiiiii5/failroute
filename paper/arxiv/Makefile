# Build the arXiv submission for the failroute study.
#
#   make            full build: pdflatex -> bibtex -> pdflatex -> pdflatex
#   make quick      single pdflatex pass (fast feedback, stale citations)
#   make submission build then bundle main.tar.gz for arXiv upload
#   make clean      remove build products
#
# Requires a LaTeX toolchain (pdflatex + bibtex). If none is installed, see
# paper/ARTIFACT.md for how this checkout was built instead.

MAIN    := main
LATEX   := pdflatex
BIBTEX  := bibtex
LATEXFLAGS := -interaction=nonstopmode -halt-on-error -file-line-error

.PHONY: all quick bibtexonly submission clean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex refs.bib $(wildcard figures/*.pdf)
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex
	-$(BIBTEX) $(MAIN)
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex

quick: $(MAIN).tex
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex

# Bundle only what arXiv needs; refuses to run if the build has errors.
submission: all
	@test -s $(MAIN).pdf || (echo "no PDF produced"; exit 1)
	@if /usr/bin/grep -q '^!' $(MAIN).log; then \
	  echo "LaTeX errors present in $(MAIN).log -- refusing to bundle"; exit 1; \
	fi
	tar -czf $(MAIN).tar.gz $(MAIN).tex refs.bib figures/*.pdf $(MAIN).bbl
	@echo "wrote $(MAIN).tar.gz"

clean:
	rm -f $(MAIN).aux $(MAIN).log $(MAIN).out $(MAIN).bbl $(MAIN).blg \
	      $(MAIN).tar.gz
