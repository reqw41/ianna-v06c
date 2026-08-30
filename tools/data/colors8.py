#!/usr/bin/env python3
"""Цветовая система 8-цветной сборки (3 плоскости), согласована 2026-08-30.
Слоты палитры (индекс пикселя 0..7): 0 чёрный, 1..5 цвета героя (фиксированы на всех
экранах), 6 — опознавательный цвет врага экрана / яркий, 7 — «фоновый» (небо/вода/серый).
Прозрачность спрайтов — в масках (маска по ИСХОДНОМУ пикселю), поэтому слот 0 — обычный чёрный.
Карта «цвет MSX -> слот» одна на уровень (тайлы общие), по экранам меняются только значения
слотов 6 и 7 (палитра ставится при смене экрана).
"""
import collections
SLOT_RGB = [(0,0,0),(3,2,1),(7,4,1),(7,5,5),(4,6,7),(5,0,1)]   # слоты 0..5 (RGB 0..7 Вектора)
# герой: переназначение исходных цветов (стабилен в деталях; согласовано: серый->корич, блики->голубой)
HREMAP = {0:0, 1:0, 9:1, 10:2, 14:3, 4:4, 3:5, 7:1, 11:4, 6:4, 8:4, 5:2, 2:1, 12:1, 13:1, 15:1}
# опознавательный цвет врага (слот 6 на его экранах) и карта банка врага -> слоты
ENEMY_SLOT6 = {20:(7,7,7), 21:(0,5,0), 22:(7,7,7), 23:(5,5,5), 24:(5,5,5), 25:(5,5,5),
               26:(0,5,0), 27:(4,6,7), 28:(5,5,5), 29:(3,2,1), 30:(5,0,1)}
def enemy_map(msx, slot6_rgb, slot7_rgb):
    """Карта 16->слот для банка врага: к ближайшему из 8 слотов его экрана (слот 6 = его цвет)."""
    pal = SLOT_RGB + [slot6_rgb, slot7_rgb]
    return [0] + [nearest(msx[c], pal) for c in range(1, 16)]
W = (1.0, 2.0, 0.6)
def d2(a, b): return sum(w*(x-y)**2 for w, x, y in zip(W, a, b))
def nearest(rgb, pal): return min(range(len(pal)), key=lambda i: d2(rgb, pal[i]))
def level_system(SRC, lvl):
    """-> (tile_map[16], screens: [(slot6_rgb, slot7_rgb)], palettes: [[8 rgb]])."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from build_edd import screens_of, tile_pixels
    from pletter import depack as pletter_depack
    plt = (SRC/'test.plt').read_bytes(); msx = []
    for i in range(16):
        b0, b1 = plt[2*i], plt[2*i+1]; msx.append(((b0>>4)&7, b1&7, b0&7))
    msx[0] = (0, 0, 0)
    sr5 = pletter_depack((SRC/f'tiles_nivel{lvl:02d}.SR5.plet1').read_bytes())
    lv = (SRC/f'level{lvl}.map').read_bytes(); scr = screens_of(lv)
    # частоты цветов по тайлам уровня — кандидаты на слоты 6/7 уровня
    hist = collections.Counter()
    for s in scr:
        for t in s[:320]: hist[t] += 1
    # карта тайлов уровня: небо/глубокая вода -> 7, зелень -> 6, остальное к ближайшему из 0..5
    # (слоты 6/7 меняются по экранам — тайлам их давать можно только цветам, чья роль совпадает с ролью слота)
    tile_map = [0]*16
    for c in range(1, 16):
        rgb = msx[c]
        if rgb in ((0,0,5), (2,3,7)): tile_map[c] = 7            # небо и середина воды
        elif rgb in ((0,5,0), (4,7,0)): tile_map[c] = 6           # зелень (мох; на экранах врага перекрасится)
        else: tile_map[c] = nearest(rgb, SLOT_RGB)
    screens = []; palettes = []
    for s in scr:
        en = [s[o] for o in (362, 368) if len(s) > o and s[o]]
        s6 = ENEMY_SLOT6.get(en[0]) if en else None
        # гистограмма экрана в цветах, ушедших в слоты 6/7
        h6 = collections.Counter(); h7 = collections.Counter()
        for k in range(320):
            c = s[k] if k < 160 else s[k]
            pass
        for k in range(160):
            for t in (s[k], s[160+k]):
                if t == 0: continue
                for row in tile_pixels(sr5, t):
                    for v in row:
                        if tile_map[v] == 6: h6[msx[v]] += 1
                        elif tile_map[v] == 7: h7[msx[v]] += 1
        if s6 is None: s6 = h6.most_common(1)[0][0] if h6 else (0,5,0)
        s7 = h7.most_common(1)[0][0] if h7 else (0,0,5)
        screens.append((s6, s7)); palettes.append(SLOT_RGB + [s6, s7])
    return msx, tile_map, screens, palettes
