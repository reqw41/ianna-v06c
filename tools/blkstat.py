#!/usr/bin/env python3
"""Разведка «ЧЁРНЫЙ СТАЙЛ»: сколько их за тик, кто их накрывает и в каком они состоянии карты слотов.

Зачем: идея «стайл, у которого фоновый тайл чёрный (номер в vec_blk_tab), передний тайл 0, а сверху
РОВНО ОДИН спрайт — собирать композитом прямо в VRAM, минуя слот пула» окупается ровно настолько,
сколько таких стайлов набирается за тик И насколько они пригодны. Стенд считает и то, и другое:
  - какой спрайт накрывает стайл (индекс в SPDATA, банк, 2/4 плоскости, зеркальность): ГЕРОЙ
    (индекс 0) из отбора выпадает — его слоты сброс выводит списком позади луча (vpf_hero), а
    композит написал бы часть героя ещё в фазе сборки, то есть порвал бы позу;
  - состояние стайла в карте слотов ($FE — прямой в VRAM, слот — через пул) и накрытие текущими
    и ПРОШЛЫМИ прямоугольниками спрайтов (прошлое место обязано стираться при сбросе, иначе спрайт
    на кадр раздваивается).

  python3 tools/blkstat.py <rom> <lst> <edd> X,Y [прогрев=30]
Маршрут — как у proftick/measure_vec (20 тиков влево, 5 на месте, 35 удар+бег), чтобы числа
сравнивались со статьями профиля напрямую.
"""
import sys, os, pathlib, collections
ROM, LST, EDD, ST = sys.argv[1:5]
SETTLE = int(sys.argv[5]) if len(sys.argv) > 5 else 30
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100; rv.patch_menu(cpu)
a = sym['random']; rd = sym['randData']
cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv._start_done[0] = False
RS = sym['RunScripts']; FC = sym['FrameCounter']
w = rv.Warmup(sym, keys); done = False; ticks = 0
for fr in range(1500):
    c = 0
    while not cpu.halted and c < rv.STEP_BUDGET:
        pc = cpu.pc
        if not rv._start_done[0] and pc == sym['SaveCheckpoint']:
            cpu.mem[sym['current_levelx']] = rv.START[0]; cpu.mem[sym['current_levely']] = rv.START[1]
            rv._start_done[0] = True
        if w.step(pc, fr): done = True
        if pc == RS: ticks += 1; cpu.mem[FC] = ticks & 0xFF
        cpu.step(); c += 1
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
    if done: break
assert done
keys.clear()
ROUTE = [(20, ['left']), (5, []), (35, ['fire', 'left'])]
NT = sum(n for n, _ in ROUTE)
mem = cpu.mem
RIT = sym['RedrawInvTiles']; SLOT = sym['vec_slot_tab']; MAP = sym['CURRENT_SCREEN_MAP']
FG = MAP + 160; BLK = sym['vec_blk_tab']; SPD = sym['SPDATA']; PON = sym['vec_pool_on']
BANKTAB = sym['vec_bank_tab']; PREV = sym['vec_spr_prev']
who = collections.Counter(); state = collections.Counter(); nticks = 0


def rects(cur):
    """Прямоугольники спрайтов в стайлах: cur=True — текущие (только перерисовываемые), иначе прошлые."""
    out = []
    for i in range(16):
        e = SPD + i * 8
        if not (mem[e] | mem[e+1]): continue
        if cur:
            if not mem[e+7]: continue
            x, y, nx, ny, typ = mem[e+3], mem[e+4], mem[e+5], mem[e+6], mem[e+2]
        else:
            p = PREV + i * 4
            x, y, nx, ny, typ = mem[p], mem[p+1], mem[p+2], mem[p+3], mem[e+2]
            if nx == 0: continue
        if y >= 160: continue
        e1 = x - 1 + nx * 8; e2 = y - 1 + ny * 8
        out.append((i, typ, mem[e+2] & 0x3f, x >> 4, 15 if e1 > 255 else min(15, e1 >> 4),
                    y >> 4, (159 if e2 >= 160 else e2) >> 4))
    return out


def scan():
    global nticks
    nticks += 1
    blk = [mem[BLK+i] for i in range(4)]
    cur = rects(True); prv = rects(False)
    for sy in range(10):
        for sx in range(16):
            idx = sy * 16 + sx
            s = mem[SLOT+idx]
            if s == 0xff: continue                      # стайл не грязный
            if mem[MAP+idx] not in blk: continue        # фон не чёрный
            if mem[FG+idx]: continue                    # есть передний тайл
            c = [r for r in cur if r[3] <= sx <= r[4] and r[5] <= sy <= r[6]]
            p = [r for r in prv if r[3] <= sx <= r[4] and r[5] <= sy <= r[6]]
            state[('$FE прямой' if s == 0xfe else 'слот', f'текущих {len(c)}', f'прошлых {min(len(p),2)}')] += 1
            if len(c) == 1:
                i, typ, bank, *_ = c[0]
                port = mem[BANKTAB + ((bank - 2) & 0x1f) * 2]
                who[(i, bank, '2пл' if port & 1 else '4пл', 'зерк' if typ & 0x80 else 'прямой')] += 1
            elif not c: who[('накрыт прошлым/ничем',)] += 1
            else: who[('больше одного спрайта',)] += 1


started = False
while ticks < SETTLE + NT:
    while not cpu.halted:
        pc = cpu.pc
        if pc == RS:
            ticks += 1; mem[FC] = ticks & 0xFF
            if ticks >= SETTLE:
                started = True; k = ticks - SETTLE; acc = 0
                for n, ks in ROUTE:
                    acc += n
                    if k < acc: keys[:] = ks; break
        if started and pc == RIT and mem[PON]: scan()
        cpu.step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
print(f'{nticks} тиков; ЧЁРНЫЕ стайлы (фон в vec_blk_tab, FG = 0)')
print('  кто накрывает (спрайт, банк, плоскостей, зеркальность):')
for k, v in who.most_common():
    print(f'    {v/max(1,nticks):6.2f}/тик  {v:5d}  {k}')
print('  состояние карты слотов x накрытие:')
for k, v in state.most_common():
    print(f'    {v/max(1,nticks):6.2f}/тик  {v:5d}  {k}')
