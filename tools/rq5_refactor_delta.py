#!/usr/bin/env python3
"""RQ5: what the predicate refactor actually changed, counted from the two frames.

Both frames are per-finding coverage exports produced by tools/coverage_union.py
--emit-per-finding over the same pinned corpus:

    bench/corpus-coverage-per-finding-621.jsonl   v0.8.0 predicate, 621 findings
    bench/corpus-coverage-per-finding-v2.jsonl    refactored predicate, 476 findings

Everything here is a count or a set difference. No interval is computed in this file:
proportions that need one go through tools/compute_intervals.py --rq5, which is the
canonical Wilson implementation (iron law #7 -- there is exactly one in the tree).

Why this is a tool and not prose: three figures quoted from an earlier hand count of
this delta did not survive being recomputed here. The dropped/added split is not a
subset relation (sites were both lost and gained), the "dropped findings were
failroute-only" share has to be stated over dropped *sites* rather than over the net
change, and the share of declared-contract findings the refactor silenced is below
100% -- a handful still report at HIGH or MEDIUM. Counts that flatter the change are
the ones most worth re-running.

Usage:
    cd 新项目-failroute && .venv/bin/python tools/rq5_refactor_delta.py
Writes bench/rq5-refactor-delta.json and prints the report.
"""
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = 'bench/corpus-coverage-per-finding-621.jsonl'
NEW = 'bench/corpus-coverage-per-finding-v2.jsonl'
# The per-finding export as it stood before the V3 covered_by fix. Preserved rather than
# regenerated: the over-crediting inference it records no longer exists in the source, so
# this file is the only record of what the paper's V2 static-novelty figure came from.
PRE_FIX = 'bench/corpus-coverage-per-finding-v2-pre-coverby-fix.jsonl'
LABELS = [('paper/annotations.csv', 'frozen 80'),
          ('paper/annotations-v2-additions.csv', 'supplementary 60')]
OUT = 'bench/rq5-refactor-delta.json'


def key(rec):
    return (rec['repo'], rec['file'], int(rec['lineno']), rec['rule'])


def load(path):
    if not os.path.isfile(path):
        sys.exit('error: required per-finding export missing: %s\n'
                 '  regenerate with: .venv/bin/python tools/coverage_union.py '
                 '--findings-dir <dir> --emit-per-finding %s --out <json>' % (path, path))
    recs = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
    by_site = {}
    for r in recs:
        by_site.setdefault(key(r), []).append(r)
    return recs, by_site


def return_annotation(sig):
    """Classify a signature's declared return type. Returns (group, annotation)."""
    if not sig or '->' not in sig:
        return ('no-declared-return', '')
    ret = sig.split('->', 1)[1].strip().rstrip(':').strip()
    if not ret:
        return ('truncated', '')
    # An unbalanced opener means the CSV field was cut mid-annotation, so the
    # return type is not recoverable; say so rather than guessing a group.
    if ret.count('[') != ret.count(']'):
        return ('truncated', ret)
    if re.fullmatch(r'None', ret):
        return ('none', ret)
    admits_none = bool(re.search(r'\bOptional\s*\[', ret)) or \
        bool(re.search(r'\bNone\b', ret)) or 'Union' in ret
    return ('none-admitting' if admits_none else 'other', ret)



def stable(counter: "Counter[str]") -> dict:
    """Sorted view of a Counter.

    Several of these counts are built by iterating a *set* (site differences,
    removed-rule differences), so their insertion order follows string hash
    randomisation and changes between processes. The numbers were always right;
    the printed order was not, which silently broke any claim whose expect
    quoted it. Sorting at build time keeps stdout and the JSON artefact
    byte-stable across runs.
    """
    return {k: counter[k] for k in sorted(counter)}


def main():
    os.chdir(ROOT)
    for p in [OLD, NEW] + [f for f, _ in LABELS]:
        if not os.path.isfile(p):
            sys.exit('error: required input missing: %s' % p)

    old_recs, old_sites = load(OLD)
    new_recs, new_sites = load(NEW)
    ok, nk = set(old_sites), set(new_sites)
    dropped, added, kept = ok - nk, nk - ok, ok & nk

    def cov(rec):
        return bool(rec['baseline_tools_colocated'])

    def only_share(keys, table):
        n = len(keys)
        o = sum(1 for k in keys if not cov(table[k][0]))
        return {'sites': n, 'failroute_only': o,
                'linter_covered': n - o,
                'failroute_only_pct': round(100.0 * o / n, 1) if n else None}

    # ---- label disposition ---------------------------------------------------
    labels = []
    for path, tag in LABELS:
        for r in csv.DictReader(open(path, encoding='utf-8')):
            r['_src'] = tag
            labels.append(r)
    # Joined on (repo, file, lineno), NOT on the rule as well: a label identifies a
    # handler, and the refactor can reclassify a handler under a different rule without
    # dropping it. Joining on the rule too counts that as a deletion -- it cost one
    # labelled FALSE_POSITIVE (fickling polyglot.py:150, implicit-fallback in the frozen
    # frame, silent-fallback in this one) and made this tool report a single surviving
    # false positive where there are two. This is also the key compute_intervals.py --rq5
    # uses for the crosstab, so the two now agree. The frame difference above stays on
    # the four-part key, because there a finding really is identified by its rule.
    by_site = {}
    for _k, _recs in new_sites.items():
        by_site.setdefault((_k[0], _k[1], _k[2]), _recs[0])
    disp = defaultdict(Counter)
    ann_group = Counter()
    ann_disp = Counter()
    rule_changed = []
    for r in labels:
        lab = r['label']
        f = by_site.get((r['repo'], r['file'], int(r['lineno'])))
        if f is not None:
            sev = f['severity']
            disp[lab]['kept'] += 1
            disp[lab]['sev_' + sev] += 1
            state = 'kept-' + sev
            if f['rule'] != r['rule']:
                disp[lab]['rule_changed'] += 1
                rule_changed.append({'label': lab, 'repo': r['repo'], 'file': r['file'],
                                     'lineno': int(r['lineno']), 'labelled_as': r['rule'],
                                     'now_reported_as': f['rule'], 'severity': sev})
        else:
            disp[lab]['dropped'] += 1
            state = 'dropped'
        disp[lab]['_n'] += 1
        grp, ann = return_annotation(r.get('function_signature', ''))
        r['_ann_group'] = grp
        ann_group[(lab, grp)] += 1
        ann_disp[(lab, grp, state)] += 1

    def contract_group(grps):
        n = sum(ann_group[('CONTRACT', g)] for g in grps)
        loud = sum(v for (lab, g, st), v in ann_disp.items()
                   if lab == 'CONTRACT' and g in grps
                   and st in ('kept-high', 'kept-medium'))
        return {'labels': n, 'still_high_or_medium': loud,
                'dropped_or_downgraded': n - loud,
                'dropped_or_downgraded_pct': round(100.0 * (n - loud) / n, 1) if n else None}

    # ---- the covered_by fix, before and after --------------------------------
    # The pre-fix export is preserved rather than regenerated: the inference it records
    # no longer exists in the source, so this file is the only record of what the paper's
    # V2 numbers were computed from. The paper's before/after table cites it.
    if not os.path.isfile(PRE_FIX):
        sys.exit('error: the preserved pre-fix per-finding export is missing: %s\n'
                 '  the paper quotes a before/after comparison against it, so it cannot '
                 'be regenerated from the current source' % PRE_FIX)
    pre_recs, _ = load(PRE_FIX)
    if len(pre_recs) != len(new_recs):
        sys.exit('error: pre-fix export has %d findings but the current frame has %d -- '
                 'the covered_by fix must not change what is reported, only what it is '
                 'credited with' % (len(pre_recs), len(new_recs)))

    def novel(recs):
        return sum(1 for r in recs if not r['covered_by_static'])

    def high_novel(recs):
        return sum(1 for r in recs if r['severity'] == 'high' and not r['covered_by_static'])

    over = [(p, q) for p, q in zip(pre_recs, new_recs)
            if set(p['covered_by_static']) - set(q['covered_by_static'])]
    gained = [(p, q) for p, q in zip(pre_recs, new_recs)
              if set(q['covered_by_static']) - set(p['covered_by_static'])]
    emptied = [(p, q) for p, q in over if not q['covered_by_static']]
    covered_by_fix = {
        'pre_fix_export': PRE_FIX,
        'findings_pre': len(pre_recs), 'findings_post': len(new_recs),
        'static_novel_pre': novel(pre_recs), 'static_novel_post': novel(new_recs),
        'static_novel_pct_pre': round(100.0 * novel(pre_recs) / len(pre_recs), 1),
        'static_novel_pct_post': round(100.0 * novel(new_recs) / len(new_recs), 1),
        'high_uncovered_pre': high_novel(pre_recs), 'high_uncovered_post': high_novel(new_recs),
        'coloc_novel_pre': sum(1 for r in pre_recs if not cov(r)),
        'coloc_novel_post': sum(1 for r in new_recs if not cov(r)),
        'over_credited_findings': len(over),
        'over_credited_that_became_novel': len(emptied),
        'over_credited_but_still_covered': len(over) - len(emptied),
        'gained_credit_findings': len(gained),
        'over_credited_by_rule': dict(Counter(p['rule'] for p, _ in over)),
        'over_credited_by_severity': dict(Counter(p['severity'] for p, _ in over)),
        'rules_removed': stable(Counter(x for p, q in over
                                         for x in set(p['covered_by_static'])
                                         - set(q['covered_by_static']))),
    }

    out = {
        'inputs': {'old': OLD, 'new': NEW,
                   'labels': [{'path': p, 'tag': t} for p, t in LABELS]},
        'frames': {
            'old': {'findings': len(old_recs), 'distinct_sites': len(ok),
                    'linter_covered': sum(1 for r in old_recs if cov(r)),
                    'failroute_only': sum(1 for r in old_recs if not cov(r)),
                    'by_rule': stable(Counter(k[3] for k in ok))},
            'new': {'findings': len(new_recs), 'distinct_sites': len(nk),
                    'linter_covered': sum(1 for r in new_recs if cov(r)),
                    'failroute_only': sum(1 for r in new_recs if not cov(r)),
                    'by_rule': stable(Counter(k[3] for k in nk)),
                    'severity': dict(Counter(r['severity'] for r in new_recs)),
                    'isomorphism': dict(Counter(str(r['isomorphism']) for r in new_recs))},
        },
        'delta': {
            'net_findings': len(new_recs) - len(old_recs),
            'sites_dropped': len(dropped), 'sites_added': len(added),
            'sites_kept': len(kept),
            'is_a_subset': not added,
            'dropped': only_share(dropped, old_sites),
            'added': only_share(added, new_sites),
            'kept': only_share(kept, new_sites),
            'dropped_by_rule': stable(Counter(k[3] for k in dropped)),
            'added_by_rule': stable(Counter(k[3] for k in added)),
            'multi_finding_sites_old': sum(1 for k, v in old_sites.items() if len(v) > 1),
            'multi_finding_sites_new': sum(1 for k, v in new_sites.items() if len(v) > 1),
        },
        'label_disposition': {lab: {k: v for k, v in c.items()} for lab, c in disp.items()},
        'label_rule_changes': rule_changed,
        'covered_by_fix': covered_by_fix,
        'declared_return_groups': {'%s/%s' % kk: v for kk, v in sorted(ann_group.items())},
        'contracts': {
            'all': contract_group(set(g for (l, g) in ann_group if l == 'CONTRACT')),
            'none_admitting': contract_group(['none', 'none-admitting']),
            'literal_none': contract_group(['none']),
        },
    }
    json.dump(out, open(OUT, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

    f = out['frames']
    print('frames: %d findings / %d sites  ->  %d findings / %d sites  (net %+d)'
          % (f['old']['findings'], f['old']['distinct_sites'],
             f['new']['findings'], f['new']['distinct_sites'], out['delta']['net_findings']))
    print('linter coverage: %d/%d = %.1f%%  ->  %d/%d = %.1f%%'
          % (f['old']['linter_covered'], f['old']['findings'],
             100 * f['old']['linter_covered'] / f['old']['findings'],
             f['new']['linter_covered'], f['new']['findings'],
             100 * f['new']['linter_covered'] / f['new']['findings']))
    d = out['delta']
    print('sites: dropped %d  added %d  kept %d  (is the new frame a subset? %s)'
          % (d['sites_dropped'], d['sites_added'], d['sites_kept'], d['is_a_subset']))
    for tag in ('dropped', 'added', 'kept'):
        s = d[tag]
        print('  %-8s %4d sites, %4d failroute-only (%.1f%%)'
              % (tag, s['sites'], s['failroute_only'], s['failroute_only_pct'] or 0))
    print('  dropped by rule:', d['dropped_by_rule'])
    print('  added   by rule:', d['added_by_rule'])
    print('  sites reported twice: old %d, new %d'
          % (d['multi_finding_sites_old'], d['multi_finding_sites_new']))
    print('new-frame isomorphism classes:', f['new']['isomorphism'])
    print('new-frame severity:', f['new']['severity'])
    print()
    for lab, c in disp.items():
        print('%-15s n=%d kept=%d dropped=%d  %s'
              % (lab, c['_n'], c['kept'], c['dropped'],
                 {k[4:]: v for k, v in c.items() if k.startswith('sev_')}))
    print()
    for name, c in out['contracts'].items():
        print('CONTRACT %-16s %d labels: dropped-or-downgraded %d (%.1f%%), still HIGH/MEDIUM %d'
              % (name, c['labels'], c['dropped_or_downgraded'],
                 c['dropped_or_downgraded_pct'] or 0, c['still_high_or_medium']))
    print()
    x = covered_by_fix
    print('covered_by fix (pre-fix export: %s)' % x['pre_fix_export'])
    print('  findings                 : %d -> %d (must be equal: the fix changes credit, not output)'
          % (x['findings_pre'], x['findings_post']))
    print('  statically novel         : %d -> %d   (%.1f%% -> %.1f%%)'
          % (x['static_novel_pre'], x['static_novel_post'],
             x['static_novel_pct_pre'], x['static_novel_pct_post']))
    print('  HIGH and uncovered       : %d -> %d' % (x['high_uncovered_pre'], x['high_uncovered_post']))
    print('  co-location novel        : %d -> %d (empirical; the covered_by fix cannot change it -- any move here is the AA1 pylint-invocation correction, not this fix)'
          % (x['coloc_novel_pre'], x['coloc_novel_post']))
    print('  over-credited findings   : %d, of which %d became novel and %d stayed covered'
          % (x['over_credited_findings'], x['over_credited_that_became_novel'],
             x['over_credited_but_still_covered']))
    print('  gained credit            : %d (expected 3: repairing the tuple bail-out adds '
          'BLE001/W0718/S110 to `except (anyio.get_cancelled_exc_class(), Exception):`)'
          % x['gained_credit_findings'])
    print('  over-credited by rule    :', x['over_credited_by_rule'])
    print('  over-credited by severity:', x['over_credited_by_severity'])
    print('  rules removed            :', x['rules_removed'])
    if rule_changed:
        print()
        print('labels whose site is still reported but under a different rule (%d):' % len(rule_changed))
        for rc in rule_changed:
            print('  %-15s %s %s:%d  %s -> %s (sev %s)'
                  % (rc['label'], rc['repo'], rc['file'].split('/')[-1], rc['lineno'],
                     rc['labelled_as'], rc['now_reported_as'], rc['severity']))
    print('\nwrote %s' % OUT)


if __name__ == '__main__':
    main()
