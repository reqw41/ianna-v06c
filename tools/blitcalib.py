#!/usr/bin/env python3
"""КАЛИБРОВКА ЦЕН БЮДЖЕТА DI: реальные такты между соседними проверками бюджета против цены.

Бюджет на счётчике 0 ВИ53 читает НАСТОЯЩУЮ фазу кадра, поэтому цена (A при call vec_budget)
обязана покрывать ровно то, что произойдёт ДО СЛЕДУЮЩЕЙ проверки: сам блит плюс обвязка обхода.
Здесь на детерминированном прогоне (как cmpbuild, --norand) для каждой цены собирается
распределение реально потраченных тактов (в единицах 256) — медиана / p90 / максимум.
После ускорения блиттера цены нужно перечислить по этой таблице (см. комментарии calib в
src/vec/vec_vdp.asm): занизишь — потеряешь прерывание, завысишь — лишний halt.

  python3 tools/blitcalib.py <rom> <lst> <edd> X,Y <тиков> [--rand]
"""
import sys, os, re, bisect, pathlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
src = open('tools/profile_vec.py').read()
exec(src[src.index('# Такты ВЕКТОРА'):src.index('keys = []')])
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100 + len(rom)] = rom; cpu.pc = 0x100
rv.patch_menu(cpu)
if '--rand' not in OPTS:
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
keys.append('right')

BUD = sym['vec_budget']; RS = sym['RunScripts']; FC = sym['FrameCounter']
mem = cpu.mem; step = cpu.step; cyc = 0; ticks = 0
prev = None                      # (цена, такты на входе)
stat = collections.defaultdict(list)
while ticks < N:
    while not cpu.halted:
        pc = cpu.pc
        if pc == BUD:
            if prev is not None: stat[prev[0]].append((cyc - prev[1]) / 256)
            prev = (cpu.a, cyc)
        if pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        cyc += CYC[mem[pc] if pc < 0x8000 else cpu.rb(pc)]
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
print(f'сцена {ST}, {N} тиков. Цена -> реально потрачено до следующей проверки (ед. 256 тактов):')
print(f'{"цена":>5s} {"вызовов":>8s} {"медиана":>8s} {"p90":>6s} {"макс":>6s}  вердикт')
for c, v in sorted(stat.items()):
    v.sort(); n = len(v)
    med, p90, mx = v[n // 2], v[int(n * .9)], v[-1]
    verdict = 'ЗАНИЖЕНА' if p90 > c else ('завышена' if p90 < c - 2 else 'в норме')
    print(f'{c:5d} {n:8d} {med:8.1f} {p90:6.1f} {mx:6.1f}  {verdict}')
