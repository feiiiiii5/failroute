#!/usr/bin/env python3
"""Build the three paper figures from artifacts that already exist on disk.

Inputs (all produced by other scripts, never re-derived here):
  paper/intervals.json                       -- P3, Wilson 95% score intervals
  bench/corpus-coverage-union-5tool.json     -- P5, per-rule + per-tool coverage
                                               for the four linters and semgrep
  paper/merged-pr-recall.csv                 -- recall ground truth (70 merged PRs)

Outputs: paper/figures/fig{1,2,3}_*.{pdf,png}

Design constraints: greyscale, direct labels, and no color-only distinctions,
so the figures remain readable when printed in black and white.
"""
from __future__ import annotations

import csv
import json
import os
import textwrap

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'paper', 'figures')
PPI = 200

def load(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return json.load(f)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + '.pdf'), bbox_inches='tight')
    fig.savefig(os.path.join(OUT, name + '.png'), dpi=PPI, bbox_inches='tight')
    plt.close(fig)
    print('wrote paper/figures/%s.{pdf,png}' % name)


# ---------------------------------------------------------------- figure 1 ---
def figure1(cells):
    """Per-package LLM DEFECT-label share with Wilson 95% score intervals."""

    def pick(group, label):
        for r in cells:
            if r['group'] == group and r['label'] == label:
                return r
        return None

    rows = [pick('overall[pass1]', 'defect rate')]
    rows.append(pick('pooled[pass1]', 'seven mature packages (all but deepteam)'))
    pkgs = [r for r in cells if r['group'] == 'by-package[pass1]']
    pkgs.sort(key=lambda r: -r['denominator'])
    rows.extend(pkgs)
    rows = [r for r in rows if r is not None]

    names = []
    for r in rows:
        if r['group'] == 'overall[pass1]':
            names.append('all 8 packages (n=%d)' % r['denominator'])
        elif r['group'] == 'pooled[pass1]':
            names.append('pooled, 7 mature pkgs (n=%d)' % r['denominator'])
        else:
            n = r['label'].replace(' defect rate', '')
            names.append('%s (n=%d)' % (n, r['denominator']))

    y = list(range(len(rows)))[::-1]
    pts = [100.0 * r['point'] for r in rows]
    lo = [100.0 * r['wilson95_low'] for r in rows]
    hi = [100.0 * r['wilson95_high'] for r in rows]
    low_err = [p - l for p, l in zip(pts, lo)]
    high_err = [h - p for p, h in zip(pts, hi)]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.errorbar(pts, y, xerr=[low_err, high_err], fmt='o', ms=7,
                color='0.0', ecolor='0.0', elinewidth=1.4, capsize=4,
                label='point estimate, Wilson 95% interval', zorder=3)
    ax.axvline(0.0, color='0.4', lw=0.8, ls=':', zorder=1)

    zs = [(p, yi, r) for p, yi, r in zip(pts, y, rows) if r['numerator'] == 0]
    if zs:
        ax.scatter([r['one_sided95_upper_pct'] for _, _, r in zs],
                   [yi for _, yi, _ in zs], marker='v', s=52, facecolor='none',
                   edgecolor='0.0', linewidth=1.2, zorder=4,
                   label='one-sided 95% upper bound (zero-label cells)')

    for p, yi, r, h in zip(pts, y, rows, hi):
        xpos = max(h, r['one_sided95_upper_pct'] or 0.0) + 2.0
        ax.annotate('%d/%d' % (r['numerator'], r['denominator']),
                    (xpos, yi), textcoords='data', ha='left', va='center',
                    fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(-1.5, max(hi) * 1.18 + 9)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel('LLM DEFECT-label share among sampled findings (%)')
    ax.set_title('Frozen LLM labels by package, 80 sampled findings\n'
                 '(five DEFECT labels have an unestablished failure-conversion mechanism)',
                 fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.14),
              ncol=2, frameon=False)
    fig.tight_layout()
    save(fig, 'fig1_defect_rate_by_package')


# ---------------------------------------------------------------- figure 2 ---
def figure2(u5):
    """Coverage of the pinned findings by baseline and failure-routing family."""
    total = u5['failroute_total']
    order = ['silent-fallback', 'no-action', 'silent-suppress', 'masked-exception']
    columns = [
        ('ruff', 'ruff'),
        ('bandit', 'bandit'),
        ('pylint', 'pylint'),
        ('flake8+bugbear', 'flake8 +\nbugbear'),
        ('semgrep', 'project\nSemgrep'),
        ('union4', 'four-linter\nunion'),
        ('union5', 'five-tool\nunion'),
    ]

    if sum(u5['by_rule'][rule]['total'] for rule in order) != total:
        raise ValueError('per-rule denominators do not sum to failroute_total')
    if sum(u5['by_rule'][rule]['covered_4'] for rule in order) != u5['union_covered_4tool_recheck']:
        raise ValueError('four-linter per-rule counts do not match the aggregate')
    if sum(u5['by_rule'][rule]['covered_5'] for rule in order) != u5['union_covered_5tool']:
        raise ValueError('five-tool per-rule counts do not match the aggregate')

    shares, cell_labels = [], []
    for rule in order:
        n = u5['by_rule'][rule]['total']
        counts = []
        for key, _label in columns:
            if key == 'union4':
                covered = u5['by_rule'][rule]['covered_4']
            elif key == 'union5':
                covered = u5['by_rule'][rule]['covered_5']
            else:
                covered = u5['per_tool_by_rule'].get(key, {}).get(rule, 0)
            if not 0 <= covered <= n:
                raise ValueError('%s coverage for %s is outside its denominator' % (key, rule))
            counts.append(covered)
        shares.append([100.0 * count / n for count in counts])
        cell_labels.append(['%d/%d' % (count, n) for count in counts])

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    image = ax.imshow(shares, cmap='Greys', vmin=0, vmax=100,
                      aspect='auto', interpolation='nearest')

    for row, rule in enumerate(order):
        for col, share in enumerate(shares[row]):
            ax.text(col, row, cell_labels[row][col], ha='center', va='center',
                    fontsize=8, color='white' if share >= 65 else 'black')

    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels([label for _key, label in columns], fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([
        '%s (n=%d)' % (rule, u5['by_rule'][rule]['total']) for rule in order
    ], fontsize=8.5)
    ax.set_xticks([-0.5 + i for i in range(len(columns) + 1)], minor=True)
    ax.set_yticks([-0.5 + i for i in range(len(order) + 1)], minor=True)
    ax.grid(which='minor', color='white', linestyle='-', linewidth=1.5)
    ax.tick_params(which='both', length=0)
    ax.tick_params(axis='x', pad=7)
    ax.set_xlabel('Detector or union', fontsize=8.5, labelpad=5)
    ax.set_ylabel('Failure-routing family', fontsize=8.5, labelpad=7)

    four = u5['union_covered_4tool_recheck']
    five = u5['union_covered_5tool']
    fig.suptitle('Baseline coverage by failure-routing family', fontsize=10.5, y=0.98)
    fig.text(0.5, 0.91,
             'Four-linter union: %d/%d (%.1f%%); with project Semgrep rules: %d/%d (%.1f%%)' % (
                 four, total, 100.0 * four / total, five, total, 100.0 * five / total),
             ha='center', fontsize=8.5)
    fig.subplots_adjust(left=0.28, right=0.91, top=0.84, bottom=0.20)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02,
                            ticks=[0, 25, 50, 75, 100])
    colorbar.set_label('covered (%)', fontsize=8)
    colorbar.ax.tick_params(labelsize=8, length=2)
    save(fig, 'fig2_cross_tool_coverage')


# ---------------------------------------------------------------- figure 3 ---
def figure3(cells):
    """Recall of the six-rule family against merged security-relevant fixes."""
    path = os.path.join(ROOT, 'paper', 'merged-pr-recall.csv')
    with open(path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    family = [r for r in rows
              if r.get('belongs_to_family', '').strip().lower() == 'yes']

    def cell(group, label):
        for r in cells:
            if r['group'] == group and r['label'] == label:
                return r
        return None

    all_c = cell('recall', 'recall vs all family fixes')
    scope_c = cell('recall', 'recall vs in-scope family fixes')

    body = []
    for r in family:
        repo = r['repo'].split('/')[-1]
        detected = r.get('detected', '').strip().lower() or 'n/a'
        rule = r.get('rule_matched', '').strip() or '—'
        note = r.get('note', '').strip()
        if len(note) > 74:
            note = note[:71] + '...'
        body.append([textwrap.fill(repo, 15), '#' + r['pr_number'],
                     detected.upper(), rule.replace('-', '-\n'),
                     textwrap.fill(note, 42)])

    fig, ax = plt.subplots(figsize=(7.2, 0.43 * (len(body) + 2)))
    ax.axis('off')
    tbl = ax.table(cellText=body,
                   colLabels=['Repository', 'PR', 'Detected', 'Rule', 'Note (abridged)'],
                   cellLoc='left', bbox=[0.0, 0.08, 1.0, 0.89],
                   colWidths=[0.18, 0.085, 0.105, 0.135, 0.495])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    for (r, c), tex in tbl.get_celld().items():
        tex.set_edgecolor('0.75')
        if r == 0:
            tex.set_facecolor('0.82')
            tex.set_text_props(weight='bold')
        elif body[r - 1][2] == 'YES':
            tex.set_facecolor('0.93')
            tex.set_text_props(weight='bold' if c == 2 else 'normal')

    fig.suptitle('Detection on merged fixes in the failure-routing reference set',
                 fontsize=10, y=0.995)
    fig.text(0.02, 0.012,
             'All family fixes: %d/%d = %.1f%% (Wilson 95%%: %.1f-%.1f%%)\n'
             'In-scope subset: %d/%d = %.1f%% (Wilson 95%%: %.1f-%.1f%%)' % (
                 all_c['numerator'], all_c['denominator'], 100 * all_c['point'],
                 all_c['wilson95_low_pct'], all_c['wilson95_high_pct'],
                 scope_c['numerator'], scope_c['denominator'], 100 * scope_c['point'],
                 scope_c['wilson95_low_pct'], scope_c['wilson95_high_pct'],
             ), fontsize=9, va='bottom', ha='left')
    fig.tight_layout()
    save(fig, 'fig3_recall_by_family')


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    iv = load('paper/intervals.json')
    figure1(iv['cells'])
    figure2(load('bench/corpus-coverage-union-5tool.json'))
    figure3(iv['cells'])


if __name__ == '__main__':
    main()
