#!/usr/bin/env python3
"""Кого на уровне класть в две плоскости: жадный подбор по «ущербу» с проверкой раскладки.
Ущерб банка = доля смещённых точек x число экранов, где враг встречается (на скольких экранах
игрок увидит упрощение). Половины великана всегда идут парой — они на одном экране, а слоты
палитры 1..3 у экрана одни. Уже утверждённые карты (BANK_2PLANE_ALL) считаются по ним, остальные —
оптимумом k-medoids по трём цветам плюс чёрный.
  python3 tools/pick_2plane.py [номера уровней]
"""
import sys, pathlib, collections, itertools, subprocess, os
MODE = os.environ.get('PACK_MODE', 'low')   # low = тайлы в начало страницы (без перенумерации),
                                            # dense = плотная укладка с перенумерацией через LUT
sys.path.insert(0, 'tools/data')
import build_edd as B

raw = B.msx_palette((B.SRC / 'test.plt').read_bytes())
PAL = [((v & 7)*255//7, ((v >> 3) & 7)*255//7, ((v >> 6) & 3)*255//3) for v in raw]
NAMES = {7: 'скелет', 8: 'орк', 9: 'мумия', 10: 'тролль', 11: 'Дальгурак', 12: 'валун',
         13: 'рыцарь', 14: 'голем', 16: 'огр', 18: 'минотавр', 20: 'демон'}
EB = {20: 7, 21: 8, 22: 9, 23: 10, 24: 12, 25: 13, 26: 11, 27: (14, 15), 28: (16, 17),
      29: (18, 19), 30: (20, 21)}
PAIRS = {14: 15, 16: 17, 18: 19, 20: 21}        # половины великанов
MERGE = dict(B.COLOR_MERGE)

def dist(a, b):
    r1, g1, b1 = PAL[a]; r2, g2, b2 = PAL[b]
    return (2*(r1-r2)**2 + 4*(g1-g2)**2 + 3*(b1-b2)**2) ** 0.5

def counts(banks):
    c = collections.Counter()
    for b in banks:
        for f in B.parse_sprite_asm(str(B.BUILD / 'msx2' / f'{B.BANK_FILE[b]}.asm')):
            c.update(MERGE.get(v, v) for row in f for v in row if v)
    return c

def cost(banks):
    """Доля смещённых точек при укладке банков (одного существа) в четыре цвета."""
    c = counts(banks)
    tot = sum(c.values())
    ready = B.BANK_2PLANE_ALL.get(banks[0])
    if ready:                                    # карта уже утверждена — считаем по ней
        slot = {}
        for src, s in ready.items(): slot.setdefault(s, []).append(src)
        moved = 0
        for src, s in ready.items():
            rep = max(slot[s], key=lambda k: c.get(k, 0))
            if src != rep: moved += c.get(src, 0)
        return moved*100.0/max(tot, 1), True
    rest = [k for k in c if PAL[k] != (0, 0, 0)]
    best = min(((sum(c[k]*min(dist(k, m) for m in meds) for k in rest), meds)
                for meds in itertools.combinations(rest, min(3, len(rest)))), default=(0, ()))
    meds = best[1]
    moved = sum(c[k] for k in rest if k not in meds)
    return moved*100.0/max(tot, 1), False

def level_info(L):
    lvl = (B.SRC / f'level{L}.map').read_bytes()
    scr = B.screens_of(lvl)
    need, seen = set(), collections.Counter()
    for s in scr:
        ob = s[360:403]
        for t in (ob[2], ob[8] if ob[2] not in (27, 28, 29, 30) else 0):
            v = EB.get(t)
            if v:
                v = v if isinstance(v, tuple) else (v,)
                need.update(v); seen[v[0]] += 1
    return sorted({2, 3} | need), seen

def ntiles(L):
    lvl = (B.SRC / f'level{L}.map').read_bytes()
    u = set()
    for s in B.screens_of(lvl): u |= set(s[0:160])
    return len(u - {0}) + 1

def fits(L, tiny):
    r = subprocess.run([sys.executable, 'tools/kvaz_pack.py', f'--level={L}',
                        ] + (['--tiles-low'] if MODE == 'low' else [f'--tiles={ntiles(L)}', '--tiles-end']) +
                       ([] if L == 1 else ['--menu-out']) +
                       ['--tiny=' + ','.join(map(str, sorted(tiny)))],
                       capture_output=True, text=True)
    return ('НЕ ВЛЕЗАЕТ' not in r.stdout) and ('ВЛЕЗАЕТ' in r.stdout), r.stdout

for L in [int(a) for a in sys.argv[1:]] or list(range(1, 10)):
    banks, seen = level_info(L)
    cands = []
    for b in sorted(seen):
        if b in (2, 3): continue
        group = [b, PAIRS[b]] if b in PAIRS else [b]
        pct, ready = cost(group)
        cands.append((pct*seen[b], pct, seen[b], group, ready))
    cands.sort()                                  # сперва самые дешёвые по ущербу
    ok, _ = fits(L, set())
    tiny = set()
    for dmg, pct, n, group, ready in cands:
        if ok: break
        tiny.update(group)
        ok, _ = fits(L, tiny)
    print(f'уровень {L}: банки {banks}')
    if not ok:
        print('   НЕ ВЛЕЗАЕТ даже со всеми сжатыми'); continue
    if not tiny:
        print('   влезает целиком в шестнадцати цветах'); continue
    print('   в четыре цвета: ' + ', '.join(
        f'{NAMES[g[0]]} ({p:.0f} % точек, {n} экр.{", карта готова" if r else ""})'
        for d, p, n, g, r in cands if g[0] in tiny))
    print(f'   всего сжато банков: {len(tiny)} из {len(banks)}')
