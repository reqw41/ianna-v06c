# -*- coding: utf-8 -*-
"""Русские надписи игровой панели: названия оружия и буква уровня.

Издание одноязычное (русское), а в панели по-английски оставались картиночные надписи —
они лежат не текстом, а точками в armas.SR5/marcador.SR5. Исходные .SR5.plet1 не трогаем:
патч накладывается на РАСПАКОВАННЫЙ битмап при сборке набора (build_edd.build_kvaz),
до нарезки column_blob. Размер в наборе от этого не меняется — те же 4x192 и 2x288 байт.

  SWORD -> МЕЧ, ECLIPSE -> ЛУНА, AXE -> ТОПОР, BLADE -> КЛИНОК
  («ЛУНА» вместо «ЗАТМЕНИЕ»: в 24 точки затмение сливается в кашу)
  L: -> У: у героя в панели и в двух значках врагов (двоеточие и цифры движок печатает сам)
"""

# ---------- узкий шрифт 3x5 для названий оружия (в слот 24 точки влезает и КЛИНОК) ----------
F35 = {
 'А': ['010', '101', '111', '101', '101'],
 'Е': ['111', '100', '110', '100', '111'],
 # И — единственная в наборе 4 точки шириной: в трёх её не отличить от Н (диагональ негде вести,
 # а средний столбец без диагонали даёт ту же Н). КЛИНОК с ней ровно 24 точки — вся ширина слота.
 'И': ['1001', '1001', '1011', '1101', '1001'],
 'К': ['101', '110', '100', '110', '101'],
 'Л': ['011', '101', '101', '101', '101'],
 'М': ['101', '111', '111', '101', '101'],
 'Н': ['101', '101', '111', '101', '101'],
 'О': ['111', '101', '101', '101', '111'],
 'П': ['111', '101', '101', '101', '101'],
 'Р': ['111', '101', '111', '100', '100'],
 'Т': ['111', '010', '010', '010', '010'],
 'У': ['101', '101', '111', '001', '111'],
 'Ч': ['101', '101', '111', '001', '001'],
}

WEAPONS = ('МЕЧ', 'ЛУНА', 'ТОПОР', 'КЛИНОК')
LABEL_Y = 1            # надпись слота: строки 1..5 (в оригинале буквы стояли в 1..6)
LABEL_H = 6            # чистим 1..6 — сколько занимала английская надпись
SLOT_W = 24            # ширина слота в точках (3 знакоместа column_blob)

# ---------- «У» вместо «L» в счётчике уровня: 5 точек в ширину, 6 в высоту ----------
# Форма — сжатая до 5 точек «У» игрового шрифта (font_ru.SHAPES['У']): две руки, хвост влево.
U56 = ['##.##',
       '##.##',
       '.###.',
       '..##.',
       '.##..',
       '##...']
# Как выглядит «L» оригинала: столбик 2 точки шириной на 5 строк и подошва 4 точки.
L_STEM_W, L_FOOT_W, L_H = 2, 4, 6


def _bg(rows, y, x):
    return rows[y][x]


def find_L(rows, h, bg=1):
    """Все вхождения «L» счётчика уровня: (x, y, цвет столбика, цвет подошвы).

    Ищем именно форму, а не координаты: если художник подвинет панель, сборка упадёт на
    проверке количества, а не нарисует «У» поверх чужих точек.
    """
    out = []
    w = len(rows[0])
    for y in range(h - L_H + 1):
        for x in range(1, w - L_FOOT_W):
            a = rows[y][x]
            if a == bg:
                continue
            b = rows[y + L_H - 1][x]
            if b == bg:
                continue
            ok = True
            for dy in range(L_H - 1):                       # столбик: 2 точки цвета a
                if rows[y + dy][x] != a or rows[y + dy][x + 1] != a: ok = False; break
                if rows[y + dy][x + 2] != bg or rows[y + dy][x + 3] != bg: ok = False; break
                if rows[y + dy][x - 1] != bg: ok = False; break
            if not ok:
                continue
            for dx in range(L_FOOT_W):                      # подошва: 4 точки цвета b
                if rows[y + L_H - 1][x + dx] != b: ok = False; break
            if not ok or rows[y + L_H - 1][x - 1] != bg:
                continue
            if y and any(rows[y - 1][x + dx] != bg for dx in range(L_FOOT_W)): continue
            if y + L_H < h and any(rows[y + L_H][x + dx] != bg for dx in range(L_FOOT_W)): continue
            out.append((x, y, a, b))
    return out


def draw_U(rows, x, y, ink, ink_foot, bg=1):
    """«У» на месте «L»: занимает на точку левее (там пусто), правый край и высота те же."""
    x0 = x - 1
    for dy in range(L_H):
        for dx in range(L_FOOT_W + 1):
            rows[y + dy][x0 + dx] = bg
    for dy, line in enumerate(U56):
        c = ink_foot if dy == L_H - 1 else ink
        for dx, ch in enumerate(line):
            if ch == '#':
                rows[y + dy][x0 + dx] = c


def _ink_of(rows, x0, y0, w, h, bg):
    """Цвет надписи = самый частый не-фоновый в прямоугольнике."""
    import collections
    c = collections.Counter(rows[y0 + y][x0 + x] for y in range(h) for x in range(w))
    del c[bg]
    return c.most_common(1)[0][0]


def _text(word):
    return sum(len(F35[ch][0]) for ch in word) + len(word) - 1


def patch_armas(armas):
    """armas.SR5 (256x24): 4 слота оружия по 24 точки + два значка врага."""
    for w, word in enumerate(WEAPONS):
        x0 = w * 32
        bg = armas[0][x0]
        ink = _ink_of(armas, x0, LABEL_Y, SLOT_W, LABEL_H, bg)
        for y in range(LABEL_Y, LABEL_Y + LABEL_H):
            for x in range(x0, x0 + SLOT_W):
                armas[y][x] = bg
        assert _text(word) <= SLOT_W, (word, _text(word))
        x = x0 + (SLOT_W - _text(word)) // 2
        for ch in word:
            g = F35[ch]
            for dy, line in enumerate(g):
                for dx, p in enumerate(line):
                    if p == '1':
                        armas[LABEL_Y + dy][x + dx] = ink
            x += len(g[0]) + 1
    hits = find_L(armas, 24)
    assert len(hits) == 2, hits           # значки врага «вкл»/«выкл»
    for x, y, a, b in hits:
        draw_U(armas, x, y, a, b)
    return armas


def patch_panel(panel):
    """marcador.SR5 (256x32): «L:» у героя и подложка тех же двух значков врага."""
    hits = find_L(panel, 32)
    assert len(hits) == 3, hits           # герой + подложка двух значков
    for x, y, a, b in hits:
        draw_U(panel, x, y, a, b)
    return panel


if __name__ == '__main__':
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import build_edd as B
    from pletter import depack as pd
    armas = patch_armas(B.sr5_rows(pd((B.SRC / 'armas.SR5.plet1').read_bytes()), 24))
    panel = patch_panel(B.sr5_rows(pd((B.SRC / 'marcador.SR5.plet1').read_bytes()), 32))
    for y in range(16):
        print('%2d ' % y + ''.join('.' if v == 1 else '%x' % v for v in armas[y][:176]))
    print()
    for y in range(24, 32):
        print('%2d ' % y + ''.join('.' if v == 1 else '%x' % v for v in panel[y][145:245]))
