#!/usr/bin/env python3
"""计算四个句法 linter 的并集覆盖，得出真正的 failroute-only 数。

诚实口径：不要只对照 ruff。pylint 的 W0702/W0703 覆盖面远大于 ruff S110/S112。
用法：cd 新项目-failroute && .venv/bin/python tools/coverage_union.py
"""
import json
import os
import subprocess
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
PY = '.venv/bin/python'
LOCK = json.load(open('paper/corpus-lock.json', encoding='utf-8'))
TOL = 1

def sh(c, t=900): return subprocess.run(c, capture_output=True, text=True, timeout=t)

def ruff(r):
    o = sh([PY,'-m','ruff','check','--no-cache','--isolated','--select','S110,S112','--output-format','json',r]).stdout
    return [(os.path.abspath(d['filename']), d['location']['row']) for d in json.loads(o or '[]')]
def bandit(r):
    o = sh([PY,'-m','bandit','-r',r,'-f','json','-t','B110,B112','-q']).stdout
    return [(os.path.abspath(d['filename']), d['line_number']) for d in json.loads(o or '{}').get('results',[])]
def pylint(r):
    o = sh([PY,'-m','pylint','--disable=all','--enable=W0702,W0703,W0705,W0706',
            '--output-format=json','--persistent=n','--jobs=4',r]).stdout
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
per_tool=defaultdict(Counter); union_by_rule=Counter(); total_by_rule=Counter()
covered_total=0; fr_total=0; rows=[]

for p in LOCK['packages']:
    root=os.path.normpath(os.path.join('paper/corpus',p['extracted_to'],p['scan_root']))
    fr=[]
    for line in open(f"paper/scan/{p['name']}.jsonl",encoding='utf-8'):
        d=json.loads(line); f=os.path.abspath(d['file'])
        assert os.path.exists(f), f
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
 'line_tolerance':TOL,'failroute_total':fr_total,'union_covered':covered_total,
 'failroute_only':fr_total-covered_total,
 'by_rule':{r:{'total':total_by_rule[r],'covered':union_by_rule[r],'only':total_by_rule[r]-union_by_rule[r]} for r in total_by_rule},
 'per_tool_by_rule':{n:dict(per_tool[n]) for n,_ in TOOLS},
 'per_package':[{'name':a,'failroute':b,'covered':c,'only':d} for a,b,c,d in rows]},
 open('bench/corpus-coverage-union.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print("\nwrote bench/corpus-coverage-union.json")
