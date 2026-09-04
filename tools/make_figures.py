#!/usr/bin/env python3
"""Build the three paper figures from artifacts that already exist on disk.

Inputs (all produced by other scripts, never re-derived here):
  paper/intervals.json                       -- P3, Wilson 95% score intervals
  bench/corpus-coverage-union-5tool.json     -- P5, per-rule + per-tool coverage
                                               for the four linters and semgrep
  paper/merged-pr-recall.csv                 -- recall ground truth (70 merged PRs)

Outputs: paper/figures/fig{1,2,3}_*.{pdf,png}

Design constraints: greyscale + hatch patterns only, so all three figures stay
readable when printed in black and white.
"""
from __future__ import annotations

import csv
import json
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'paper', 'figures')
PPI = 200

GREY = {
    'ruff': '1.00', 'bandit': '0.82', 'pylint': '0.60', 'flake8+bugbear': '0.40',
    'semgrep': '0.88', 'union4': '0.22', 'union5': '0.50',
}
HATCH = {
    'ruff': '', 'bandit': '//', 'pylint': '\\\\', 'flake8+bugbear': '..',
    'semgrep': '////', 'union4': '', 'union5': 'xx',
}
EDGE = '0.0'


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
    """Per-package defect rate with Wilson 95% score intervals."""

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
                   label='one-sided 95% upper bound (zero-defect cells)')

    for p, yi, r, h in zip(pts, y, rows, hi):
        xpos = max(h, r['one_sided95_upper_pct'] or 0.0) + 2.0
        ax.annotate('%d/%d' % (r['numerator'], r['denominator']),
                    (xpos, yi), textcoords='data', ha='left', va='center',
                    fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(-1.5, max(hi) * 1.18 + 9)
    ax.set_xlabel('defect rate among sampled findings (%)')
    ax.set_title('Annotated defect rate per package, 80 sampled findings\n'
                 '(labels from pass 1; a second annotation pass agreed on every item)',
                 fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.14),
              ncol=2, frameon=False)
    fig.tight_layout()
    save(fig, 'fig1_defect_rate_by_package')


# ---------------------------------------------------------------- figure 2 ---
def figure2(u5):
    """Coverage of failroute's 649 findings by existing linters, per rule."""
    total = u5['failroute_total']
    order = ['silent-fallback', 'no-action', 'silent-suppress', 'masked-exception']
    tools = [('ruff', 'ruff'), ('bandit', 'bandit'), ('pylint', 'pylint'),
             ('flake8+bugbear', 'flake8+bugbear'),
             ('semgrep', 'semgrep (our rules)')]

    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    slot = 0
    ticks, labels = [], []
    for rule in order:
        n = u5['by_rule'][rule]['total']
        bars = []
        for key, _label in tools:
            covered = u5['per_tool_by_rule'].get(key, {}).get(rule, 0)
            bars.append((key, covered))
        bars.append(('union4', u5['by_rule'][rule]['covered_4']))
        bars.append(('union5', u5['by_rule'][rule]['covered_5']))
        width = 0.78 / len(bars)
        for i, (key, k) in enumerate(bars):
            x = slot + i * width
            h = 100.0 * k / n
            ax.bar(x, h, width=width, color=GREY[key], edgecolor=EDGE,
                   linewidth=0.7, hatch=HATCH[key], zorder=3)
            ax.annotate('%d/%d' % (k, n), (x, h), textcoords='offset points',
                        xytext=(0, 2.5), rotation=90, ha='center', va='bottom',
                        fontsize=6.2)
        ticks.append(slot + 0.78 / 2)
        labels.append('%s\n%d of %d findings' % (rule, n, total))
        slot += 1.0

    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_xlim(-0.1, slot - 0.1)
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylabel('share of this rule\'s failroute findings covered (%)')
    ax.set_title('Coverage of failroute findings by existing syntactic linters, by rule\n'
                 'union4 = ruff+bandit+pylint+flake8-bugbear (%d/%d)   '
                 'union5 = + semgrep (%d/%d)' % (
                     u5['union_covered_4tool_recheck'], total,
                     u5['union_covered_5tool'], total),
                 fontsize=10)
    handles = []
    for key, label in tools + [('union4', 'union of the four linters'),
                               ('union5', 'union incl. semgrep')]:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor=GREY[key],
                                     edgecolor=EDGE, linewidth=0.7,
                                     hatch=HATCH[key], label=label))
    ax.legend(handles=handles, fontsize=7.5, ncol=4, frameon=False,
              loc='upper center', bbox_to_anchor=(0.5, -0.16))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
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
        body.append([repo, '#' + r['pr_number'], r['pr_title'][:38],
                     detected.upper(), rule, note])

    fig, ax = plt.subplots(figsize=(11.4, 0.36 * (len(body) + 3.4)))
    ax.axis('off')
    tbl = ax.table(cellText=body,
                   colLabels=['repo', 'PR', 'fix title (truncated)',
                              'detected', 'rule matched', 'note'],
                   cellLoc='left', bbox=[0.0, 0.10, 1.0, 0.88],
                   colWidths=[0.095, 0.045, 0.235, 0.065, 0.105, 0.455])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(6.8)
    for (r, c), tex in tbl.get_celld().items():
        tex.set_edgecolor('0.75')
        if r == 0:
            tex.set_facecolor('0.82')
            tex.set_text_props(weight='bold')
        elif body[r - 1][3] == 'YES':
            tex.set_facecolor('0.93')
            tex.set_text_props(weight='bold' if c == 3 else 'normal')

    fig.suptitle('Detection recall on merged fixes that belong to the failure-routing family',
                 fontsize=11, y=1.0)
    fig.text(0.012, 0.012,
             'Recall %d/%d = %.1f%% (Wilson 95%%: %.1f-%.1f%%) against all %d family fixes; '
             '%d/%d = %.1f%% (Wilson 95%%: %.1f-%.1f%%) against the %d in-scope subset '
             '(out-of-scope rows carry detected=n/a). Denominators recounted from '
             'paper/merged-pr-recall.csv by tools/compute_intervals.py.' % (
                 all_c['numerator'], all_c['denominator'], 100 * all_c['point'],
                 all_c['wilson95_low_pct'], all_c['wilson95_high_pct'],
                 all_c['denominator'],
                 scope_c['numerator'], scope_c['denominator'], 100 * scope_c['point'],
                 scope_c['wilson95_low_pct'], scope_c['wilson95_high_pct'],
                 scope_c['denominator']),
             fontsize=6.8, va='bottom', ha='left')
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
