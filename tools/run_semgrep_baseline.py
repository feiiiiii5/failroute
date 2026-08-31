#!/usr/bin/env python3
"""P5: semgrep baseline merged into the linter comparison + 5-tool coverage union.

Runs a hand-written exception-handling rule set (tools/semgrep-rules/exception-handling.yaml)
over the same pinned corpus as tools/coverage_union.py, plus re-runs the four original
linters, so that the union is computed from real line sets rather than from cached counts.

Writes:  bench/corpus-linter-comparison.json   (adds linters["semgrep"] per package)
         bench/corpus-coverage-union-5tool.json (5-tool union; the 4-tool baseline file
                                                 is deliberately NOT overwritten)
Usage: cd 新项目-failroute && .venv/bin/python tools/run_semgrep_baseline.py
"""
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
PY = '.venv/bin/python'
SG = os.environ.get('SEMGREP', '/tmp/sgvenv/bin/semgrep')
RULES = 'tools/semgrep-rules/exception-handling.yaml'
LOCK = json.load(open('paper/corpus-lock.json', encoding='utf-8'))
TOL = 1


def sh(c, t=1800):
    return subprocess.run(c, capture_output=True, text=True, timeout=t)


def ruff(r):
    o = sh([PY, '-m', 'ruff', 'check', '--no-cache', '--isolated', '--select', 'S110,S112',
            '--output-format', 'json', r]).stdout
    return [(os.path.abspath(d['filename']), d['location']['row']) for d in json.loads(o or '[]')]


def bandit(r):
    o = sh([PY, '-m', 'bandit', '-r', r, '-f', 'json', '-t', 'B110,B112', '-q']).stdout
    return [(os.path.abspath(d['filename']), d['line_number'])
            for d in json.loads(o or '{}').get('results', [])]


def pylint(r):
    o = sh([PY, '-m', 'pylint', '--disable=all', '--enable=W0702,W0703,W0705,W0706',
            '--output-format=json', '--persistent=n', '--jobs=4', r]).stdout
    return [(os.path.abspath(d['path']), d['line']) for d in json.loads(o or '[]')]


def flake8(r):
    o = sh([PY, '-m', 'flake8', '--select', 'E722,B001,B017', '--format', '%(path)s\t%(row)d', r]).stdout
    out = []
    dropped = 0
    for ln in (o or '').splitlines():
        a = ln.split('\t')
        if len(a) == 2:
            try:
                out.append((os.path.abspath(a[0]), int(a[1])))
            except ValueError:
                dropped += 1
    if dropped:
        print(f'  [warn] {dropped} unparseable row(s) dropped', file=__import__('sys').stderr)
    return out


def semgrep(r):
    p = sh([SG, '--metrics=off', '--disable-version-check', '--no-git-ignore', '--json',
            '-f', RULES, r])
    if p.returncode not in (0, 1):
        raise RuntimeError((p.stderr or p.stdout)[-800:])
    d = json.loads(p.stdout or '{}')
    return [(os.path.abspath(x['path']), x['start']['line']) for x in d.get('results', [])]


TOOLS = [('ruff', ruff), ('bandit', bandit), ('pylint', pylint),
         ('flake8+bugbear', flake8), ('semgrep', semgrep)]

cmp_doc = json.load(open('bench/corpus-linter-comparison.json', encoding='utf-8'))
per_tool = defaultdict(Counter)
union_by_rule = Counter()
union_by_rule_4 = Counter()
total_by_rule = Counter()
covered_total = 0
covered_total_4 = 0
fr_total = 0
semgrep_codes = Counter()
pkg_rows = []

for p in LOCK['packages']:
    name = p['name']
    root = os.path.normpath(os.path.join('paper/corpus', p['extracted_to'], p['scan_root']))
    fr = []
    for line in open('paper/scan/%s.jsonl' % name, encoding='utf-8'):
        d = json.loads(line)
        fr.append((os.path.abspath(d['file']), d['lineno'], d['rule']))
    fr_total += len(fr)
    for _, _, rl in fr:
        total_by_rule[rl] += 1

    hits = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fn, root): n for n, fn in TOOLS}
        for fu in futs:
            n = futs[fu]
            t0 = time.time()
            try:
                hits[n] = fu.result()
                status, err = 'ok', None
            except Exception as e:  # failroute: ignore
                # Intentional: the error is recorded in `status`/`err` two lines down
                # and written to the output JSON, so the failure is visible, not silent.
                hits[n] = []
                status, err = 'error', repr(e)[:400]
            secs = round(time.time() - t0, 1)
            if n == 'semgrep':
                entry = {'status': status, 'select': RULES, 'findings': len(set(hits[n])),
                         'seconds': secs}
                if err:
                    entry['error'] = err
                cmp_row = next((r for r in cmp_doc['packages'] if r['name'] == name), None)
                if cmp_row is not None:
                    cmp_row['linters']['semgrep'] = entry
    idx = {}
    for n, hs in hits.items():
        m = defaultdict(set)
        for f, l in hs:
            m[f].add(l)
        idx[n] = m

    cov = cov4 = 0
    for f, l, rl in fr:
        hit5 = [n for n, _ in TOOLS if any(abs(c - l) <= TOL for c in idx[n].get(f, ()))]
        hit4 = [n for n in hit5 if n != 'semgrep']
        for n in hit5:
            per_tool[n][rl] += 1
        if hit5:
            cov += 1
            union_by_rule[rl] += 1
        if hit4:
            cov4 += 1
            union_by_rule_4[rl] += 1
        if hit5 and not hit4:
            semgrep_codes['newly_covered_by_semgrep'] += 1
    covered_total += cov
    covered_total_4 += cov4
    pkg_rows.append({'name': name, 'failroute': len(fr), 'covered_5tool': cov,
                     'covered_4tool': cov4, 'only_5tool': len(fr) - cov})
    print('%-18s failroute=%-5d covered4=%-5d covered5=%-5d semgrep_raw=%d' % (
        name, len(fr), cov4, cov, len(set(hits['semgrep']))), flush=True)

sg_ver = sh([SG, '--version']).stdout.strip()
cmp_doc.setdefault('tool_versions', {})['semgrep'] = sg_ver
cmp_doc['semgrep_note'] = ('semgrep row added by tools/run_semgrep_baseline.py on %s. '
                           'Rule set is hand-written (tools/semgrep-rules/'
                           'exception-handling.yaml); it is not an upstream semgrep '
                           'default ruleset.' % time.strftime('%Y-%m-%d', time.gmtime()))
json.dump(cmp_doc, open('bench/corpus-linter-comparison.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

out = {'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
       'line_tolerance': TOL, 'semgrep_version': sg_ver, 'rule_file': RULES,
       'failroute_total': fr_total,
       'union_covered_5tool': covered_total,
       'union_covered_4tool_recheck': covered_total_4,
       'failroute_only_5tool': fr_total - covered_total,
       'newly_covered_by_semgrep': semgrep_codes['newly_covered_by_semgrep'],
       'by_rule': {r: {'total': total_by_rule[r], 'covered_5': union_by_rule[r],
                       'covered_4': union_by_rule_4[r],
                       'only_5': total_by_rule[r] - union_by_rule[r]}
                   for r in total_by_rule},
       'per_tool_by_rule': {n: dict(per_tool[n]) for n, _ in TOOLS},
       'per_package': pkg_rows}
json.dump(out, open('bench/corpus-coverage-union-5tool.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('\n4-tool recheck=%d  5-tool=%d  (baseline file said 253)  semgrep-new=%d' % (
    covered_total_4, covered_total, semgrep_codes['newly_covered_by_semgrep']))
print('wrote bench/corpus-linter-comparison.json + bench/corpus-coverage-union-5tool.json')
