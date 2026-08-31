#!/usr/bin/env python3
"""在钉版语料（paper/corpus）上跑 failroute 与四个句法 linter 的对照。

与 tools/compare_linters.py 的区别：那一份只扫 failroute 自身源码 + 标注语料，
本脚本扫的是 8 个真实 AI/ML 包的钉版源码，是论文 RQ1 的正式口径。

用法：cd 新项目-failroute && .venv/bin/python tools/compare_linters_corpus.py
"""
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = '.venv/bin/python'
LOCK = json.load(open('paper/corpus-lock.json', encoding='utf-8'))
TOL = 1  # 行号容差


def sh(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def tool_version(mod, args=('--version',)):
    r = sh([PY, '-m', mod, *args])
    return ((r.stdout or r.stderr).strip().splitlines() or [''])[0]


def run_ruff(root):
    r = sh([PY, '-m', 'ruff', 'check', '--no-cache', '--isolated',
            '--select', 'S110,S112', '--output-format', 'json', root])
    hits = []
    try:
        for d in json.loads(r.stdout or '[]'):
            hits.append((os.path.abspath(d['filename']), d['location']['row'], d.get('code')))
    except Exception as e:
        # A malformed payload means this linter contributed zero coverage to the
        # comparison. Swallowing it would silently understate the baseline and
        # overstate failroute's novelty -- the exact defect class this repo is about.
        raise RuntimeError(
            f"{__name__}: could not parse output; the comparison would be wrong. "
            f"stderr={(r.stderr or '')[:300]!r}") from e
    return hits


def run_bandit(root):
    r = sh([PY, '-m', 'bandit', '-r', root, '-f', 'json', '-t', 'B110,B112', '-q'])
    hits = []
    try:
        for d in json.loads(r.stdout or '{}').get('results', []):
            hits.append((os.path.abspath(d['filename']), d['line_number'], d.get('test_id')))
    except Exception as e:
        # A malformed payload means this linter contributed zero coverage to the
        # comparison. Swallowing it would silently understate the baseline and
        # overstate failroute's novelty -- the exact defect class this repo is about.
        raise RuntimeError(
            f"{__name__}: could not parse output; the comparison would be wrong. "
            f"stderr={(r.stderr or '')[:300]!r}") from e
    return hits


def run_pylint(root):
    r = sh([PY, '-m', 'pylint', '--disable=all',
            '--enable=W0702,W0703,W0705,W0706', '--output-format=json',
            '--persistent=n', '--jobs=4', root])
    hits = []
    try:
        for d in json.loads(r.stdout or '[]'):
            hits.append((os.path.abspath(d['path']), d['line'], d.get('message-id')))
    except Exception as e:
        # pylint is the strongest baseline in this comparison (178 + 67 of the 253).
        # If its output fails to parse and we return [], the headline coverage number
        # collapses without anyone noticing. Fail loudly instead.
        raise RuntimeError(
            f"pylint: could not parse output; the comparison would be wrong. "
            f"stderr={(r.stderr or '')[:300]!r}") from e
    return hits


def run_flake8(root):
    r = sh([PY, '-m', 'flake8', '--select', 'E722,B001,B017',
            '--format', '%(path)s\t%(row)d\t%(code)s', root])
    hits = []
    dropped = 0
    for line in (r.stdout or '').splitlines():
        parts = line.split('\t')
        if len(parts) == 3:
            try:
                hits.append((os.path.abspath(parts[0]), int(parts[1]), parts[2]))
            except ValueError:
                dropped += 1
    if dropped:
        print(f"  [warn] flake8: {dropped} unparseable row(s) dropped", file=sys.stderr)
    return hits


LINTERS = [('ruff', run_ruff, 'S110,S112'),
           ('bandit', run_bandit, 'B110,B112'),
           ('pylint', run_pylint, 'W0702,W0703,W0705,W0706'),
           ('flake8+bugbear', run_flake8, 'E722,B001,B017')]

report = {'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
          'corpus_lock': 'paper/corpus-lock.json', 'line_tolerance': TOL,
          'tool_versions': {}, 'packages': []}
for name, mod in [('ruff', 'ruff'), ('bandit', 'bandit'), ('pylint', 'pylint'), ('flake8', 'flake8')]:
    report['tool_versions'][name] = tool_version(mod)

grand = defaultdict(int)
grand_match = defaultdict(int)
grand_rule_match = defaultdict(Counter)

for p in LOCK['packages']:
    root = os.path.normpath(os.path.join('paper/corpus', p['extracted_to'], p['scan_root']))
    # failroute 的 file 字段已是相对仓根（cwd）的路径，直接 abspath 即可。
    # 早期版本在此处又拼了一次 scan_root，导致索引全部落空、重叠静默为 0。
    fr = []
    missing = 0
    with open(f"paper/scan/{p['name']}.jsonl", encoding='utf-8') as fh:
        for line in fh:
            d = json.loads(line)
            f = os.path.abspath(d['file'])
            if not os.path.exists(f):
                missing += 1
            fr.append((f, d['lineno'], d.get('rule') or d.get('mode')))
    assert missing == 0, f"{p['name']}: {missing} finding 路径不存在，匹配不可信"

    fr_index = defaultdict(set)
    for f, ln, rl in fr:
        fr_index[f].add(ln)

    entry = {'name': p['name'], 'version': p['version'], 'scan_root': root,
             'failroute_findings': len(fr), 'linters': {}}
    print(f"\n=== {p['name']} v{p['version']}  failroute={len(fr)} ===")
    grand['failroute'] += len(fr)

    for lname, fn, sel in LINTERS:
        t0 = time.time()
        try:
            hits = fn(root)
        except subprocess.TimeoutExpired:  # failroute: ignore
            # Intentional: None is a sentinel meaning "this linter timed out", and the
            # caller below branches on `hits is None` and records the timeout in the
            # output JSON. The failure is reported, not discarded.
            hits = None
        dt = round(time.time() - t0, 1)
        if hits is None:
            entry['linters'][lname] = {'status': 'timeout', 'select': sel}
            print(f"  {lname:<16} TIMEOUT ({dt}s)")
            continue
        matched = set()
        for f, ln, code in hits:
            for cand in fr_index.get(f, ()):
                if abs(cand - ln) <= TOL:
                    matched.add((f, cand))
        entry['linters'][lname] = {'status': 'ok', 'select': sel, 'findings': len(hits),
                                   'matched_failroute': len(matched), 'seconds': dt,
                                   'codes': dict(Counter(c for _, _, c in hits))}
        grand[lname] += len(hits)
        grand_match[lname] += len(matched)
        for f, ln, rl in fr:
            if (f, ln) in matched:
                grand_rule_match[lname][rl] += 1
        print(f"  {lname:<16} findings={len(hits):<5} matched={len(matched):<5} ({dt}s)")
    report['packages'].append(entry)

report['totals'] = {'failroute': grand['failroute'],
                    **{k: {'findings': grand[k], 'matched_failroute': grand_match[k],
                           'matched_by_rule': dict(grand_rule_match[k])}
                       for k, _, _ in LINTERS}}
open('bench/corpus-linter-comparison.json', 'w', encoding='utf-8').write(
    json.dumps(report, ensure_ascii=False, indent=2))
print("\n" + "=" * 72)
print(f"failroute 总发现: {grand['failroute']}")
for k, _, _ in LINTERS:
    print(f"  {k:<16} findings={grand[k]:<5} 能碰及 failroute 发现={grand_match[k]}")
print("\nwrote bench/corpus-linter-comparison.json")
