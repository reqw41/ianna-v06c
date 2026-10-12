#!/usr/bin/env python3
"""Оценка идеи «перерисовывать только реально изменившееся»: сколько стайлов попадает в грязные по ЦЕПОЧКЕ
(MarkOverlappingSprites помечает задетый спрайт целиком и инвалидирует все тайлы под ним, рекурсивно),
а сколько — по первичным причинам (сам спрайт сдвинулся/сменил кадр, анимация тайла).
  python3 tools/chain_est.py <rom> <lst> <edd> X,Y [--route=pace|fight|none] [--ticks=60] [--pos=x,y]
Первичный стайл обязан быть перерисован; цепной — только потому, что задет соседний спрайт."""
import sys, os, pathlib
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]; A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST=A[:4]; os.environ['IANNA_EDD']=EDD
ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'pace'); NT=int(next((o[8:] for o in OPTS if o.startswith('--ticks=')),'60'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sym=rv.load_syms(pathlib.Path(LST)); keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu, LST)
rv.START=tuple(int(v) for v in ST.split(',')); rv.STEP_BUDGET=400000; rv.start_game(cpu,keys,sym)
mem=cpu.mem; RS=sym['RunScripts']; IT=sym['InvalidateTiles']; IS=sym['InvalidateSTiles']; MOS=sym['MarkOverlappingSprites']; EPP=sym['ENTITY_PLAYER_POINTER']
SCEN={'fight':[(['fire','right'],10),([],6),(['fire','up'],10),([],6),(['fire','down'],10),([],6),(['fire','left'],10),([],6),(['right'],12),(['left'],12)],
      'pace':[(['right'],30),(['left'],30)],'none':[([],10)]}[ROUTE]
def skeys(f):
    f%=sum(n for _,n in SCEN)
    for k,n in SCEN:
        if f<n: return k
        f-=n
def stiles(b,c,d,e):   # символы 8px -> стайлы 16px, поле 16x10
    return {(x,y) for x in range(b//2,min(16,(b+d+1)//2)) for y in range(c//2,min(10,(c+e+1)//2))}
import re,bisect,collections
_s={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: _s.setdefault(int(m.group(1),16),m.group(2))
_a=sorted(_s); _n=[_s[a] for a in _a]
def fn(pc):
    k=bisect.bisect_right(_a,pc)-1; return _n[k] if k>=0 else '?'
callers=collections.Counter()
gran=[]; HC=set(); Q=set(); det=[]; VPB=sym['vec_pool_begin']; SPD=sym['SPDATA']; prev={}; same=[]; red=[]; area_same=[]; area=[]
ticks=0; fr=0; mos_sp=None; P=set(); T=set(); rows=[]; e0=None; spr_n=[]
while ticks<NT:
    keys[:]=skeys(fr)
    n=0
    while not cpu.halted and n<400000:
        pc=cpu.pc
        if pc==RS:
            if e0 is None: e0=mem[EPP+4]
            elif mem[EPP+4]<e0: mem[EPP+4]=e0
            if ticks: rows.append((len(P),len(T))); gran.append((len(T),len(HC),len(Q)))
            HC=set(); Q=set(); P=set(); T=set(); ticks+=1; mem[sym['FrameCounter']]=ticks&0xFF; mem[sym['FrameCounter']+1]=0
        elif pc==VPB:
            ns=0; nr=0; a_s=0; a_r=0
            for i in range(16):
                e=bytes(mem[SPD+i*8:SPD+i*8+8])
                if e[0]|e[1]:
                    if e[7]:
                        nr+=1; a_r+=e[5]*e[6]
                        if prev.get(i)==e[:7]:
                            ns+=1; a_s+=e[5]*e[6]
                            st_=stiles(e[3]//8,e[4]//8,e[5],e[6]); inP=len(st_&P); det.append((i,e[3],e[4],e[5],e[6],len(st_),inP))
                    prev[i]=e[:7]
                else: prev.pop(i,None)
            red.append(nr); same.append(ns); area.append(a_r); area_same.append(a_s)
        elif pc==MOS and mos_sp is None: mos_sp=cpu.sp
        elif pc==IT:
            ra=mem[cpu.sp]|mem[cpu.sp+1]<<8; callers[(fn(ra),mos_sp is not None)]+=1
            s=stiles(cpu.b,cpu.c,cpu.d,cpu.e); T|=s
            HC|={(x,y) for x in range(cpu.b,min(32,cpu.b+cpu.d)) for y in range(cpu.c//2,min(10,(cpu.c+cpu.e+1)//2))}
            Q|={(x,y) for x in range(cpu.b,min(32,cpu.b+cpu.d)) for y in range(cpu.c,min(20,cpu.c+cpu.e))}
            if mos_sp is None: P|=s
        elif pc==IS and mos_sp is None:
            s={(x,y) for x in range(cpu.b,min(16,cpu.b+cpu.d)) for y in range(cpu.c,min(10,cpu.c+cpu.e))}; T|=s; P|=s
        cpu.step(); n+=1
        if mos_sp is not None and cpu.sp>mos_sp: mos_sp=None
    cpu.halted=False; fr+=1
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
rows=rows[2:]
k=len(red)-len(rows); red=red[k:]; same=same[k:]; area=area[k:]; area_same=area_same[k:]
p=sum(a for a,_ in rows)/len(rows); t=sum(b for _,b in rows)/len(rows)
print(f'{ST} {ROUTE}: спрайтов на перерисовку за тик {sum(red)/len(red):.1f}, из них не изменились {sum(same)/len(same):.1f}; площадь (символы 8x8) {sum(area)/len(area):.0f}, из неё у неизменившихся {sum(area_same)/len(area):.0f}')
print(f'{ST} {ROUTE}: тиков {len(rows)}; грязных стайлов на тик: всего {t:.1f}, первичных {p:.1f}, по цепочке {t-p:.1f} ({(t-p)/max(t,.01)*100:.0f} %); '
      f'тиков, где цепочка что-то добавила: {sum(1 for a,b in rows if b>a)}; макс. всего {max(b for _,b in rows)}, первичных в том же тике {max(rows,key=lambda r:r[1])[0]}')

import collections
c=collections.Counter((d[0],d[3],d[4]) for d in det)
print('  неизменившиеся перерисованные: (спрайт, ширина, высота в символах): раз', dict(c))
if det: print('  в среднем стайлов под таким спрайтом %.1f, из них первично грязных %.1f'%(sum(d[5] for d in det)/len(det), sum(d[6] for d in det)/len(det)))
all_spr=collections.Counter()
print('  кто зовёт InvalidateTiles (функция, внутри цепочки): раз', dict(callers.most_common(12)))

g=gran[2:]; s=sum(a for a,_,_ in g); h=sum(b for _,b,_ in g); q=sum(c for _,_,c in g)
print(f'  гранулярность: стайлов 16x16 на тик {s/len(g):.1f}; колонок 8x16 нужно {h/len(g):.1f} из {2*s/len(g):.1f} ({h/(2*s)*100:.0f} %); клеток 8x8 нужно {q/len(g):.1f} из {4*s/len(g):.1f} ({q/(4*s)*100:.0f} %)')
