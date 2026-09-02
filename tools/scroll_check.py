#!/usr/bin/env python3
"""Кто пишет в порт $03. Порт $03 — это и выбор ряда клавиатуры, и РЕГИСТР ВЕРТИКАЛЬНОГО СКРОЛЛА:
запись вне кадрового гасящего сдвигает картинку (экран подёргивается). Печатает функции,
из которых идёт запись, и долю записей вне обработчика прерывания.
  python3 tools/scroll_check.py [--start=X,Y] [--frames=200]"""
import sys, pathlib, re, bisect, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FRAMES=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'200'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
syms={}
for line in open('build/ianna_vec.lst',encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    i=bisect.bisect_right(addrs,pc)-1
    return names[i] if i>=0 else '?'
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=[]; cpu=rv.make_cpu(keys)
if START: rv.START=START
rv.start_game(cpu,keys,sym)
ISR_LO=sym['vec_isr']; ISR_HI=sym.get('get_joystick',ISR_LO+0x400)
hits=collections.Counter()
base=cpu.out_handler
def out(p,v):
    if p==0x03: hits[fn(cpu.pc)]+=1
    return base(p,v)
cpu.out_handler=out
keys.append("right")
for _ in range(FRAMES):
    while not cpu.halted: cpu.step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
tot=sum(hits.values())
print(f'записей в порт $03: {tot}')
for f,n in hits.most_common(10): print(f'  {f}: {n}')
