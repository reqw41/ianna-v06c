#!/usr/bin/env python3
r"""ОЦЕНКА save-under: сколько стайлов фона рисуется ТОЛЬКО из-за одного спрайта.

Идея save-under: вместо перерисовки фона тайлами под СТАРЫМ положением спрайта — восстановить
фон из буфера, снятого перед прошлой отрисовкой спрайта, а перед новой отрисовкой снять буфер
заново. Тогда все стайлы, которые грязны ТОЛЬКО из-за этого спрайта (и старое, и новое место),
рисовать не нужно вовсе: восстановление старого прямоугольника + снятие нового покрывает
ровно те пиксели, которых спрайт когда-либо касался.

Что считает стенд (детерминированный прогон, как cmpbuild --norand):
  * все вызовы InvalidateTiles/InvalidateSTiles с ВЛАДЕЛЬЦЕМ прямоугольника:
    - вызов из UpdateSprite -> владелец = спрайт, который двигают (объединённый старый+новый пр-к);
    - вызов из MarkOverlappingSprites/CleanSprite -> владелец = спрайт, чей прямоугольник совпал;
    - AnimateSTiles и прочее -> владельца нет («чужой» источник).
  * какие стайлы РЕАЛЬНО нарисованы в фоновом проходе (после дедупликации RIT_MAP) и почём
    (такты между входом в rit_call и возвратом).
  * для каждого спрайта: excl = (его стайлы) \ (стайлы всех прочих источников) — это и есть
    кандидаты на снятие; сумма по великанам (банк ROM 14..21) — потолок выигрыша.

Цена save-under (модель шины Вектора, см. tools/blit_model.py):
  восстановление 384 Б: pop из квазидиска (6 т/байт) + запись (8 т/байт) + шаг адреса ~ 2900 т;
  снятие 384 Б: чтение VRAM (8 т/байт) + push в квазидиск (6 т/байт) + шаги ~ 8500 т.
Обе цены задаются ключами --restore/--save, чтобы проверять чувствительность вывода.

  python3 tools/saveunder_est.py <rom> <lst> <edd> X,Y <тиков> [--rand] [--verbose]
"""
import sys, os, re, bisect, pathlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
if len(A) < 5:
    sys.exit(__doc__)
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])
def opt(name, dflt):
    for o in OPTS:
        if o.startswith('--' + name + '='):
            return float(o.split('=', 1)[1])
    return dflt
# Цена БАЙТА (модель шины Вектора, tools/blit_model.py) — взяты ТЕОРЕТИЧЕСКИЕ МИНИМУМЫ, то есть
# оценка в пользу save-under (реальный код всегда дороже на обвязку):
#   восстановление квазидиск -> VRAM: pop 6 + запись 8 + шаг адреса 8 = 22 т/байт
#     (сверка: сброс пула на уровне 1 даёт минимум 23 т/байт, факт 33.8 — см. blit_model)
#   снятие VRAM -> квазидиск: чтение 8 + шаг 8 + push 8 = 24 т/байт
T_RESTORE = opt('restore', 22.0)
T_SAVE = opt('save', 24.0)
VERBOSE = '--verbose' in OPTS

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
UPD = sym['UpdateSprite']; INVT = sym['InvalidateTiles']; INVS = sym['InvalidateSTiles']
RSP2 = sym['RedrawScreen_part2']
RITC = sym['rit_call']; RIT_MAP = sym['RIT_MAP']; RITMAPP = sym['rit_mapp']
SPDATA = sym['SPDATA']; ZIX = sym['z_ix']
MAXSPR = 16
mem = cpu.mem


def stiles(x, y, nx, ny):
    """Прямоугольник спрайта в ПИКСЕЛЯХ -> множество стайлов 16x16 (как InvalidateTiles: тайлы 8 px
    -> стайлы делением на 2). Ряды >= 10 (панель) обход не рисует."""
    t0x, t0y = x >> 3, y >> 3
    t1x, t1y = (x >> 3) + nx - 1, (y >> 3) + ny - 1
    out = set()
    for sy in range((t0y & 0x1f) >> 1, ((t1y & 0x1f) >> 1) + 1):
        if sy >= 10:
            continue
        for sx in range((t0x & 0x1f) >> 1, ((t1x & 0x1f) >> 1) + 1):
            out.add((sx, sy))
    return out


def rect_stiles(bx, cy, dn, en):
    """Прямоугольник уже в СТАЙЛАХ (как он лёг в tiles_dirty)."""
    return {(x, y) for y in range(cy, cy + en) if y < 10 for x in range(bx, bx + dn)}


def spr_rect(i):
    b = SPDATA + i * 8
    return (mem[b + 3], mem[b + 4], mem[b + 5], mem[b + 6])


def spr_on(i):
    b = SPDATA + i * 8
    return mem[b] | mem[b + 1]


def spr_bank(i):
    return mem[SPDATA + i * 8 + 2] & 0x7f


GIANT_BANKS = set(range(14, 22))     # голем 14/15, огр 16/17, минотавр 18/19, демон 20/21

# ---- состояние прогона
tick = 0
own_stack = []          # владельцы вложенных InvalidateTiles
upd_stack = []          # (ret, idx, old_rect, new_bc)
rects = []              # (владелец, множество стайлов) за тик
drawn_bg = {}           # стайл -> такты (фоновый проход)
drawn_fg = {}
cur_draw = None         # (ret, стайл, пас, такты)
tick_cyc = 0
res = []                # по тикам: dict
banks_seen = collections.Counter()

step = cpu.step
ticks_done = 0
CHECK = collections.Counter()

def close_tick():
    global rects, drawn_bg, drawn_fg, tick_cyc
    if tick_cyc == 0:
        return
    own = collections.defaultdict(set)
    for o, s in rects:
        own[o] |= s
    all_bg = set(drawn_bg)
    banks = {i: spr_bank(i) for i in range(MAXSPR) if spr_on(i)}
    # байт буфера на спрайт: nx*8 px по X / 8 = nx байт в строке, ny*8 строк, 4 плоскости
    bufb = {}
    for i in range(MAXSPR):
        x, y, nx, ny = spr_rect(i)
        bufb[i] = nx * ny * 8 * 4

    def group(members):
        """excl = стайлы, грязные ТОЛЬКО из-за спрайтов группы (и реально нарисованные)."""
        mine = set()
        others = set()
        for o, s in own.items():
            if isinstance(o, int) and o in members:
                mine |= s
            else:
                others |= s
        excl = (mine - others) & all_bg
        cost = sum(bufb[i] for i in members if i in own) * (T_RESTORE + T_SAVE)
        return dict(mine=len(mine & all_bg), excl=len(excl),
                    gain=sum(drawn_bg[t] for t in excl), cost=cost)

    # самопроверка стенда: каждый нарисованный стайл обязан быть покрыт каким-то грязным
    # прямоугольником, иначе разбор владельцев потерял вызов
    cover = set()
    for s in own.values():
        cover |= s
    CHECK['lost'] += len(all_bg - cover)
    CHECK['drawn'] += len(all_bg)
    act = [i for i in own if isinstance(i, int)]
    per = {i: group({i}) for i in act}
    gi = [i for i in act if banks.get(i, 0) in GIANT_BANKS]
    res.append(dict(tick=tick, cyc=tick_cyc, bg=len(all_bg),
                    bgcyc=sum(drawn_bg.values()), fg=len(drawn_fg),
                    fgcyc=sum(drawn_fg.values()), per=per, banks=banks,
                    grp_giant=group(set(gi)) if gi else None,
                    grp_all=group(set(act)) if act else None))
    rects = []
    drawn_bg = {}
    drawn_fg = {}
    tick_cyc = 0


while ticks_done < N:
    while not cpu.halted:
        pc = cpu.pc
        op = mem[pc] if pc < 0x8000 else cpu.rb(pc)
        w = CYC[op]
        tick_cyc += w
        if cur_draw is not None:
            cur_draw[2] += w
        if pc == RS:
            ticks_done += 1
            tick = ticks_done
            mem[FC] = ticks_done & 0xFF
        elif pc == RSP2:
            # граница тика для разбора: сюда приходят ПОСЛЕ прохода фона/спрайтов/FG, и здесь же
            # оригинал обнуляет ndirtyrects. Считать по RunScripts нельзя: AnimateSTiles зовут
            # ДО него, и его прямоугольники попали бы в прошлый тик (ловилось самопроверкой)
            close_tick()
        elif pc == UPD:
            ix = mem[ZIX] | (mem[ZIX + 1] << 8)
            idx = (ix - SPDATA) // 8
            assert 0 <= idx < MAXSPR and (ix - SPDATA) % 8 == 0, f'UpdateSprite: IX={ix:04X}'
            ret = cpu.rb(cpu.sp) | (cpu.rb(cpu.sp + 1) << 8)
            upd_stack.append((ret, idx, spr_rect(idx), (cpu.b, cpu.c)))
            CHECK['upd'] += 1
        elif pc == INVT:
            b, c, d, e = cpu.b, cpu.c, cpu.d, cpu.e
            owner = None
            if upd_stack:
                owner = upd_stack[-1][1]
            else:                       # MarkOverlappingSprites / CleanSprite: ищем спрайт по пр-ку
                for i in range(MAXSPR):
                    x, y, nx, ny = spr_rect(i)
                    if spr_on(i) and ((x >> 3) & 0x1f, (y >> 3) & 0x1f, nx, ny) == (b, c, d, e):
                        owner = i
                        break
            own_stack.append(owner if owner is not None else 'чужой')
            CHECK['inv'] += 1
            CHECK['inv_noowner'] += (owner is None)
        elif pc == INVS:
            o = own_stack.pop() if own_stack else 'чужой'
            rects.append((o, rect_stiles(cpu.b, cpu.c, cpu.d, cpu.e)))
        elif pc == RITC:
            # какой проход — по самомодифицируемому младшему байту карты (rit_mapp+1)
            bgpass = mem[RITMAPP + 1] == (RIT_MAP & 0xFF)
            cur_draw = [pc + 3, (cpu.b >> 4, cpu.c >> 4), 0, bgpass]
        step()
        if upd_stack and cpu.pc == upd_stack[-1][0]:
            upd_stack.pop()
        if cur_draw is not None and cpu.pc == cur_draw[0]:
            d = drawn_bg if cur_draw[3] else drawn_fg
            d[cur_draw[1]] = d.get(cur_draw[1], 0) + cur_draw[2]
            cur_draw = None
    cpu.halted = False
    if cpu.ie:
        cpu.ie = False
        cpu.push(cpu.pc)
        cpu.pc = 0x38
close_tick()

# ---- отчёт
nt = len(res)
if nt == 0:
    sys.exit('тиков не набрано')
tot = sum(r['cyc'] for r in res)
bg = sum(r['bg'] for r in res)
bgc = sum(r['bgcyc'] for r in res)
fg = sum(r['fg'] for r in res)
fgc = sum(r['fgcyc'] for r in res)
print(f'сцена {ST}: {nt} тиков, {tot/nt:.0f} такт/тик')
print(f'  фон: {bg/nt:.2f} стайла/тик, {bgc/nt:.0f} такт/тик ({bgc/max(bg,1):.0f} т/стайл, '
      f'{bgc/tot*100:.1f} % тика)')
print(f'  FG:  {fg/nt:.2f} стайла/тик, {fgc/nt:.0f} такт/тик ({fgc/max(fg,1):.0f} т/стайл)')

print(f'  самопроверка: нарисовано {CHECK["drawn"]} стайлов, без грязного прямоугольника '
      f'{CHECK["lost"]}; InvalidateTiles {CHECK["inv"]} (без владельца {CHECK["inv_noowner"]}), '
      f'UpdateSprite {CHECK["upd"]}')
print(f'  цена байта: восстановление {T_RESTORE:.0f} т, снятие {T_SAVE:.0f} т '
      f'(теоретические минимумы — оценка В ПОЛЬЗУ save-under)')


def show(name, rows):
    n = sum(1 for r in rows if r)
    if not n:
        return
    mine = sum(r['mine'] for r in rows if r)
    excl = sum(r['excl'] for r in rows if r)
    gain = sum(r['gain'] for r in rows if r)
    cost = sum(r['cost'] for r in rows if r)
    net = gain - cost
    print(f'  {name:26s} {mine/nt:6.2f} {excl/nt:6.2f} {gain/nt:8.0f} {cost/nt:8.0f} '
          f'{net/nt:+9.0f} {net/tot*100:+7.2f} %')


print(f'  {"группа":26s} {"мои":>6s} {"тольк":>6s} {"выигр":>8s} {"цена":>8s} {"нетто":>9s} '
      f'{"% тика":>9s}')
seen = set()
for r in res:
    seen |= set(r['per'])
for i in sorted(seen):
    bank = next((r['banks'][i] for r in res if i in r['banks']), 0)
    mark = ' ВЕЛИКАН' if bank in GIANT_BANKS else ''
    show(f'спрайт {i} (банк {bank}){mark}', [r['per'].get(i) for r in res])
show('ВСЕ великаны как один', [r['grp_giant'] for r in res])
show('ВСЕ спрайты как один', [r['grp_all'] for r in res])

if VERBOSE:
    for r in res[:40]:
        pp = ' '.join(f'спр{i}:{p["excl"]}' for i, p in sorted(r['per'].items()))
        print(f'   тик {r["tick"]:3d} такт {r["cyc"]:7d} фон {r["bg"]:2d} FG {r["fg"]:2d}  {pp}')

# ---- арифметика безубыточности: сколько стайлов надо СНЯТЬ, чтобы окупить одну пару
# «восстановить старое место + снять новое» для половины великана (24x32 px x 4 плоскости = 384 Б)
cps = bgc / max(bg, 1)
for nb, what in ((384, 'половина великана 24x32'), (768, 'великан целиком 24x64')):
    c = nb * (T_RESTORE + T_SAVE)
    print(f'  безубыточность ({what}, {nb} Б): {c:.0f} т = {c/cps:.1f} стайла фона '
          f'(стайл {cps:.0f} т); прямоугольник накрывает не больше '
          f'{2*((nb//384)*2+1)} стайлов')
