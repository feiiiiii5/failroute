#!/usr/bin/env python3
"""P5 detail pass: semgrep-only match counts + per-rule code tallies per package.

tools/run_semgrep_baseline.py merged semgrep findings/seconds into
bench/corpus-linter-comparison.json but left matched_failroute unset; this script
fills it in (±1-line co-location against paper/scan/<pkg>.jsonl) and records which
hand-written rule fired. Read-only w.r.t. the corpus; rewrites only the comparison json.

Usage: cd 新项目-failroute && SEMGREP=/tmp/sgvenv/bin/semgrep .venv/bin/python tools/semgrep_detail.py
"""
import json, io, os, subprocess, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
SG = os.environ.get('SEMGREP', '/tmp/sgvenv/bin/semgrep')
RULES = 'tools/semgrep-rules/exception-handling.yaml'
LOCK = json.load(io.open('paper/corpus-lock.json', encoding='utf-8'))
TOL = 1
cmp_doc = json.load(io.open('bench/corpus-linter-comparison.json', encoding='utf-8'))
codes_all = collections.Counter()
for p in LOCK['packages']:
    root = os.path.normpath(os.path.join('paper/corpus', p['extracted_to'], p['scan_root']))
    r = subprocess.run([SG, '--metrics=off', '--disable-version-check', '--no-git-ignore',
                        '--json', '-f', RULES, root], capture_output=True, text=True, timeout=1800)
    res = json.loads(r.stdout or '{}').get('results', [])
    idx = collections.defaultdict(set)
    for x in res:
        idx[os.path.abspath(x['path'])].add(x['start']['line'])
    fr = []
    for line in io.open('paper/scan/%s.jsonl' % p['name'], encoding='utf-8'):
        d = json.loads(line)
        fr.append((os.path.abspath(d['file']), d['lineno'], d['rule']))
    matched = 0
    by_rule = collections.Counter()
    for f, l, rl in fr:
        if any(abs(c - l) <= TOL for c in idx.get(f, ())):
            matched += 1
            by_rule[rl] += 1
    codes = collections.Counter(x['check_id'].split('.')[-1] for x in res)
    codes_all.update(codes)
    row = next((x for x in cmp_doc['packages'] if x['name'] == p['name']), None)
    if row is not None:
        row['linters']['semgrep']['matched_failroute'] = matched
        row['linters']['semgrep']['codes'] = dict(codes)
        row['linters']['semgrep']['matched_by_failroute_rule'] = dict(by_rule)
    print('%-16s raw=%-5d matched=%-4d uniq=%d | %s' % (
        p['name'], len(res), matched, len(set((os.path.abspath(x['path']), x['start']['line'])
                                             for x in res)),
        ' '.join('%s=%d' % kv for kv in codes.most_common())), flush=True)
json.dump(cmp_doc, io.open('bench/corpus-linter-comparison.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('\nrule tallies corpus-wide:', dict(codes_all.most_common()))
print('updated bench/corpus-linter-comparison.json')
