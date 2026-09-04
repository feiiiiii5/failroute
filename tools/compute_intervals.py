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
import glob
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Q1: os.chdir moved into main() so importing this module (h1_stats.py delegation,
# iron law #7) has no side effects on the importer's working directory.
# paper/intervals.json on every verify (default path unchanged for reproducers).
# Q1: --out parsing moved into main() (import-safe).
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



def main() -> None:
    os.chdir(ROOT)
    OUT = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'paper/intervals.json'
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
               # S batch (review item A4): the sec:tri boundary cells sit on a knife edge
               # (n=86 upper 24.1636 vs n=85 upper 24.4282 against arm 3's 24.3763), where
               # one-decimal display renders both as 24.4 and reads as a fudge. Two-decimal
               # fields are carried for every cell; the one-decimal fields are unchanged so
               # existing consumers keep their values.
               'wilson95_low_pct2': round(100 * lo, 2), 'wilson95_high_pct2': round(100 * hi, 2),
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
    # S batch (T3): arm 2 is now read from the PUBLISHED artefact
    # paper/arm2-tracked-sites.csv -- a field-for-field projection of the companion
    # repository's paper-8 rows -- so every arm-2 statistic below is reproducible from
    # the public repo alone. Missing inputs fail loudly instead of skipping silently.
    A2 = 'paper/arm2-tracked-sites.csv'
    LEDGER = 'paper/h1_arm3_classification.csv'
    for _p in (A2, LEDGER):
        if not os.path.exists(_p):
            sys.exit('error: required paper artefact missing: %s' % _p)
    SENS = {}
    SB = {}
    a2 = list(csv.DictReader(open(A2, encoding='utf-8')))
    cnt = Counter(r['label'] for r in a2)
    sites = [r for r in a2 if r['label'] in ('FIXED', 'SURVIVED')]
    fixed = sum(1 for r in sites if r['label'] == 'FIXED')
    add('triangulation', 'arm 2: tracked family sites spontaneously fixed', fixed, len(sites),
        'paper/arm2-tracked-sites.csv, labels FIXED|SURVIVED over the 8 pinned packages')
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
    # S batch (review item A3): readers could not compute a distinct-defect denominator
    # from the paper. Recomputed from the ledger's own notes rather than hardcoded: a
    # closed row is a duplicate when its note says so, or says its substance re-landed
    # in a counted merge.
    dup = [r for r in nonself
           if 'duplicate' in r.get('note', '').lower() or 're-landed' in r.get('note', '').lower()]
    add('triangulation', 'arm 3 on a distinct-defect denominator', n_merged,
        n_merged + len(fam_closed) - len(dup),
        '%d of the %d closed-unmerged family rows are marked duplicate-of, or '
        'substance-shared with, a counted row' % (len(dup), len(fam_closed)))
    uq_prs = sum(1 for r in family if r['repo'] == 'cvs-health/uqlm')
    add('triangulation', 'uqlm author-reported family fixes merged', uq_prs, uq_prs,
        'package-level matched approximation (context, not a test)')
    for k, n_, tag in [(13, 478, 'all tracked sites as risk set'), (13, 144, '30% defect share'),
                       (13, 86, 'boundary'), (13, 85, 'just below boundary'),
                       (13, 72, "paper's own 15% base rate"), (6, 72, 'half the fixes on defects'),
                       (2, 72, 'fixes proportional to defect share')]:
        add('sensitivity', 'arm-2 corner k=%d n=%d (%s)' % (k, n_, tag), k, n_,
            'N-batch single-axis corners; superseded in the paper by the rebase* groups')
    a3lo, a3hi = wilson(n_merged, n_merged + len(fam_closed))
    bnd = next(n_ for n_ in range(13, len(sites) + 1) if wilson(13, n_)[1] < a3lo)
    SENS = {'arm3_lower_pct_exact': round(100 * a3lo, 4),
            'arm3_upper_pct_exact': round(100 * a3hi, 4),
            'boundary_n_at_k13': bnd,
            'boundary_defect_share_pct': round(100.0 * bnd / len(sites), 2),
            'corner_upper_at_boundary_pct': round(100 * wilson(13, bnd)[1], 4),
            'corner_upper_below_boundary_pct': round(100 * wilson(13, bnd - 1)[1], 4)}

    # --- S batch (T2), axis 1: the arm-2 risk set is a CONVENTION, not a measurement.
    # The companion pipeline tracked 2,128 sites over the eight packages and labelled
    # only the 478 FIXED|SURVIVED ones; 1,650 (77.5%) were discarded as TOO_YOUNG /
    # VANISHED / MUTATED and the paper never disclosed it (review item M1).
    RISK = [('fixed_survived', ('FIXED', 'SURVIVED')),
            ('plus_mutated', ('FIXED', 'SURVIVED', 'MUTATED')),
            ('plus_vanished', ('FIXED', 'SURVIVED', 'MUTATED', 'VANISHED')),
            ('all_tracked', ('FIXED', 'SURVIVED', 'MUTATED', 'VANISHED', 'TOO_YOUNG'))]
    risk_sets = {}
    for name, keep in RISK:
        rows = [r for r in a2 if r['label'] in keep]
        risk_sets[name] = {'N': len(rows),
                           'deepteam': sum(1 for r in rows if r['pkg'] == 'deepteam')}

    # --- S batch (T2), axis 2: the defect-share estimator. tools/draw_sample.py
    # guarantees >=1 draw per (rule x package) stratum and allocates the remainder
    # proportionally, so the sampling fraction runs 8.9%-50% across the 19 strata and
    # the unweighted 12/80 is a sample share, not an estimate of the frame's defect
    # share (review items A2/M3). Weighted estimators are computed from the frozen
    # v0.7.0 frame (paper/scan) and paper/annotations.csv.
    frame = []
    for fn in sorted(glob.glob('paper/scan/*.jsonl')):
        for line in open(fn, encoding='utf-8'):
            if line.strip():
                frame.append(json.loads(line))
    Nh = Counter((d['rule'], d['repo']) for d in frame)
    Np = Counter(d['repo'] for d in frame)
    ann1 = PASS['pass1']
    nh, dh, npk, dpk = Counter(), Counter(), Counter(), Counter()
    fnpk, fdpk = Counter(), Counter()
    for r in ann1.values():
        k = (r['rule'], r['repo'])
        nh[k] += 1
        npk[r['repo']] += 1
        if r['label'] == 'DEFECT':
            dh[k] += 1
            dpk[r['repo']] += 1
        # The four implicit-fallback sample items belong to the 659 draw but not to the
        # 649 frozen frame (that rule's findings were all removed as false). A weighted
        # estimator over the 649 frame must divide by the sample items that are IN that
        # frame, or it mixes two frames and biases the rate down. The unweighted and the
        # per-package Table 6 rates keep all 80 / all 14 items, as the paper states them.
        if k in Nh:
            fnpk[r['repo']] += 1
            if r['label'] == 'DEFECT':
                fdpk[r['repo']] += 1
    frame_n = len(frame)
    w_strat = sum(Nh[k] * (dh[k] / nh[k]) for k in Nh if nh.get(k))
    w_pkg = sum(Np[p] * (fdpk[p] / fnpk[p]) for p in Np if fnpk.get(p))
    fracs = [nh[k] / Nh[k] for k in Nh if nh.get(k)]
    share_unw = sum(dh.values()) / len(ann1)
    share_strat = w_strat / frame_n
    share_pkg = w_pkg / frame_n
    dt_lo, dt_hi = wilson(dpk['deepteam'], npk['deepteam'])
    dt_rate = dpk['deepteam'] / npk['deepteam']

    EST = [('unweighted 12/80 (deprecated as an estimator)', share_unw),
           ('design-weighted by rule x package stratum', share_strat),
           ('design-weighted by package, frame-restricted', share_pkg)]
    for name, _keep in RISK:
        N, dt = risk_sets[name]['N'], risk_sets[name]['deepteam']
        g = 'rebase%d' % N
        for ename, share in EST:
            add(g, 'risk set %s x %s' % (name, ename), fixed, int(round(N * share)),
                'S-batch 2-D sensitivity; see sec:tri tab:sens')
        add(g, 'risk set %s x package composition (deepteam-specific rate)' % name,
            fixed, int(round(dt * dt_rate)),
            '%d deepteam sites x labelled rate %d/%d' % (dt, dpk['deepteam'], npk['deepteam']))
    n_floor = int(round(risk_sets['fixed_survived']['deepteam'] * dt_lo))
    add('rebase%d' % risk_sets['fixed_survived']['N'],
        'risk set fixed_survived x composition FLOOR (deepteam at its Wilson lower bound)',
        fixed, n_floor,
        'most conservative composition cell; every other package taken as zero defects')
    n_rev = risk_sets['plus_vanished']['N']
    add('rebase%d' % n_rev, 'REVERSE corner: every VANISHED site counted as maintainer action',
        fixed + cnt['VANISHED'], n_rev, 'not supportable; arm 2 would exceed arm 3')

    LK = json.load(open('paper/corpus-lock.json', encoding='utf-8'))
    sdist_lines = LK['totals']['total_lines']
    scanned_lines = sum(p.get('scan_root_total_lines') or 0 for p in LK['packages'])
    sdist_py = LK['totals']['py_files']
    scanned_py = sum(p.get('scan_root_py_files') or 0 for p in LK['packages'])
    SYM = 'bench/corpus-coverage-union-ruff-ble001.json'
    SYM5 = 'bench/corpus-coverage-union-5tool-ruff-ble001.json'
    NARROW5 = 'bench/corpus-coverage-union-5tool.json'
    sym = json.load(open(SYM, encoding='utf-8')) if os.path.exists(SYM) else {}
    sym5 = json.load(open(SYM5, encoding='utf-8')) if os.path.exists(SYM5) else {}
    nar5 = json.load(open(NARROW5, encoding='utf-8')) if os.path.exists(NARROW5) else {}
    ruff_narrow = sum(COV['per_tool_by_rule']['ruff'].values())
    pylint_coloc = sum(COV['per_tool_by_rule']['pylint'].values())
    ruff_sym = sum(sym.get('per_tool_by_rule', {}).get('ruff', {}).values())
    dt_findings = {d['name']: d['failroute'] for d in COV.get('per_package', [])}.get('deepteam', 0)
    SB = {
        'arm2_population': {
            'tracked_sites_total': len(a2), 'labels': dict(cnt),
            'binary_labelled': len(sites), 'fixed': fixed,
            'discarded': len(a2) - len(sites),
            'discarded_pct': round(100.0 * (len(a2) - len(sites)) / len(a2), 2),
            'binary_pct_of_tracked': round(100.0 * len(sites) / len(a2), 2),
            'carries_failroute_rule': sum(1 for r in sites if r['rule_first']),
            'carries_failroute_rule_pct': round(
                100.0 * sum(1 for r in sites if r['rule_first']) / len(sites), 2),
            'deepteam_share_of_binary_pct': round(
                100.0 * risk_sets['fixed_survived']['deepteam'] / len(sites), 2),
            'deepteam_share_of_findings_pct': round(100.0 * dt_findings / COV['failroute_total'], 2),
            'deepteam_sites_under_metrics_or_vulnerabilities': sum(
                1 for r in sites if r['pkg'] == 'deepteam'
                and r['file'].startswith(('metrics/', 'vulnerabilities/'))),
            'survived_days_span_min': min(float(r['days_span']) for r in sites
                                          if r['label'] == 'SURVIVED'),
            'survived_versions_min': min(int(r['n_versions_observed']) for r in sites
                                         if r['label'] == 'SURVIVED'),
            'fixed_pr_attributed': sum(1 for r in sites if r['label'] == 'FIXED'
                                       and r['attributed_pr']),
            'arm3_duplicate_rows': len(dup),
            'arm3_distinct_defects': n_merged + len(fam_closed) - len(dup),
        },
        'risk_sets': risk_sets,
        'weighted_defect_share': {
            'frame': frame_n, 'frame_strata': len(Nh),
            'sample_items': len(ann1), 'sample_items_in_frame_strata': sum(nh[k] for k in Nh),
            'deepteam_items_in_frame': fnpk['deepteam'],
            'sampling_fraction_min_pct': round(100 * min(fracs), 1),
            'sampling_fraction_max_pct': round(100 * max(fracs), 1),
            'unweighted_pct': round(100 * share_unw, 2),
            'weighted_by_stratum_pct': round(100 * share_strat, 2),
            'weighted_by_stratum_numerator': round(w_strat, 2),
            'weighted_by_package_pct': round(100 * share_pkg, 2),
            'weighted_by_package_numerator': round(w_pkg, 2),
            'deepteam_labelled': '%d/%d' % (dpk['deepteam'], npk['deepteam']),
            'deepteam_wilson_pct': [round(100 * dt_lo, 2), round(100 * dt_hi, 2)],
        },
        'extrapolated_defects': {
            'deepteam_findings': dt_findings,
            'point': round(dt_findings * dt_rate, 1),
            'low': round(dt_findings * dt_lo, 1), 'high': round(dt_findings * dt_hi, 1),
            'other_seven_point': 0,
            'naive_global_at_15pct': round(COV['failroute_total'] * share_unw, 1),
        },
        'denominator_factors': {
            'sdist_lines': sdist_lines, 'scanned_lines': scanned_lines,
            'sdist_py_files': sdist_py, 'scanned_py_files': scanned_py,
            'findings': COV['failroute_total'],
            'factor_scanned': round(scanned_lines / COV['failroute_total'], 2),
            'orders_scanned': round(math.log10(scanned_lines / COV['failroute_total']), 4),
            'factor_sdist': round(sdist_lines / COV['failroute_total'], 2),
            'orders_sdist': round(math.log10(sdist_lines / COV['failroute_total']), 4),
        },
        'baseline_symmetry': {
            'ruff_narrow_select': 'S110,S112', 'ruff_narrow_colocated': ruff_narrow,
            'ruff_symmetric_select': sym.get('ruff_select'), 'ruff_symmetric_colocated': ruff_sym,
            'pylint_colocated': pylint_coloc,
            'union4_narrow': COV['union_covered'], 'union4_symmetric': sym.get('union_covered'),
            'union5_narrow': nar5.get('union_covered_5tool'),
            'union5_symmetric': sym5.get('union_covered_5tool'),
            'only4_narrow': COV['failroute_only'], 'only4_symmetric': sym.get('failroute_only'),
            'only5_narrow': nar5.get('failroute_only'), 'only5_symmetric': sym5.get('failroute_only'),
            'ratio_pylint_over_ruff_narrow': round(pylint_coloc / ruff_narrow, 4),
            'ratio_pylint_over_ruff_symmetric': round(pylint_coloc / ruff_sym, 4)
            if ruff_sym else None,
        },
    }

    out = {'generated_at_utc8': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
           'method': 'Wilson score interval, z=%.9f (two-sided 95%%); zero-numerator cells also '
                     'given the exact one-sided Clopper-Pearson upper bound 1-alpha**(1/n)' % Z,
           'recall_csv_columns': rec_cols,
           'sensitivity_boundary': SENS,
           's_batch': SB,
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


if __name__ == '__main__':
    main()
