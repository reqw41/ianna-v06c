#!/usr/bin/env python3
"""Оценка гранулярности dirty 8×8 vs текущие супертайлы 16×16.

Считает на детерминированном стенде (как saveunder_est / abcyc --norand):
  * сколько стайлов реально нарисовано в BG/FG (rit_call) и сколько тактов;
  * сколько тактов ушло на сброс пула (vec_pool_flush);
  * объединение клеток 8×8 из InvalidateTiles (вход — в чарах) и из
    InvalidateSTiles (стайл → 4 клетки);
  * покрытие нарисованных стайлов этими клетками = «полезная» доля площади.

Потолок выигрыша (идеальный блит/сброс по клеткам, без накладных):
  gain ≈ (1 − useful/stiless_cells) × (BG + FG + flush) тактов.

  python3 tools/dirty8_est.py <rom> <lst> <edd> X,Y <тиков> [--rand]
"""
import sys, os, pathlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
if len(A) < 5:
    sys.exit(__doc__)
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])

os.environ['IANNA_EDD'] = EDD
if 'demo' in pathlib.Path(ROM).name:
    sys.exit('ОТКАЗ: демо-ROM не несёт сцен.')
sys.argv = [sys.argv[0]]
sys.path.insert(0, 'tools')
import run_vec as rv
src = open('tools/profile_vec.py').read()
exec(src[src.index('# Такты ВЕКТОРА'):src.index('keys = []')])

sym = rv.load_syms(pathlib.Path(LST))
keys = []
cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes()
cpu.mem[0x100:0x100 + len(rom)] = rom
cpu.pc = 0x100
rv.patch_menu(cpu)
if '--rand' not in OPTS:
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(','))
rv.start_game(cpu, keys, sym)
keys.append('right')

RS = sym['RunScripts']; FC = sym['FrameCounter']
INVT = sym['InvalidateTiles']; INVS = sym['InvalidateSTiles']
RSP2 = sym['RedrawScreen_part2']
RITC = sym['rit_call'] if 'rit_call' in sym else sym['rit_jp']   # серийный блит переименовал метку
DT_RIT = sym['dt_rit']          # BG-рисовалка в rit_call+1
DFT_RIT = sym['dft_rit']        # FG
FLUSH = sym['vec_pool_flush']
mem = cpu.mem
step = cpu.step


def chars_from_stile_rect(sx, sy, nx, ny):
    """Прямоугольник стайлов → множество клеток 8×8 (поле 32×20, ряды ≥20 — панель)."""
    out = set()
    for y in range(sy * 2, (sy + ny) * 2):
        if y >= 20:
            continue
        for x in range(sx * 2, (sx + nx) * 2):
            if x < 32:
                out.add((x, y))
    return out


def chars_from_tile_rect(tx, ty, nx, ny):
    """Прямоугольник в чарах 8×8 (как на входе InvalidateTiles)."""
    out = set()
    for y in range(ty & 0x1f, (ty & 0x1f) + ny):
        if y >= 20:
            continue
        for x in range(tx & 0x1f, (tx & 0x1f) + nx):
            if x < 32:
                out.add((x, y))
    return out


def stile_of_char(cx, cy):
    return (cx >> 1, cy >> 1)


# ---- состояние тика
tick = 0
tick_cyc = 0
char_dirty = set()          # клетки 8×8 из инвалидаций за тик
drawn_bg = {}               # стайл -> такты
drawn_fg = {}
flush_cyc = 0
cur_draw = None             # [ret_pc, stile, cyc, bgpass]
cur_flush = None            # [ret_pc, cyc]
inv_stack = 0               # глубина: InvalidateTiles ещё не дошёл до InvalidateSTiles
res = []

def close_tick():
    global char_dirty, drawn_bg, drawn_fg, flush_cyc, tick_cyc
    if tick_cyc == 0:
        return
    all_st = set(drawn_bg) | set(drawn_fg)
    stiless_cells = set()
    for sx, sy in all_st:
        stiless_cells |= chars_from_stile_rect(sx, sy, 1, 1)
    # клетки, которые «нужны»: пересечение dirty-инвалидаций с нарисованными стайлами
    useful = char_dirty & stiless_cells
    # стайлы, где dirty покрывает не все 4 клетки — кандидаты на четверти
    partial = 0
    for sx, sy in all_st:
        cells = chars_from_stile_rect(sx, sy, 1, 1)
        n = len(cells & char_dirty)
        if 0 < n < 4:
            partial += 1
    bgc = sum(drawn_bg.values())
    fgc = sum(drawn_fg.values())
    n_cells = len(stiless_cells)
    n_use = len(useful)
    ratio = (n_use / n_cells) if n_cells else 1.0
    area_cyc = bgc + fgc + flush_cyc
    gain = (1.0 - ratio) * area_cyc
    res.append(dict(
        cyc=tick_cyc, bg=len(drawn_bg), fg=len(drawn_fg),
        bgc=bgc, fgc=fgc, flush=flush_cyc,
        cells=n_cells, useful=n_use, ratio=ratio, gain=gain,
        partial=partial, dirty=len(char_dirty),
    ))
    char_dirty = set()
    drawn_bg = {}
    drawn_fg = {}
    flush_cyc = 0
    tick_cyc = 0


ticks_done = 0
while ticks_done < N:
    while not cpu.halted:
        pc = cpu.pc
        op = mem[pc] if pc < 0x8000 else cpu.rb(pc)
        w = CYC[op]
        tick_cyc += w
        if cur_draw is not None:
            cur_draw[2] += w
        if cur_flush is not None:
            cur_flush[1] += w
        if pc == RS:
            ticks_done += 1
            tick = ticks_done
            mem[FC] = ticks_done & 0xFF
        elif pc == RSP2:
            close_tick()
        elif pc == INVT:
            char_dirty |= chars_from_tile_rect(cpu.b, cpu.c, cpu.d, cpu.e)
            inv_stack += 1
        elif pc == INVS:
            if inv_stack > 0:
                inv_stack -= 1
            else:
                # прямой InvalidateSTiles (анимация и т.п.) — весь стайл
                char_dirty |= chars_from_stile_rect(cpu.b, cpu.c, cpu.d, cpu.e)
        elif pc == RITC:
            # rit_call+1..+2 = адрес dt_rit (фон) или dft_rit (FG)
            tgt = mem[RITC + 1] | (mem[RITC + 2] << 8)
            bgpass = tgt == DT_RIT
            cur_draw = [pc + 3, (cpu.b >> 4, cpu.c >> 4), 0, bgpass]
        elif pc == FLUSH:
            ret = cpu.rb(cpu.sp) | (cpu.rb(cpu.sp + 1) << 8)
            cur_flush = [ret, 0]
        step()
        if cur_draw is not None and cpu.pc == cur_draw[0]:
            d = drawn_bg if cur_draw[3] else drawn_fg
            d[cur_draw[1]] = d.get(cur_draw[1], 0) + cur_draw[2]
            cur_draw = None
        if cur_flush is not None and cpu.pc == cur_flush[0]:
            flush_cyc += cur_flush[1]
            cur_flush = None
    cpu.halted = False
    if cpu.ie:
        cpu.ie = False
        cpu.push(cpu.pc)
        cpu.pc = 0x38
close_tick()

nt = len(res)
if nt == 0:
    sys.exit('тиков не набрано')

def avg(k):
    return sum(r[k] for r in res) / nt

tot = sum(r['cyc'] for r in res)
area = sum(r['bgc'] + r['fgc'] + r['flush'] for r in res)
gain = sum(r['gain'] for r in res)
# средневзвешенная доля полезной площади
cells = sum(r['cells'] for r in res)
useful = sum(r['useful'] for r in res)
ratio = useful / cells if cells else 1.0

print(f'сцена {ST}: {nt} тиков, {tot/nt:.0f} такт/тик')
print(f'  нарисовано: BG {avg("bg"):.2f} стайла, FG {avg("fg"):.2f}; '
      f'клеток стайлов {avg("cells"):.1f}/тик, dirty-инвалид. {avg("dirty"):.1f}/тик')
print(f'  такты: BG {avg("bgc"):.0f}, FG {avg("fgc"):.0f}, flush {avg("flush"):.0f} '
      f'(вместе {area/nt:.0f} = {area/tot*100:.1f}% тика)')
print(f'  покрытие dirty∩нарисованное: {useful}/{cells} клеток = {ratio*100:.1f}% площади стайлов')
print(f'  стайлов с 1..3 грязными четвертями: {avg("partial"):.2f}/тик')
print(f'  потолок выигрыша (идеал 8×8): {gain/nt:.0f} т/тик '
      f'({gain/tot*100:.1f}% тика, {(1-ratio)*100:.1f}% площади BG+FG+flush)')
# оценка тик/с: кадр ≈ 60000 тактов @ 1.5МГц? Vector: 1.5MHz / (312*64*4?) —
# как в mus_reg_bench: ~0.28 кадра = известная шкала. FRAME ≈ 29950*2? 
# Из docs/ANALYSIS.md: тик в тактах / 60000 ≈ кадры при ~1.5 МГц и 50Гц → 30000 тактов/кадр слотов?
# abcyc печатает такты; measure_vec: кадр ~29950 тиков таймера * 2 = ~60К тактов CPU.
FRAME = 60000
c_now = tot / nt
c_new = c_now - gain / nt
print(f'  оценка кадров/тик: сейчас {c_now/FRAME:.2f}, после {c_new/FRAME:.2f} '
      f'(Δ {-(c_now-c_new)/FRAME:.2f}); тик/с≈ {min(10, 50/(c_now/FRAME)):.2f} → '
      f'{min(10, 50/(c_new/FRAME)):.2f}')
