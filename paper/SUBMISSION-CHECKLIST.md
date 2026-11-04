# Before uploading to arXiv: facts only the author can confirm

This list accompanies the 4 November 2026 manuscript (`paper/arxiv/main.pdf`,
source bundle `paper/arxiv/main.zip`). Nothing below has been filled in on the
author's behalf; each item needs the author's own confirmation or edit.

## Title page

1. **Title.** It was changed during the audit revision to
   *Measuring What a Failure-Routing Detector Adds: Representation, File
   Discovery and Denominators in AI/ML Python*, to match the
   measurement-protocol framing. The previous title was *Failure-Routing in
   AI/ML Python Except-Handlers: Corpus Measurements and Validation Limits*.
   Confirm the title, or restore the previous one (`\title` and `pdftitle`).
2. **Author name** "Yufeiyang Chen": confirm the spelling and form used on arXiv.
3. **Affiliation** "School of Cyber Science and Technology, Sun Yat-sen
   University, Shenzhen, China": confirm that this is current and that you may
   list it for this work.
4. **Correspondence email** `fei76161@gmail.com`: confirm that it should be
   public.

## Statements

5. **Author contribution and AI assistance** (title-page footnote). It says that
   the author originated the idea, directed the study and takes responsibility
   for the final work; that AI language tools assisted software development,
   testing, data analysis, and the drafting and revision of the text; and that
   all corpus labels were produced by LLM agents. Confirm that this describes
   your role and the AI use accurately.
6. **Conflict of interest.** The section lists the documented relationships:
   the author wrote the detector and the supplementary Semgrep rules, selected
   the main corpus partly from packages they had contributed to, and submitted
   the curated pull requests. A sentence "The author declares no other competing
   interests" was **removed**, because only the author can assert it. If it is
   true, add it back; otherwise add whatever else must be disclosed.
7. **Funding.** The manuscript makes no funding statement. Add one if the work
   was funded, or a "no specific funding" statement if that is true and you want
   one.
8. **Licence.** The manuscript states CC BY 4.0. Confirm that this is the licence
   you will choose on the arXiv form.

## Submission metadata

9. **Category.** Primary cs.SE fits the content: an evaluation methodology for
   static analysis, warning coverage and measurement validity. No cross-list is
   needed; the work makes no machine-learning methods contribution. Acceptance
   is decided by arXiv moderation and is not guaranteed.
10. **Abstract field.** Paste the abstract body from `main.tex` (1,692
    characters, within the 1,920-character limit; check with
    `tools/check_abstract_len.py`) with the TeX escapes `\%` and `\_` removed.
11. **Comments field** (suggestion): "21 pages, 4 figures. Code, data and
    reproduction scripts: https://github.com/feiiiiii5/failroute".

## Evidence the author should know is not independently re-runnable

* Eight claim checks are `HIST`. Six need commits `6eb7973` and `50275e8`,
  which are absent from the public history; two need the unreleased
  `contractlens` repository. Five of them are re-derived on public commits,
  which shows reproducibility, not identity with the lost commits.
* The two five-tool Semgrep claims fail by design: Semgrep 1.175.0 partially
  parses one corpus file, so five-tool figures are reported as observed values
  with an upper bound.
* All labels are LLM-produced with unrecorded model identity; no defect
  precision or recall is claimed.
