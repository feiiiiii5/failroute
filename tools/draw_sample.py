#!/usr/bin/env python3
"""从钉版语料扫描结果中按（规则 × 包）分层随机抽样，供人工裁定。

用法：.venv/bin/python tools/draw_sample.py --n 80 --seed 20260831
"""
import argparse
import glob
import hashlib
import json
import os
import random

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
ap=argparse.ArgumentParser(); ap.add_argument('--n',type=int,default=80)
ap.add_argument('--seed',type=int,default=20260831)
ap.add_argument('--out',default='paper/sample.jsonl')
a=ap.parse_args()

items=[]
for f in sorted(glob.glob('paper/scan/*.jsonl')):
    for line in open(f,encoding='utf-8'):
        d=json.loads(line); items.append(d)
strata={}
for d in items: strata.setdefault((d['rule'], d['repo']), []).append(d)

# 比例分配 + 每层至少 1 条（小层全取）
rnd=random.Random(a.seed)
total=len(items); picked=[]
keys=sorted(strata, key=lambda k:(k[0],k[1]))
# 先给每层保底 1 条
for k in keys:
    picked.append((k, rnd.choice(strata[k])))
remaining=a.n-len(picked)
# 剩余按层大小比例分配
weights=[(k,len(strata[k])) for k in keys]
tot=sum(w for _,w in weights)
alloc={k:0 for k in keys}
for k,w in weights:
    alloc[k]=int(remaining*w/tot)
# 补足取整误差
while sum(alloc.values())<remaining:
    k=max(keys,key=lambda kk:len(strata[kk])-alloc[kk]-1)
    alloc[k]+=1
chosen_ids={id(x) for _,x in picked}
for k in keys:
    pool=[x for x in strata[k] if id(x) not in chosen_ids]
    take=min(alloc[k],len(pool))
    for x in rnd.sample(pool,take): picked.append((k,x))

picked=picked[:a.n]
picked.sort(key=lambda kx:(kx[0][0],kx[0][1],kx[1]['file'],kx[1]['lineno']))
with open(a.out,'w',encoding='utf-8') as fh:
    for i,(k,d) in enumerate(picked,1):
        d=dict(d); d['sample_index']=i; d['stratum']=f"{k[0]}|{k[1]}"
        fh.write(json.dumps(d,ensure_ascii=False)+"\n")
blob=open(a.out,'rb').read()
print(f"抽样 {len(picked)} 条 → {a.out}")
print(f"seed={a.seed}  sha256={hashlib.sha256(blob).hexdigest()[:32]}")
from collections import Counter

c=Counter(k[0] for k,_ in picked); cr=Counter(k[1] for k,_ in picked)
print("按规则:", dict(c)); print("按包  :", dict(cr))
