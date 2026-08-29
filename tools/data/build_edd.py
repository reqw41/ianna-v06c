#!/usr/bin/env python3
"""
build_edd.py — данные для Ianna/Вектор.

Без аргументов: образ квазидиска build/ianna.edd (4 страницы по 64К) + build/gen_data.asm.
  страница 0: $0000.. кадры варвара, банк 2 (sprite_barbaro_1.asm), 384 Б/кадр
              $8000.. 256 тайлов уровня, 128 Б/тайл (фон, без маски)
  страница 1: $0000.. кадры варвара, банк 3 (sprite_barbaro_2.asm)
              $6000.. передние тайлы с маской, 256 Б/тайл (только используемые уровнем)
              $8000.. level1.map (строки/скрипты перенесены на STRING_AREA)
--demo: одиночный ROM без квазидиска: build/demo_data.asm (org DEMO_DATA_ADDR) с данными
  ТОЛЬКО первой сцены: используемые тайлы фона + LUT, передние тайлы, кадры 0..N-1 банка 2,
  мини-уровень (все ячейки -> стартовый экран, скрипты только нужные).

Форматы (общие для обеих сборок):
  тайл фона 128 Б: for p in 0..3: for col in 0..1: rows 0..15 (экран сверху вниз, DCR L)
  передний тайл 256 Б: for p: for col: rows 0..15: [data, mask] (mask=1 где прозрачно)
  кадр спрайта 24x32 = 384 Б: for col in 0..2: for row 31..0: [p0,p1,p2,p3] (снизу вверх, INR L);
      маска считается на лету = ~(p0|p1|p2|p3). Адрес кадра MSX ($8000+n*384) -> база + n*384.
  Плоскость p несёт бит (3-p) цвета: индекс палитры Вектора == цвет MSX.
"""
import sys, re, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pletter import depack as pletter_depack
from aplib import depack as aplib_depack
from level_tools import parse_level, build_level, relocate_strings, pack

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'ref/msx2/src'
BUILD = ROOT / 'build'
STRING_AREA_KVAZ = 0x6C00   # vars наверху ОЗУ (см. build_vec.py): string_area квазидисковой сборки
STRING_AREA_DEMO = 0x7400   # демо: string_area 512 Б, vars короче (до $8000 ровно)
DEMO_DATA_ADDR = 0x0200     # блок данных демо-ROM сразу за jp по $0100
DEMO_FRAMES = 10            # idle, gira, camina x6, cae x2 (см. sprites.asm)

def planes_of_row(pixels):
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
    pl = [planes_of_row(r) for r in rows]
    out = bytearray()
    for p in range(4):
        for col in range(2):
            for y in range(16):
                out.append(pl[y][p][col])
    return bytes(out)

def fg_tile_bytes(rows):
    pl = [planes_of_row(r) for r in rows]
    mk = [mask_of_row(r) for r in rows]
    out = bytearray()
    for p in range(4):
        for col in range(2):
            for y in range(16):
                out += bytes([pl[y][p][col], mk[y][col]])
    return bytes(out)

def parse_sprite_asm(path):
    rows = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = re.match(r'\s*DB\s+(.*)', line)
        if not m:
            continue
        vals = [int(v) for v in m.group(1).split(',')]
        assert len(vals) == 12, line
        row = []
        for b in vals:
            row += [b & 15, b >> 4]     # спрайты MSX2: МЛАДШИЙ ниббл = левый пиксель (см. rld в sendSpriteGfx)
        rows.append(row)
    assert len(rows) % 32 == 0, (path, len(rows))
    return [rows[i:i+32] for i in range(0, len(rows), 32)]

def sprite_frame_bytes(frame):
    """384 Б: for col(0..2): for row 31..0: [p0,p1,p2,p3]"""
    pl = [planes_of_row(r) for r in frame]
    out = bytearray()
    for col in range(3):
        for y in range(31, -1, -1):
            out += bytes(pl[y][p][col] for p in range(4))
    return bytes(out)

def msx_palette(plt):
    out = []
    for i in range(16):
        b0, b1 = plt[2*i], plt[2*i+1]
        r = (b0 >> 4) & 7; b = b0 & 7; g = b1 & 7
        out.append(((b >> 1) << 6) | (g << 3) | r)
    out[0] = 0x00   # цвет 0 в уровне только прозрачный; пустые строки VRAM -> чёрные
    return out

def screens_of(level):
    n = level[12]
    addrs = [level[22+2*i] | (level[23+2*i] << 8) for i in range(n)]
    return [aplib_depack(level, a - 0x8000)[0] for a in addrs]

def fg_lut_lines(fg):
    lut = [0]*256
    for i, t in enumerate(fg):
        lut[t] = i + 1
    lines = ['; LUT передних тайлов: 0 = нет, иначе индекс+1 (адрес = FG_TILES_BASE + (i-1)*256); страница!',
             '\tds ($ + 255) & $FF00 - $', 'fg_tile_lut:']
    for i in range(0, 256, 16):
        lines.append('\tdb ' + ', '.join(str(v) for v in lut[i:i+16]))
    return lines

def palette_lines():
    pal = msx_palette((SRC / 'test.plt').read_bytes())
    return ['vec_palette:', '\tdb ' + ', '.join(f'${c:02X}' for c in pal)]

def build_kvaz():
    pages = [bytearray(65536) for _ in range(4)]
    sr5 = pletter_depack((SRC / 'tiles_nivel01.SR5.plet1').read_bytes())
    assert len(sr5) == 32768
    for n in range(256):
        pages[0][0x8000 + n*128: 0x8000 + (n+1)*128] = bg_tile_bytes(tile_pixels(sr5, n))
    b2 = parse_sprite_asm(SRC / 'sprite_barbaro_1.asm')
    b3 = parse_sprite_asm(SRC / 'sprite_barbaro_2.asm')
    for i, fr in enumerate(b2):
        pages[0][i*384:(i+1)*384] = sprite_frame_bytes(fr)
    for i, fr in enumerate(b3):
        pages[1][i*384:(i+1)*384] = sprite_frame_bytes(fr)
    level = (SRC / 'level1.map').read_bytes()
    fg = sorted(set().union(*(set(s[160:320]) for s in screens_of(level))) - {0})
    for i, t in enumerate(fg):
        addr = 0x6000 + i*256
        pages[1][addr:addr+256] = fg_tile_bytes(tile_pixels(sr5, t))
    assert 0x6000 + len(fg)*256 <= 0x8000
    info = parse_level(level)
    level2 = build_level(info, STRING_AREA_KVAZ)          # строки/скрипты -> string_area Вектора
    pages[1][0x8000:0x8000+len(level2)] = level2
    edd = b''.join(bytes(p) for p in pages)
    (BUILD / 'ianna.edd').write_bytes(edd)
    lines = ['; сгенерировано build_edd.py (квазидиск)', 'FG_TILES_BASE\tequ $6000\t; страница 1'] + palette_lines() + [''] + fg_lut_lines(fg)
    (BUILD / 'gen_data.asm').write_text('\n'.join(lines) + '\n')
    print(f'ianna.edd: {len(edd)} Б; кадров банк2={len(b2)} банк3={len(b3)}; FG-тайлов={len(fg)}; level {len(level2)} Б')

def trim_scripts(block, nstrings, nscripts, keep):
    """Оставить в блоке строк/скриптов только скрипты keep (остальные -> пустой ACTION_NONE).
    Возвращает новый распакованный блок с базой $C000 (как оригинал)."""
    def rd(o): return block[o] | (block[o+1] << 8)
    st = rd(0) - 0xC000; sc = rd(2) - 0xC000
    strs = [rd(st + 2*i) - 0xC000 for i in range(nstrings)]
    scrs = [rd(sc + 2*i) - 0xC000 for i in range(nscripts)]
    ends = sorted(set(strs + scrs + [len(block)]))
    def span(o):
        nxt = min(e for e in ends if e > o)
        return block[o:nxt]
    out = bytearray(4 + 2*nstrings + 2*nscripts)
    body = bytearray()
    ptrs_s = []; ptrs_c = []
    for o in strs:
        ptrs_s.append(len(out) + len(body)); body += b'\0'      # пустая строка
    empty = len(out) + len(body); body += b'\0'                 # ACTION_NONE
    for i, o in enumerate(scrs):
        if i in keep:
            ptrs_c.append(len(out) + len(body)); body += span(o)
        else:
            ptrs_c.append(empty)
    def wr(o, v): out[o] = (v + 0xC000) & 0xff; out[o+1] = ((v + 0xC000) >> 8) & 0xff
    wr(0, 4); wr(2, 4 + 2*nstrings)
    for i, p in enumerate(ptrs_s): wr(4 + 2*i, p)
    for i, p in enumerate(ptrs_c): wr(4 + 2*nstrings + 2*i, p)
    return bytes(out) + bytes(body)

def build_demo():
    out_dir = BUILD / 'demo'; out_dir.mkdir(parents=True, exist_ok=True)
    sr5 = pletter_depack((SRC / 'tiles_nivel01.SR5.plet1').read_bytes())
    level = (SRC / 'level1.map').read_bytes()
    info = parse_level(level)
    start = info['header'][18] * info['w'] + info['header'][17]
    scr = screens_of(level)[start]
    bg = sorted(set(scr[:160])); fg = sorted(set(scr[160:320]) - {0})
    # тайлы фона + байтовый LUT (номер -> индекс)
    tiles = b''.join(bg_tile_bytes(tile_pixels(sr5, t)) for t in bg)
    lut = [0]*256
    for i, t in enumerate(bg): lut[t] = i
    fgt = b''.join(fg_tile_bytes(tile_pixels(sr5, t)) for t in fg)
    # кадры
    b2 = parse_sprite_asm(SRC / 'sprite_barbaro_1.asm')
    frames = b''.join(sprite_frame_bytes(f) for f in b2[:DEMO_FRAMES])
    # мини-уровень: скрипты только нужные этому экрану
    objs = scr[360:403]
    keep = {objs[0]} | {objs[1+6*k+5] for k in range(7) if objs[1+6*k+1]}
    trimmed = trim_scripts(info['strings']['en'], info['nstrings'], info['nscripts'], keep)
    info2 = dict(info); info2['strings'] = {'en': trimmed, 'es': trimmed}
    # раскладка блока данных
    layout = [('demo_tiles', tiles), ('demo_fg', fgt), ('demo_frames', frames)]
    off = DEMO_DATA_ADDR
    addr = {}
    for name, data in layout:
        addr[name] = off; off += len(data)
    level_addr = off
    mini = build_level(info2, STRING_AREA_DEMO, level_base=level_addr, screen_map=[start]*info['n'], langs=('en',))
    layout.append(('demo_level', mini)); off += len(mini)
    for name, data in layout:
        (out_dir / f'{name}.bin').write_bytes(data)
    lines = ['; сгенерировано build_edd.py --demo (одиночный ROM, без квазидиска)',
             f'\torg ${DEMO_DATA_ADDR:04X}',
             f'DEMO_TILES_BASE\tequ ${addr["demo_tiles"]:04X}',
             f'FG_TILES_BASE\tequ ${addr["demo_fg"]:04X}',
             f'DEMO_FRAMES_BASE\tequ ${addr["demo_frames"]:04X}',
             f'DEMO_LEVEL_ADDR\tequ ${level_addr:04X}']
    for name, data in layout:
        lines.append(f'{name}:\n\tincbin "demo/{name}.bin"')
    lines += palette_lines() + ['', '; LUT тайлов фона: номер -> индекс (адрес = DEMO_TILES_BASE + idx*128); страница!',
                                '\tds ($ + 255) & $FF00 - $', 'demo_tile_lut:']
    for i in range(0, 256, 16):
        lines.append('\tdb ' + ', '.join(str(v) for v in lut[i:i+16]))
    lines += [''] + fg_lut_lines(fg)
    lines.append(f'demo_data_end:\t; = ${off:04X} + палитра/LUT')
    (BUILD / 'demo_data.asm').write_text('\n'.join(lines) + '\n')
    total = off - DEMO_DATA_ADDR + 16 + 512
    print(f'demo: BG-тайлов {len(bg)} ({len(tiles)} Б), FG {len(fg)} ({len(fgt)} Б), кадров {DEMO_FRAMES} ({len(frames)} Б), '
          f'уровень {len(mini)} Б (скрипты {sorted(keep)}), всего ~{total} Б, конец данных ${off:04X}')

if __name__ == '__main__':
    if '--demo' in sys.argv:
        build_demo()
    else:
        build_kvaz()
