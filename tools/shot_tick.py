#!/usr/bin/env python3
"""Снимок экрана после N игровых ТИКОВ (не кадров) — чтобы сравнивать сборки разной скорости.
  python3 tools/shot_tick.py X,Y выходной_тег [клавиша] [--ticks=20] [--fixrand]
--fixrand подменяет FrameCounter номером тика: логика перестаёт зависеть от скорости сборки
(враги ходят по случайности, завязанной на счётчик кадров), и кадры двух сборок сравнимы."""
import sys, pathlib
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]
N=int(next((a[8:] for a in sys.argv[1:] if a.startswith('--ticks=')),'20'))
START=tuple(int(v) for v in ARGS[0].split(',')); TAG=ARGS[1]
KEY=ARGS[2] if len(ARGS)>2 else None
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=set(); cpu=rv.make_cpu(keys)
rv.START=START
rv.start_game(cpu,keys,sym)
if KEY: keys.add(KEY)
RS=sym['RunScripts']; ticks=0
FIX='--fixrand' in sys.argv or '--fixrand' in ARGS
FC=sym['FrameCounter']
while ticks<N:
    while not cpu.halted:
        if cpu.pc==RS:
            ticks+=1
            if FIX: cpu.mem[FC]=ticks&0xFF; cpu.mem[FC+1]=0
        cpu.step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
pal=list(cpu.mem[sym['vec_palette']:sym['vec_palette']+16])
out=str(pathlib.Path('/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad')/f'{TAG}.png')
rv.render(bytes(cpu.mem[0x8000:0x10000]), pal, out)
print(out)
