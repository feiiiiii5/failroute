#!/usr/bin/env python3
"""计算四个句法 linter 的并集覆盖，得出真正的 failroute-only 数。

诚实口径：不要只对照 ruff。pylint 的 W0702/W0703 覆盖面远大于 ruff S110/S112。

F 批改动（2026-09-01）：
- 解释器不再硬编码相对路径 `.venv/bin/python`：优先环境变量 FAILROUTE_PY，
  其次仓内 .venv 的绝对路径，最后 sys.executable；找不到直接报错退出。
- pylint 超时 900s → 1800s（上一批撞超时，见工作计划 §1.5-⑨）；超时/解析失败一律抛出，不静默吞掉。
- findings 来源可参数化（--findings-dir），输出路径可参数化（--out），
  于是同一套口径既能复现冻结基线（paper/scan），也能算修复后的新基线。
- --with-semgrep 把自写 semgrep 规则作为第 5 个工具并入（需要 SEMGREP 指向可用二进制，默认 /tmp/sgvenv/bin/semgrep）。

用法：cd 新项目-failroute && .venv/bin/python tools/coverage_union.py [--findings-dir paper/scan] [--out ...] [--with-semgrep]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)


def _resolve_python() -> str:
    env = os.environ.get('FAILROUTE_PY')
    if env:
        if not os.path.exists(env):
            sys.exit(f'error: FAILROUTE_PY points to a missing interpreter: {env}')
        return env
    venv_py = os.path.abspath('.venv/bin/python')
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable


PY = _resolve_python()
SG = os.environ.get('SEMGREP', '/tmp/sgvenv/bin/semgrep')
RULES = 'tools/semgrep-rules/exception-handling.yaml'
LOCK = json.load(open('paper/corpus-lock.json', encoding='utf-8'))
TOL = 1
# S batch (baseline fairness, review item M4): the rule set ruff is invoked with is
# a parameter, not a literal, so the symmetric variant can be measured with the
# *same* co-location implementation (TOL, file resolution, union logic) instead of
# a second one. The default is unchanged, so every existing caller and every
# committed artifact reproduces byte-for-byte apart from generated_at_utc.
RUFF_SELECT = 'S110,S112'

def sh(c, t=900):
    r = subprocess.run(c, capture_output=True, text=True, timeout=t)
    # 🔴 L2 fix (2026-09-02): a linter that FINDS issues exits non-zero *with*
    # stdout; a linter that failed to run (missing module / crash) exits non-zero
    # with EMPTY stdout. The old one-liner returned stdout unconditionally and
    # every caller did json.loads(o or '[]'), so a missing linter silently became
    # the empty set -> union_covered=0 -> "failroute-only 100%", exit 0. That is
    # the exact silent-failure mode this paper studies. Treat empty-output-on-error
    # as fatal. (_preflight_linters below catches the common missing-package case
    # first, with a better message; this is the defence-in-depth net.)
    if r.returncode != 0 and not (r.stdout or '').strip():
        sys.exit('error: a linter run failed with empty stdout (rc=%d): %s\nstderr: %s'
                 % (r.returncode, ' '.join(str(x) for x in c[:5]), (r.stderr or '').strip()[:400]))
    return r

def ruff(r):
    o = sh([PY,'-m','ruff','check','--no-cache','--isolated','--select',RUFF_SELECT,'--output-format','json',r]).stdout
    return [(os.path.abspath(d['filename']), d['location']['row']) for d in json.loads(o or '[]')]
def bandit(r):
    o = sh([PY,'-m','bandit','-r',r,'-f','json','-t','B110,B112','-q']).stdout
    return [(os.path.abspath(d['filename']), d['line_number']) for d in json.loads(o or '{}').get('results',[])]
def pylint(r):
    o = sh([PY,'-m','pylint','--disable=all','--enable=W0702,W0703,W0705,W0706',
            '--output-format=json','--persistent=n','--jobs=4',r], t=1800).stdout
    return [(os.path.abspath(d['path']), d['line']) for d in json.loads(o or '[]')]
def flake8(r):
    o = sh([PY,'-m','flake8','--select','E722,B001,B017','--format','%(path)s\t%(row)d',r]).stdout
    out=[]
    dropped = 0
    for ln in (o or '').splitlines():
        a=ln.split('\t')
        if len(a)==2:
            try: out.append((os.path.abspath(a[0]), int(a[1])))
            except ValueError: dropped += 1
    if dropped:
        print(f'  [warn] {dropped} unparseable row(s) dropped', file=__import__('sys').stderr)
    return out

TOOLS=[('ruff',ruff),('bandit',bandit),('pylint',pylint),('flake8+bugbear',flake8)]


# 🔴 L2 (2026-09-02): the four linters run as `PY -m <tool>`. Probe each with
# --version, which never scans anything -- so a non-zero exit unambiguously means
# "unusable", unlike a real run whose non-zero exit merely means "found issues".
# flake8 additionally needs the flake8-bugbear plugin loaded, or the B001/B017
# selects silently match nothing (a *partial* silent-zero that under-counts), so
# check its --version banner advertises bugbear.
LINTER_SPECS = [
    ('ruff', ['ruff', '--version'], None),
    ('bandit', ['bandit', '--version'], None),
    ('pylint', ['pylint', '--version'], None),
    ('flake8', ['flake8', '--version'], 'bugbear'),
]


def _preflight_linters():
    """Fail loudly, naming every missing package, if any linter cannot run under PY."""
    missing = []
    for name, vargs, requires in LINTER_SPECS:
        r = subprocess.run([PY, '-m'] + vargs, capture_output=True, text=True)
        out = (r.stdout or '') + (r.stderr or '')
        if r.returncode != 0:
            missing.append(name)
        elif requires and requires not in out:
            missing.append('flake8-bugbear')
    if missing:
        sys.exit(
            'error: coverage_union.py refuses to run -- the following required linter '
            'package(s) are missing or unusable under the resolved interpreter (%s):\n  - %s\n'
            'Install the pinned set that reproduces the paper numbers with:\n'
            "  pip install '.[paper]'   (or: pip install ruff==0.16.5 bandit==1.9.4 "
            'pylint==4.0.8 flake8==7.3.0 flake8-bugbear)\n'
            'A silent empty result here would falsely report failroute-only = 100%%.'
            % (PY, '\n  - '.join(missing))
        )


def semgrep(r):
    o = sh([SG,'--metrics=off','--disable-version-check','--no-git-ignore','--json',
            '-f',RULES,r], t=1800).stdout
    d = json.loads(o or '{}')
    return [(os.path.abspath(x['path']), x['start']['line']) for x in d.get('results',[])]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--findings-dir', default='paper/scan',
                    help='per-package findings jsonl directory (default: frozen paper/scan)')
parser.add_argument('--out', default='bench/corpus-coverage-union.json',
                    help='where to write the union summary JSON')
parser.add_argument('--with-semgrep', action='store_true',
                    help='add the hand-written semgrep rules as a 5th tool')
parser.add_argument('--ruff-select', default='S110,S112',
                    help="rule set ruff is invoked with (default: the paper's S110,S112). "
                         "S batch: pass 'S110,S112,BLE001' to give ruff its broad-except "
                         "rule, symmetric to the pylint W0703 the other baselines already get.")
args = parser.parse_args()
RUFF_SELECT = args.ruff_select
if args.with_semgrep:
    if not os.path.exists(SG):
        sys.exit(f'error: semgrep binary missing: {SG} (set SEMGREP)')
    if not os.path.isfile(RULES):
        sys.exit(f'error: semgrep rules missing: {RULES}')
    TOOLS.append(('semgrep', semgrep))
if not os.path.isdir(args.findings_dir):
    sys.exit(f'error: findings dir missing: {args.findings_dir}')
_preflight_linters()

per_tool=defaultdict(Counter); union_by_rule=Counter(); total_by_rule=Counter()
union4_by_rule=Counter(); union5_by_rule=Counter()
covered_total=0; covered_total_4=0; covered_total_5=0; fr_total=0; rows=[]

for p in LOCK['packages']:
    root=os.path.normpath(os.path.join('paper/corpus',p['extracted_to'],p['scan_root']))
    fr=[]
    findings_path = os.path.join(args.findings_dir, f"{p['name']}.jsonl")
    if not os.path.isfile(findings_path):
        sys.exit(f'error: findings file missing for {p["name"]}: {findings_path}')
    for line in open(findings_path, encoding='utf-8'):
        d=json.loads(line); raw=d['file']
        # 🔴 L2: the scan jsonl store repo-relative paths (paper/corpus/...), so the
        # artifact is portable to any clone; resolve against ROOT explicitly rather
        # than relying on the chdir above. Legacy absolute paths are honoured as-is.
        # A missing corpus file now fails with instructions instead of a bare assert.
        f=os.path.abspath(raw if os.path.isabs(raw) else os.path.join(ROOT,raw))
        if not os.path.exists(f):
            sys.exit('error: corpus file not found: %s\n  (finding %s in %s). The extracted '
                     'corpus under paper/corpus/ is not committed to git; run '
                     '`python tools/fetch_corpus.py` first.' % (f, d.get('id'), findings_path))
        fr.append((f,d['lineno'],d['rule']))
    fr_total+=len(fr)
    for _,_,rl in fr: total_by_rule[rl]+=1
    hits={n:set(fn(root)) for n,fn in TOOLS}
    idx={n:defaultdict(set) for n in hits}
    for n,hs in hits.items():
        for f,l in hs: idx[n][f].add(l)
    cov=0
    for f,l,rl in fr:
        tools_hit=[n for n in hits if any(abs(c-l)<=TOL for c in idx[n].get(f,()))]
        for n in tools_hit: per_tool[n][rl]+=1
        if tools_hit: union_by_rule[rl]+=1; cov+=1
        hit4=[n for n in tools_hit if n!='semgrep']
        if hit4: union4_by_rule[rl]+=1; covered_total_4+=1
        if tools_hit: union5_by_rule[rl]+=1; covered_total_5+=1
    covered_total+=cov
    rows.append((p['name'],len(fr),cov,len(fr)-cov))
    print(f"{p['name']:<20} failroute={len(fr):<5} 被任一工具覆盖={cov:<5} failroute-only={len(fr)-cov}")

print("\n"+"="*76)
print(f"failroute 总发现        : {fr_total}")
print(f"四工具并集能覆盖        : {covered_total}  ({covered_total/fr_total*100:.1f}%)")
print(f"🟢 failroute-only       : {fr_total-covered_total}  ({(fr_total-covered_total)/fr_total*100:.1f}%)")
print("\n按规则拆解（覆盖 / 总数）：")
for rl in sorted(total_by_rule,key=lambda r:-total_by_rule[r]):
    c=union_by_rule[rl]; t=total_by_rule[rl]
    print(f"  {rl:<20} {c:>4}/{t:<5} 被覆盖 {c/t*100:>5.1f}%   → failroute-only {t-c}")
print("\n各工具单独覆盖到的 failroute 发现（按规则）：")
for n,_ in TOOLS:
    tot=sum(per_tool[n].values())
    print(f"  {n:<16} 合计 {tot:<5} " + " ".join(f"{k}={v}" for k,v in per_tool[n].most_common()))

json.dump({'generated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
 'findings_dir':args.findings_dir,'tools':[n for n,_ in TOOLS],'ruff_select':RUFF_SELECT,
 'line_tolerance':TOL,'failroute_total':fr_total,'union_covered':covered_total,
 'failroute_only':fr_total-covered_total,
 'union_covered_4tool_recheck':covered_total_4,
 'union_covered_5tool':covered_total_5,
 'by_rule':{r:{'total':total_by_rule[r],'covered':union_by_rule[r],
               'covered_4':union4_by_rule[r],'covered_5':union5_by_rule[r],
               'only':total_by_rule[r]-union_by_rule[r]} for r in total_by_rule},
 'per_tool_by_rule':{n:dict(per_tool[n]) for n,_ in TOOLS},
 'per_package':[{'name':a,'failroute':b,'covered':c,'only':d} for a,b,c,d in rows]},
 open(args.out,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(f"\nwrote {args.out}")
