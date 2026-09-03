#!/usr/bin/env python3
"""Дифференциальный тест двухплоскостного (четырёхцветного) блита в СЛОТ ПУЛА.

На каждом вызове drawSprite_pool с банком в двух плоскостях снимает вход (кадр в квазидиске,
колонка, нижняя строка, высота, направление, таблица слотов) и содержимое пула ДО, считает
ожидаемый пул моделью на Python и сверяет с тем, что оставил блит. Расхождение печатается
с адресом и обеими версиями байта.

Модель (см. build_edd.sprite_frame_bytes_2p и vec_vdp.b2p_row): строка кадра — три байта
[плоскость 2, маска, плоскость 3]; плоскости 0 и 1 только гасятся маской. Слот супертайла —
128 Б: плоскость p по смещению p*32, внутри — (cx&1)*16 + (y&15).

  python3 tools/b2pmodel.py <rom> <lst> <edd> X,Y <тиков> [--yodd]

--yodd делает y спрайтов нечётным (см. tools/poolstat.py): тогда сегменты пула получаются
нечётной длины и пара строк рвётся границей супертайла — ветка b2p_split/b2pm_split."""
import sys, os, pathlib
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])
YODD = '--yodd' in OPTS
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100; rv.patch_menu(cpu)
a = sym['random']; rd = sym['randData']
cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
keys.append('right')
RS = sym['RunScripts']; FC = sym['FrameCounter']; mem = cpu.mem; step = cpu.step
DSP = sym['drawSprite_pool']; LEAVE = sym['vec_stk_leave']; PB = sym['vec_pool_begin']
SPD = sym['SPDATA']; TAB = sym['vec_slot_tab']
V = {n: sym[n] for n in ('vec_spr_src', 'vec_spr_port', 'vec_spr_cx', 'vec_spr_ybot',
                         'vec_spr_ny', 'vec_spr_dir', 'vec_spr_skip2')}
REV = [int(f'{b:08b}'[::-1], 2) for b in range(256)]
POOL = 0xA000

def kvaz(page, addr):
    return page * 65536 + addr

def model(st, pool):
    """Ожидаемое содержимое пула после блита. pool — bytearray страницы 3 (64К), правится на месте."""
    src, port, cx, ybot, ny, dr, skip2, tab = st
    spage = (port >> 2) & 3
    pos = src
    cols = [cx + 2, cx + 1, cx] if dr else [cx, cx + 1, cx + 2]
    for ceff in cols:
        for i in range(ny):
            y = ybot - i
            b0, b1, b2 = (cpu.kvaz[kvaz(spage, pos)], cpu.kvaz[kvaz(spage, pos + 1)],
                          cpu.kvaz[kvaz(spage, pos + 2)])
            pos += 3
            if dr: b0, b1, b2 = REV[b0], REV[b1], REV[b2]
            slot = tab[((y >> 4) << 4) | ((ceff >> 1) & 15)]
            base = POOL + slot * 128 + (ceff & 1) * 16 + (y & 15)
            pool[base] &= b1
            pool[base + 32] &= b1
            pool[base + 64] = (pool[base + 64] & b1) | b0
            pool[base + 96] = (pool[base + 96] & b1) | b2
        pos += skip2
    return pool

bad = 0; checked = 0; splits = 0; ticks = 0; pend = None
while ticks < N:
    while not cpu.halted:
        pc = cpu.pc
        if pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        elif YODD and pc == PB:
            for i in range(16):
                e = SPD + i * 8
                if mem[e] | mem[e+1]: mem[e+4] |= 1
        elif YODD and pc == sym['drawSprite']: cpu.c |= 1
        elif pc == DSP and (mem[V['vec_spr_port']] & 1):
            st = (mem[V['vec_spr_src']] | (mem[V['vec_spr_src'] + 1] << 8),
                  mem[V['vec_spr_port']], mem[V['vec_spr_cx']], mem[V['vec_spr_ybot']],
                  mem[V['vec_spr_ny']], mem[V['vec_spr_dir']], mem[V['vec_spr_skip2']],
                  bytes(mem[TAB:TAB + 256]))
            pend = (st, bytearray(cpu.kvaz[3 * 65536:4 * 65536]))
        elif pc == LEAVE and pend is not None:
            st, before = pend; pend = None
            exp = model(st, before)
            got = cpu.kvaz[3 * 65536:4 * 65536]
            checked += 1
            for k in range(POOL, POOL + 80 * 128):
                if exp[k] != got[k]:
                    bad += 1
                    if bad <= 5:
                        print(f'  РАСХОЖДЕНИЕ ${k:04X}: модель {exp[k]:02X}, блит {got[k]:02X} '
                              f'(cx={st[2]} ybot={st[3]} ny={st[4]} dir={st[5]})')
                    break
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
r = ' (--yodd)' if YODD else ''
print(f'{N} тиков{r}: сверено двухплоскостных блитов в пул {checked}, расхождений {bad}')
sys.exit(1 if bad or not checked else 0)
