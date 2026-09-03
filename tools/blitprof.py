#!/usr/bin/env python3
"""Разбор стоимости блиттера: такты по МЕТКАМ (а не по функциям) и число входов в метку.
Детерминированный стенд как в cmpbuild/abcyc (--norand по умолчанию).
  python3 tools/blitprof.py <rom> <lst> <edd> X,Y <тиков> [--top=N] [--pref=dt_,dsp_]
Печатает: такты/тик всего, затем по каждой метке — такты/тик, доля, входов/тик, тактов на вход."""
import sys, os, re, bisect, pathlib, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST,N=A[0],A[1],A[2],A[3],int(A[4])
TOP=int(next((o[6:] for o in OPTS if o.startswith('--top=')),'40'))
PREF=next((o[7:] for o in OPTS if o.startswith('--pref=')),None)
PREF=tuple(PREF.split(',')) if PREF else None
os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
rv.STEP_BUDGET=400000
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    # СТРОГО: метка идёт сразу за адресом (только пробелы). Свободная регулярка ловит слова с
    # двоеточием из КОММЕНТАРИЕВ («SPR3CLR: плоскость 3 только чистим») и вешает на них чужие такты.
    m=re.match(r'([0-9A-F]{4}):\s+([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
lab={a:syms[a] for a in addrs}
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
if '--rand' not in OPTS:
    a=sym['random']; rd=sym['randData']
    cpu.mem[a:a+9]=bytes((0x3A,rd&0xFF,rd>>8,0xC6,0x4D,0x32,rd&0xFF,rd>>8,0xC9))
rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step; mem=cpu.mem
tot=0; cyc=collections.Counter(); hits=collections.Counter()
while ticks<N:
    while not cpu.halted:
        pc=cpu.pc; w=CYC[mem[pc]]; tot+=w
        nm=fn(pc); cyc[nm]+=w
        if pc in lab: hits[lab[pc]]+=1
        if pc==RS: ticks+=1; mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
print(f'{ST}: {N} тиков, всего {tot} тактов, на тик {tot/N:.0f}')
items=[(v,k) for k,v in cyc.items() if not PREF or k.startswith(PREF)]
items.sort(reverse=True)
print(f'{"метка":26s} {"такт/тик":>9s} {"%":>6s} {"вход/тик":>9s} {"такт/вход":>10s}')
for v,k in items[:TOP]:
    h=hits[k]
    print(f'{k:26s} {v/N:9.0f} {v/tot*100:6.2f} {h/N:9.1f} {(v/h if h else 0):10.1f}')
if PREF:
    s=sum(v for v,_ in items); print(f'ИТОГО по префиксам: {s/N:.0f} такт/тик ({s/tot*100:.1f} %)')
