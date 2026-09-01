#!/usr/bin/env python3
"""Как часто у спрайтов меняется кадр: от этого зависит окупаемость кеша развёрнутых (зеркальных)
кадров. Печатает по каждому слоту вывода долю тиков, в которых адрес кадра отличался от прошлого.
  python3 tools/spr_freq.py [--start=X,Y] [--frames=300]"""
import sys, pathlib, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FRAMES=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'300'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=set(); cpu=rv.make_cpu(keys)
if START: rv.START=START
rv.start_game(cpu,keys,sym)
DS=sym['drawSprite']; RS=sym['RunScripts']
SRC=sym['vec_spr_src']; DIR=sym['vec_spr_dir']
mem=cpu.mem
cur=[]; ticks=[]
step=cpu.step
for _ in range(FRAMES):
    while not cpu.halted:
        pc=cpu.pc
        if pc==RS:
            if cur: ticks.append(cur)
            cur=[]
        if pc==DS:
            cur.append((mem[SRC]|(mem[SRC+1]<<8), mem[DIR], mem[sym['vec_spr_port']]))
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
print(f'тиков с выводом: {len(ticks)}, спрайтов за тик: {sum(len(t) for t in ticks)/max(len(ticks),1):.1f}')
nslots=max((len(t) for t in ticks), default=0)
for s in range(nslots):
    seq=[t[s] for t in ticks if len(t)>s]
    if len(seq)<2: continue
    ch=sum(1 for a,b in zip(seq,seq[1:]) if a[0]!=b[0])
    mir=sum(1 for a in seq if a[1])
    print(f'  слот {s}: кадр менялся в {ch}/{len(seq)-1} тиков ({ch/(len(seq)-1)*100:.0f} %), '
          f'зеркальных {mir/len(seq)*100:.0f} %, разных кадров {len(set(a[0] for a in seq))}')
    frames=sorted({(a[2],a[0]) for a in seq})
    print('     кадры (порт, адрес):', ' '.join(f'{p:02X}:{a:04X}' for p,a in frames[:20]))
