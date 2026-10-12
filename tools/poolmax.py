#!/usr/bin/env python3
"""Занятость пула слотов: максимум vec_slot_next за прогон случайной игры и число тиков выше порогов.
  python3 tools/poolmax.py <rom> <lst> <edd> X,Y|- [--frames=4000] [--seed=1]"""
import sys, os, pathlib, random, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]; A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST=A[:4]; os.environ['IANNA_EDD']=EDD
FR=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'4000')); SEED=int(next((o[7:] for o in OPTS if o.startswith('--seed=')),'1'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sym=rv.load_syms(pathlib.Path(LST)); keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
if ST!='-': rv.START=tuple(int(v) for v in ST.split(','))
rv.STEP_BUDGET=400000; rv.start_game(cpu,keys,sym)
mem=cpu.mem; PF=sym['vec_pool_flush']; SN=sym['vec_slot_next']; WT=sym.get('wait_till_read',-1); RS=sym['RunScripts']; EPP=sym['ENTITY_PLAYER_POINTER']
MOVES=[[],['left'],['right'],['up'],['down'],['fire'],['fire','left'],['fire','right'],['up','left'],['up','right'],['down','fire'],['up','fire'],['left'],['right'],['z'],['action']]
rnd=random.Random(SEED); h=collections.Counter(); left=0; wait=False; e0=None; scr=collections.Counter()
for f in range(FR):
    if not wait:
        if left<=0: keys[:]=rnd.choice(MOVES); left=rnd.randint(3,40)
        left-=1
    n=0
    while not cpu.halted and n<400000:
        pc=cpu.pc
        if pc==PF:
            v=mem[SN]; h[v]+=1
            if v>=48: scr[(mem[sym['current_levelx']],mem[sym['current_levely']],v)]+=1
        elif pc==RS:
            if wait: wait=False; keys.clear()
            if e0 is None: e0=mem[EPP+4]
            elif mem[EPP+4]<e0: mem[EPP+4]=e0
        elif pc==WT and not wait: wait=True; keys[:]=['fire']
        cpu.step(); n+=1
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
t=sum(h.values()); mx=max(h) if h else 0
print(f'{ST} seed {SEED}: сбросов {t}; макс. слотов {mx}; >=48: {sum(c for v,c in h.items() if v>=48)}; >=56: {sum(c for v,c in h.items() if v>=56)}; >=64: {sum(c for v,c in h.items() if v>=64)}; =80: {h.get(80,0)}' + (f'; где >=48: {dict(scr.most_common(4))}' if scr else ''))
