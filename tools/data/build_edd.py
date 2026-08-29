#!/usr/bin/env python3
"""
build_edd.py — сборка образа квазидиска (.edd, 4 страницы по 64К) для Ianna/Вектор
и генерация build/gen_data.asm (палитра, LUT передних тайлов).

Раскладка (см. ANALYSIS.md):
  страница 0: $0000.. кадры варвара, банк 2 (sprite_barbaro_1.asm), 768 Б/кадр
              $8000.. 256 тайлов уровня, 128 Б/тайл (фон, без маски)
  страница 1: $0000.. кадры варвара, банк 3 (sprite_barbaro_2.asm)
              $6000.. передние тайлы с маской, 256 Б/тайл (только используемые уровнем)
              $8000.. level1.map как есть (адреса внутри карты рассчитаны на $8000)

Формат тайла фона (pop-блит, экран сверху вниз, DCR L):
  for p in 0..3: for col in 0..1: rows 0..15  -> байт = 8 пикселей, бит7 = левый
Формат кадра спрайта 24x32 (pop-блит снизу вверх, INR L):
  for p in 0..3: for col in 0..2: for row 31..0: [data, mask]; mask=1 где пиксель прозрачен (цвет 0)
Формат переднего тайла (маска, сверху вниз): for p: for col: rows 0..15: [data, mask]
Плоскость p несёт бит (3-p) цвета: индекс палитры Вектора == цвет MSX.
"""
import sys, re, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pletter import depack as pletter_depack
from aplib import depack as aplib_depack

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'ref/msx2/src'
BUILD = ROOT / 'build'

def planes_of_row(pixels):
    """pixels: список значений 0..15 (кратно 8). -> список из 4 списков байтов (по плоскостям)."""
    out = [[], [], [], []]
    for i in range(0, len(pixels), 8):
        chunk = pixels[i:i+8]
        for p in range(4):
            bit = 3 - p
            b = 0
            for k, v in enumerate(chunk):
                if (v >> bit) & 1:
                    b |= 0x80 >> k
            out[p].append(b)
    return out

def mask_of_row(pixels):
    out = []
    for i in range(0, len(pixels), 8):
        b = 0
        for k, v in enumerate(pixels[i:i+8]):
            if v == 0:
                b |= 0x80 >> k
        out.append(b)
    return out

def tile_pixels(sr5, n):
    x0, y0 = (n & 15) * 16, (n >> 4) * 16
    rows = []
    for y in range(16):
        row = []
        for x in range(16):
            b = sr5[(y0 + y) * 128 + (x0 + x) // 2]
            row.append(b >> 4 if (x & 1) == 0 else b & 15)
        rows.append(row)
    return rows

def bg_tile_bytes(rows):
    """128 Б: for p: for col: rows 0..15"""
    pl = [planes_of_row(r) for r in rows]          # pl[y][p][col]
    out = bytearray()
    for p in range(4):
        for col in range(2):
            for y in range(16):
                out.append(pl[y][p][col])
    return bytes(out)

def fg_tile_bytes(rows):
    """256 Б: for p: for col: rows 0..15: [data, mask]"""
    pl = [planes_of_row(r) for r in rows]
    mk = [mask_of_row(r) for r in rows]
    out = bytearray()
    for p in range(4):
        for col in range(2):
            for y in range(16):
                out += bytes([pl[y][p][col], mk[y][col]])
    return bytes(out)

def parse_sprite_asm(path):
    """Возвращает список кадров; кадр = 32 строки по 24 пикселя (значения 0..15)."""
    rows = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = re.match(r'\s*DB\s+(.*)', line)
        if not m:
            continue
        vals = [int(v) for v in m.group(1).split(',')]
        assert len(vals) == 12, line
        row = []
        for b in vals:
            row += [b >> 4, b & 15]
        rows.append(row)
    assert len(rows) % 32 == 0, (path, len(rows))
    return [rows[i:i+32] for i in range(0, len(rows), 32)]

def sprite_frame_bytes(frame):
    """768 Б: for p: for col(0..2): for row 31..0: [data, mask]"""
    pl = [planes_of_row(r) for r in frame]
    mk = [mask_of_row(r) for r in frame]
    out = bytearray()
    for p in range(4):
        for col in range(3):
            for y in range(31, -1, -1):
                out += bytes([pl[y][p][col], mk[y][col]])
    return bytes(out)

def msx_palette(plt):
    """test.plt: 16 x (R<<4|B, G), 3 бита. -> байты Вектора %BBGGGRRR"""
    out = []
    for i in range(16):
        b0, b1 = plt[2*i], plt[2*i+1]
        r = (b0 >> 4) & 7; b = b0 & 7; g = b1 & 7
        out.append(((b >> 1) << 6) | (g << 3) | r)
    return out

def level_fg_tiles(level):
    n = level[12]
    addrs = [level[22+2*i] | (level[23+2*i] << 8) for i in range(n)]
    fg = set()
    for a in addrs:
        scr, _ = aplib_depack(level, a - 0x8000)
        fg |= set(scr[160:320]) - {0}
    return sorted(fg)

def main():
    BUILD.mkdir(exist_ok=True)
    pages = [bytearray(65536) for _ in range(4)]
    # --- тайлы уровня 1 ---
    sr5 = pletter_depack((SRC / 'tiles_nivel01.SR5.plet1').read_bytes())
    assert len(sr5) == 32768
    for n in range(256):
        pages[0][0x8000 + n*128: 0x8000 + (n+1)*128] = bg_tile_bytes(tile_pixels(sr5, n))
    # --- спрайты варвара ---
    b2 = parse_sprite_asm(SRC / 'sprite_barbaro_1.asm')
    b3 = parse_sprite_asm(SRC / 'sprite_barbaro_2.asm')
    for i, fr in enumerate(b2):
        pages[0][i*768:(i+1)*768] = sprite_frame_bytes(fr)
    assert len(b2)*768 <= 0x8000
    for i, fr in enumerate(b3):
        pages[1][i*768:(i+1)*768] = sprite_frame_bytes(fr)
    assert len(b3)*768 <= 0x6000
    # --- передние тайлы уровня 1 с маской + LUT ---
    level = (SRC / 'level1.map').read_bytes()
    fg = level_fg_tiles(level)
    lut = [0]*256
    for i, t in enumerate(fg):
        addr = 0x6000 + i*256
        pages[1][addr:addr+256] = fg_tile_bytes(tile_pixels(sr5, t))
        lut[t] = addr
    assert 0x6000 + len(fg)*256 <= 0x8000
    # --- карта уровня ---
    pages[1][0x8000:0x8000+len(level)] = level
    assert len(level) <= 0x6000
    edd = b''.join(bytes(p) for p in pages)
    (BUILD / 'ianna.edd').write_bytes(edd)
    # --- gen_data.asm ---
    pal = msx_palette((SRC / 'test.plt').read_bytes())
    pal[0] = 0x00   # цвет 0 в уровне только прозрачный (FG-тайлы/спрайты); пустые строки VRAM -> чёрные
    lines = ['; сгенерировано build_edd.py', 'vec_palette:', '\tdb ' + ', '.join(f'${c:02X}' for c in pal), '',
             '; LUT передних тайлов: адрес в странице 1 квазидиска (0 = нет)', 'fg_tile_lut:']
    for i in range(0, 256, 8):
        lines.append('\tdw ' + ', '.join(f'${a:04X}' for a in lut[i:i+8]))
    (BUILD / 'gen_data.asm').write_text('\n'.join(lines) + '\n')
    print(f'ianna.edd: {len(edd)} Б; кадров банк2={len(b2)} банк3={len(b3)}; FG-тайлов={len(fg)} {fg}; палитра={[hex(c) for c in pal]}')

if __name__ == '__main__':
    main()
