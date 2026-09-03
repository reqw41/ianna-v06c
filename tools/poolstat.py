#!/usr/bin/env python3
"""Статистика пула и палитра на детерминированном стенде (как cmpbuild --norand).

Печатает:
  - vec_palette (16 байт) после N тиков — гейт «палитра совпала»;
  - максимум занятых слотов пула за тик (vec_slot_next на входе в vec_pool_flush);
  - сколько тиков ушло в прямой режим (переполнение пула или запрет);
  - сколько блитов спрайта пошло в пул / прямо в VRAM (по входам drawSprite_pool,
    dsp_mirror, ds_dir4, vec_blit2, vec_blit2m).

  python3 tools/poolstat.py <rom> <lst> <edd> X,Y <тиков> [--rand]"""
import sys, os, re, pathlib, hashlib, collections
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])
NORAND = '--rand' not in OPTS
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100; rv.patch_menu(cpu)
if NORAND:
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
keys.append('right')
RS = sym['RunScripts']; FC = sym['FrameCounter']; mem = cpu.mem; step = cpu.step
SLOT_NEXT = sym['vec_slot_next']; POOL_ON = sym['vec_pool_on']
FLUSH = sym.get('vec_pool_flush')
# точки входа путей блита спрайта (те, что есть в этой сборке)
PATHS = {}
for name in ('drawSprite_pool', 'dsp_mirror', 'ds_dir4', 'drawSprite_mirror',
             'vec_blit2', 'vec_blit2_pool', 'b2p_mirror', 'ds_direct'):
    if name in sym: PATHS[sym[name]] = name
cnt = collections.Counter(); maxslots = 0; direct_ticks = 0; ticks = 0
while ticks < N:
    while not cpu.halted:
        pc = cpu.pc
        if pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        elif pc == FLUSH:
            if mem[POOL_ON]: maxslots = max(maxslots, mem[SLOT_NEXT])
            else: direct_ticks += 1
        elif pc in PATHS: cnt[PATHS[pc]] += 1
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
pal = bytes(mem[sym['vec_palette']:sym['vec_palette']+16])
vram = bytes(mem[0x8000:0x10000]); ent = bytes(mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
print(f'{N} тиков: VRAM {hashlib.md5(vram).hexdigest()[:8]} ENT {hashlib.md5(ent).hexdigest()[:8]} '
      f'PAL {pal.hex()}')
print(f'    слотов максимум {maxslots}, прямых тиков {direct_ticks}, пути: '
      + ', '.join(f'{k}={v}' for k, v in sorted(cnt.items())))
