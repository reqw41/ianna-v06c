#!/usr/bin/env python3
"""Статистика пула и палитра на детерминированном стенде (как cmpbuild --norand).

Печатает:
  - vec_palette (16 байт) после N тиков — гейт «палитра совпала»;
  - максимум занятых слотов пула за тик (vec_slot_next на входе в vec_pool_flush);
  - сколько тиков ушло в прямой режим (переполнение пула или запрет);
  - сколько блитов спрайта пошло в пул / прямо в VRAM (по входам drawSprite_pool,
    dsp_mirror, ds_dir4, vec_blit2, vec_blit2m).

  python3 tools/poolstat.py <rom> <lst> <edd> X,Y <тиков> [--rand] [--yodd]

--yodd делает Y КАЖДОГО спрайта нечётным (y |= 1 в списке SPDATA на входе в vec_pool_begin —
до разметки слотов, так что и слоты, и рисование видят одно и то же). В игре все спрайты стоят
на чётных строках, поэтому ybot всегда нечётный, сегменты пула выходят чётной длины и пара строк
двухплоскостного спрайта никогда не разрывается границей супертайла. Ключ поднимает эту ветку
(b2p_split/b2pm_split). Проверка: один и тот же ROM с набором в прямом режиме (POOL_OFF=1)
и с набором в режиме пула обязаны дать один хэш VRAM."""
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
for name in ('drawSprite_pool', 'dsp_mirror', 'ds_dir4', 'ds_dir4m', 'dsm_prep',
             'vec_blit2', 'vec_blit2m', 'ds_direct',
             'b2p_row', 'b2pm_row', 'b2p_split', 'b2pm_split'):
    if name in sym: PATHS[sym[name]] = name
YODD = '--yodd' in OPTS; PB = sym['vec_pool_begin']; SPD = sym['SPDATA']; DS = sym['drawSprite']
cnt = collections.Counter(); maxslots = 0; direct_ticks = 0; ticks = 0
while ticks < N:
    while not cpu.halted:
        pc = cpu.pc
        if pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        elif YODD and pc == PB:                 # y спрайтов -> нечётный (ybot чётный): и в списке
            for i in range(16):                 # для разметки слотов, и в самом вызове блита (ниже),
                e = SPD + i * 8                 # иначе слоты и рисование разъедутся
                if mem[e] | mem[e+1]: mem[e+4] |= 1
        elif YODD and pc == DS: cpu.c |= 1
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
