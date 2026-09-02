#!/usr/bin/env python3
"""Упаковка набора уровня в квазидиск (4 страницы по 64К): полный перебор с отсечением.
Жадная раскладка даёт ложные отказы — блоков мало, перебор надёжнее.
  python3 tools/kvaz_pack.py [--level=2] [--small=14,15] [--tiles=256] [--songs-out] [--mfont-out] [--drop=12]
"""
import sys, pathlib
sys.path.insert(0, 'tools/data')
import build_edd as B
FR = B.FRAME_BYTES
OPT = dict((a.split('=', 1) + ['1'])[:2] for a in sys.argv[1:])
LEVEL = int(OPT.get('--level', 2))
SMALL = {int(x) for x in OPT.get('--small', '').split(',') if x}
TINY = {int(x) for x in OPT.get('--tiny', '').split(',') if x}   # 2 плоскости: 288 Б на кадр
DROP = {int(x) for x in OPT.get('--drop', '').split(',') if x}
NTILES = int(OPT.get('--tiles', 256))
SONGS_OUT = '--songs-out' in OPT
MFONT_OUT = '--mfont-out' in OPT

def nf(b):
    return len(B.parse_sprite_asm(str(pathlib.Path('build/msx2') / f'{B.BANK_FILE[b]}.asm')))

def level_banks(level):
    l = list((B.SRC / f'level{level}.map').read_bytes())
    need = set()
    ENEMY_BANK = {20: 7, 21: 8, 22: 9, 23: 10, 24: 12, 25: 13, 26: 11,
                  27: (14, 15), 28: (16, 17), 29: (18, 19), 30: (20, 21)}
    for scr in B.screens_of(l):
        ob = scr[360:403]
        for t in (ob[2], ob[8] if ob[2] not in (27, 28, 29, 30) else 0):
            if t in ENEMY_BANK:
                v = ENEMY_BANK[t]
                need.update(v if isinstance(v, tuple) else (v,))
    return sorted({2, 3} | need)

def map_len():
    """Длина карты уровня в квазидиске: у разных уровней она разная (уровень 1 — 8.4 КБ, уровень 2 — 9.3),
    а банк за ней должен начинаться с адреса, кратного 256. Берём фактическую, иначе раскладка,
    посчитанная по чужой длине, наедет на карту (так и вышло с орком на уровне 2)."""
    return {1: 8600, 2: 9540}.get(LEVEL, 9600)

def fixed_blocks():
    f = [(1, 0x8000, 8600, 'карта'), (2, 0xE000, 0x1000, 'песня уровня'),
         (3, 0x0000, 0x2800, 'шрифт/панель/оружие'), (3, 0x8440, 0x1BC0, 'оверлеи'),
         (3, 0xA000, 0x2800, 'пул'), (3, 0xC980, 0x1000, 'музыка'), (3, 0xD980, 0x1000, 'эффекты'),
         (2, 0xBC40, 0x300, 'таблицы уровня и копия загрузчика'),
         (2, 0xBF00, 0x100, 'вынесенный блит')]
    if not SONGS_OUT: f.append((2, 0xC000, 0x2000, 'песни меню и интро'))
    if not MFONT_OUT: f.append((3, 0xE000, 0x1000, 'шрифт меню'))
    return f

def solve(items, free):
    """items: [(имя, размер)] по убыванию; free: [[ [s,e], ... ] x4]. Возвращает раскладку или None."""
    if not items: return []
    (nm, sz), rest = items[0], items[1:]
    seen = set()
    pages = [0] if isinstance(nm, str) and nm.endswith('@0') else range(4)
    for pg in pages:
        for i, (s, e) in enumerate(free[pg]):
            if e - s < sz or (pg, e - s) in seen: continue
            seen.add((pg, e - s))
            nf2 = [list(map(list, x)) for x in free]
            nf2[pg][i] = [s + sz, e]
            if nf2[pg][i][0] >= nf2[pg][i][1]: nf2[pg].pop(i)
            sub = solve(rest, nf2)
            if sub is not None: return [(nm, pg, s, sz)] + sub
    return None

banks = [b for b in level_banks(LEVEL) if b not in DROP]
free = [[[0, 65536]] for _ in range(4)]
def occ(pg, a, n):
    out = []
    for s, e in free[pg]:
        if a >= e or a + n <= s: out.append([s, e]); continue
        if s < a: out.append([s, a])
        if a + n < e: out.append([a + n, e])
    free[pg] = out
for pg, a, n, _ in fixed_blocks(): occ(pg, a, n)
# тайлы и передние тайлы обязаны лежать в странице 0 (страница зашита в блиттере), но адрес свободен
items = [('тайлы@0', NTILES * 128), ('FG@0', 14 * 256), ('палитры экранов', 147)]
items += [(b, nf(b) * (288 if b in TINY else 384 if b in SMALL else FR)) for b in banks]
if SONGS_OUT: items.append(('песни меню', 0x2000))
if MFONT_OUT: items.append(('шрифт меню', 0x1000))
items.sort(key=lambda x: -x[1])
print(f'уровень {LEVEL}: банки {banks}' + (f', в 2 плоскости {sorted(TINY)}' if TINY else '') + (f', сжаты {sorted(SMALL)}' if SMALL else '')
      + (f', выброшены {sorted(DROP)}' if DROP else ''))
print('  ' + ', '.join(f'{n}={s/1024:.1f}К' for n, s in items))
plan = solve(items, free)
if plan is None:
    print('  НЕ ВЛЕЗАЕТ')
else:
    print('  ВЛЕЗАЕТ:')
    for nm, pg, s, sz in sorted(plan, key=lambda x: (x[1], x[2])):
        print(f'    {"банк %2d" % nm if isinstance(nm,int) else nm:14s} стр.{pg} ${s:04X}-${s+sz:04X} ({sz/1024:5.1f}К)')
    print('  LEVEL_BANKS[%d] = [' % LEVEL + ', '.join(
        f'({nm}, {pg}, 0x{s:04X}, 0x{s+sz:04X})' for nm, pg, s, sz in sorted(plan, key=lambda x: str(x[0])) if isinstance(nm, int)) + "]")
