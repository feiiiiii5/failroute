#!/usr/bin/env python3
"""95% confidence intervals (Wilson score) for every proportion reported in the paper.

Wilson (1927) score interval is used rather than the normal approximation because several
cells have zero numerators, where the Wald interval collapses to zero width.
For zero-numerator cells the exact one-sided 95% upper bound (Clopper-Pearson,
closed form 1 - alpha**(1/n)) is also reported.

Usage: cd 新项目-failroute && .venv/bin/python tools/compute_intervals.py
Writes paper/intervals.json and prints a markdown table.
"""
import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
# O batch: --out lets claims run this tool without dirtying the tracked
# paper/intervals.json on every verify (default path unchanged for reproducers).
OUT = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'paper/intervals.json'
Z = 1.959963984540054  # two-sided 95%
ALPHA = 0.05


def wilson(k, n, z=Z):
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def cp_upper_zero(n, alpha=ALPHA):
    """Exact one-sided upper bound when the numerator is 0."""
    return 1.0 - alpha ** (1.0 / n)


def labels(path):
    with open(path, encoding='utf-8') as f:
        return {int(r['sample_index']): r for r in csv.DictReader(f)}


PASS = {'pass1': labels('paper/annotations.csv'),
        'pass2': labels('paper/annotations-second-pass.csv')}

COV = json.load(open('bench/corpus-coverage-union.json', encoding='utf-8'))

# --- recall ground truth: re-count from the csv, do not trust the prose --------
# paper/merged-pr-recall.csv lists ALL 70 merged PRs; the recall denominator is the
# subset whose belongs_to_family == 'yes'. detected == 'n/a' marks out-of-scope rows.
with open('paper/merged-pr-recall.csv', encoding='utf-8') as f:
    rec_rows = list(csv.DictReader(f))
    rec_cols = list(rec_rows[0].keys()) if rec_rows else []
family = [r for r in rec_rows if r.get('belongs_to_family', '').strip().lower() == 'yes']
rec_detected = sum(1 for r in family if r.get('detected', '').strip().lower() == 'yes')
rec_in_scope = sum(1 for r in family if r.get('detected', '').strip().lower() in ('yes', 'no'))
rec_missed = sum(1 for r in family if r.get('detected', '').strip().lower() == 'no')
print('recall re-count: family=%d detected=%d missed=%d out-of-scope=%d' % (
    len(family), rec_detected, rec_missed, len(family) - rec_detected - rec_missed))

cells = []


def add(group, label, k, n, note=''):
    lo, hi = wilson(k, n)
    row = {'group': group, 'label': label, 'numerator': k, 'denominator': n,
           'point': round(k / n, 4),
           'wilson95_low': round(lo, 4), 'wilson95_high': round(hi, 4),
           'wilson95_low_pct': round(100 * lo, 1), 'wilson95_high_pct': round(100 * hi, 1),
           'width_pct': round(100 * (hi - lo), 1),
           'one_sided95_upper_pct': round(100 * cp_upper_zero(n), 1) if k == 0 else None,
           'note': note}
    cells.append(row)


for pname, rows in PASS.items():
    n = len(rows)
    cnt = Counter(r['label'] for r in rows.values())
    add('overall[%s]' % pname, 'defect rate', cnt['DEFECT'], n, 'main RQ2 estimate')
    add('overall[%s]' % pname, 'contract rate', cnt['CONTRACT'], n)
    add('overall[%s]' % pname, 'false-positive rate', cnt['FALSE_POSITIVE'], n)

    by_rule = defaultdict(Counter)
    by_repo = defaultdict(Counter)
    for r in rows.values():
        by_rule[r['rule']][r['label']] += 1
        by_repo[r['repo']][r['label']] += 1
    for rule, c in sorted(by_rule.items(), key=lambda kv: -sum(kv[1].values())):
        add('by-rule[%s]' % pname, '%s defect rate' % rule, c['DEFECT'], sum(c.values()))
    for repo, c in sorted(by_repo.items(), key=lambda kv: -sum(kv[1].values())):
        add('by-package[%s]' % pname, '%s defect rate' % repo, c['DEFECT'], sum(c.values()))
    mature = sum(c['DEFECT'] for repo, c in by_repo.items() if repo != 'deepteam')
    mature_n = sum(sum(c.values()) for repo, c in by_repo.items() if repo != 'deepteam')
    add('pooled[%s]' % pname, 'seven mature packages (all but deepteam)', mature, mature_n,
        'the conservative read argued in the discussion')

add('coverage', 'union of four syntactic linters covers failroute findings',
    COV['union_covered'], COV['failroute_total'],
    'source: bench/corpus-coverage-union.json')
for rule, d in sorted(COV['by_rule'].items(), key=lambda kv: -kv[1]['total']):
    add('coverage-by-rule', '%s covered by union' % rule, d['covered'], d['total'])
add('recall', 'recall vs all family fixes', rec_detected, len(family),
    're-counted from paper/merged-pr-recall.csv (belongs_to_family == yes)')
add('recall', 'recall vs in-scope family fixes', rec_detected, rec_in_scope,
    'detected in (yes,no); n/a rows excluded as out of language/rule scope')

# --- O batch: triangulation cells (arm 2 / arm 3 / excl-self / uqlm) and the
# sec:tri sensitivity corners, so that EVERY interval printed in the paper is
# reproducible by this canonical tool (iron law #7: no second implementation).
# arm 2 lives in the companion repo's maintainer-behaviour dataset (read-only);
# arm 3's closed side is the ledger copied into paper/ (byte-identical).
P8 = {'fickling', 'garak', 'inspect_ai', 'smolagents', 'trl', 'uqlm', 'deepteam', 'pydantic-ai-slim'}
DS = os.path.join(os.path.dirname(ROOT), '新项目-contractlens', 'data', 'dataset.jsonl')
LEDGER = 'paper/h1_arm3_classification.csv'
SENS = {}
if os.path.exists(DS) and os.path.exists(LEDGER):
    ds = [json.loads(l) for l in open(DS, encoding='utf-8')]
    sites = [r for r in ds if r.get('pkg') in P8 and r.get('label') in ('FIXED', 'SURVIVED')]
    fixed = sum(1 for r in sites if r['label'] == 'FIXED')
    add('triangulation', 'arm 2: tracked family sites spontaneously fixed', fixed, len(sites),
        'companion-repo dataset.jsonl over the 8 pinned packages')
    uq = [r for r in sites if r['pkg'] == 'uqlm']
    uqf = sum(1 for r in uq if r['label'] == 'FIXED')
    add('triangulation', 'uqlm tracked family sites spontaneously fixed', uqf, len(uq),
        'package-level matched approximation (context, not a test)')
    led = list(csv.DictReader(open(LEDGER, encoding='utf-8')))
    fam_closed = [r for r in led if r.get('family', '').strip().lower() == 'yes']
    nonself = [r for r in fam_closed if r.get('close_reason') != 'self-closed']
    n_merged = len(family)
    add('triangulation', 'arm 3: family fix PRs merged (all closures in denominator)',
        n_merged, n_merged + len(fam_closed), 'denominator = %d merged + %d closed-unmerged'
        % (n_merged, len(fam_closed)))
    add('triangulation', 'arm 3 excluding author self-closures', n_merged, n_merged + len(nonself),
        'the 16/24 figure quoted in the paper')
    uq_prs = sum(1 for r in family if r['repo'] == 'cvs-health/uqlm')
    add('triangulation', 'uqlm author-reported family fixes merged', uq_prs, uq_prs,
        'package-level matched approximation (context, not a test)')
    for k, n_, tag in [(13, 478, 'all tracked sites as risk set'), (13, 144, '30% defect share'),
                       (13, 86, 'boundary'), (13, 85, 'just below boundary'),
                       (13, 72, "paper's own 15% base rate"), (6, 72, 'half the fixes on defects'),
                       (2, 72, 'fixes proportional to defect share')]:
        add('sensitivity', 'arm-2 corner k=%d n=%d (%s)' % (k, n_, tag), k, n_,
            'hypothetical composition; see sec:tri tab:sens')
    a3lo, _a3hi = wilson(n_merged, n_merged + len(fam_closed))
    bnd = next(n_ for n_ in range(13, len(sites) + 1) if wilson(13, n_)[1] < a3lo)
    SENS = {'arm3_lower_pct_exact': round(100 * a3lo, 4),
            'boundary_n_at_k13': bnd,
            'boundary_defect_share_pct': round(100.0 * bnd / len(sites), 2),
            'corner_upper_at_boundary_pct': round(100 * wilson(13, bnd)[1], 4)}
else:
    print('WARNING: companion dataset (%s) or ledger (%s) missing; triangulation cells skipped'
          % (DS, LEDGER))

out = {'generated_at_utc8': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
       'method': 'Wilson score interval, z=%.9f (two-sided 95%%); zero-numerator cells also '
                 'given the exact one-sided Clopper-Pearson upper bound 1-alpha**(1/n)' % Z,
       'recall_csv_columns': rec_cols,
       'sensitivity_boundary': SENS,
       'cells': cells}
json.dump(out, open(OUT, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

print('| Group | Proportion | k/n | point | 95% Wilson CI | one-sided 95% upper |')
print('|---|---|---|---|---|---|')
for c in cells:
    ub = ('%.1f%%' % c['one_sided95_upper_pct']) if c['one_sided95_upper_pct'] is not None else '—'
    # O batch drive-by: print from the pre-rounded *_pct fields; the former
    # 100*round(frac,4) path could disagree with the JSON by 0.1pp (5/5 cell:
    # table showed 56.5, JSON said 56.6). One tool, one rounded value.
    print('| %s | %s | %d/%d | %.1f%% | [%.1f%%, %.1f%%] | %s |' % (
        c['group'], c['label'], c['numerator'], c['denominator'],
        100 * c['point'], c['wilson95_low_pct'], c['wilson95_high_pct'], ub))
print('\nCI wider than 40 percentage points (should not be stated as a point estimate):')
for c in cells:
    if c['width_pct'] > 40:
        print('  %-28s %-42s %d/%-3d width %.1f pp' % (
            c['group'], c['label'], c['numerator'], c['denominator'], c['width_pct']))
print('\nwrote %s (%d cells)' % (OUT, len(cells)))
