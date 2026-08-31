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
# Режим цвета: None = 16 цветов (4 плоскости); 'c8' = 8 цветов, 3 плоскости (VRAM $A000/$C000/$E000,
# плоскость 0 $8000-$9FFF свободна, бит 3 индекса всегда 0, палитра зеркалится pal[c|8]=pal[c]);
# 'ref8' = ЭТАЛОН для оракула: те же переназначенные данные (значения-слоты 0..7), но в 4-плоскостных
# форматах для текущего 16-цветного движка — плоскости 1..3 совпадают с c8 байт в байт.
C8MODE = 'c8' if '--colors8' in sys.argv else ('ref8' if '--ref8' in sys.argv else None)
from pletter import depack as pletter_depack
from aplib import depack as aplib_depack
from level_tools import parse_level, build_level, relocate_strings, pack

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'ref/msx2/src'
BUILD = ROOT / 'build'
STRING_AREA_KVAZ = 0x6B00   # vars наверху ОЗУ (см. build_vec.py); хвост таблиц упирается ровно в $8000 (драйвер НГМД занял +256 кода)
STRING_AREA_C8 = 0x6C00     # c8: rev256/slot_tab в свободной плоскости 0 ($8000) — vars выше, коду +512 Б
BG_TILES_BASE = 0x8000      # страница 0: 256 тайлов x 128 = 32К
FG_TILES_BASE = 0x5D00      # страница 0 (до 35 FG-тайлов x 256)
BANK_FILE = {2: 'sprite_barbaro_1', 3: 'sprite_barbaro_2', 7: 'sprite_esqueleto', 8: 'sprite_orc', 9: 'sprite_mummy',
             10: 'sprite_troll', 11: 'sprite_dalgurak', 12: 'sprite_rollingstone', 13: 'sprite_caballerorenegado',
             14: 'sprite_golem_inf', 15: 'sprite_golem_sup', 16: 'sprite_ogro_inf', 17: 'sprite_ogro_sup',
             18: 'sprite_minotauro_inf', 19: 'sprite_minotauro_sup', 20: 'sprite_demonio_inf', 21: 'sprite_demonio_sup'}
# Раскладка банков спрайтов (страница ROM MSX -> страница квазидиска, база, предел) по уровням; база кратна 256.
# Таблица vec_bank_tab генерируется в gen_data.asm. Банк = 41 кадр x 576 = 23616 Б ($5C40).
LEVEL_BANKS = {
    1: [(2, 0, 0x0000, 0x5D00), (3, 1, 0xA300, 0x10000), (7, 1, 0x0000, 0x8000), (8, 2, 0x0000, 0x6000),
        (9, 2, 0x6000, 0x10000), (12, 3, 0x2800, 0xA000)],
    # уровень 2, оценка сцены с големом (экран 4,6): в 256К не помещаются скелет/орк/тролль/камень — на их
    # экранах будут кадры варвара (см. ANALYSIS.md, «великаны»)
    2: [(2, 0, 0x0000, 0x5D00), (3, 1, 0x0000, 0x8000), (14, 2, 0x0000, 0x5D00), (15, 2, 0x5D00, 0xC000)],
}
LEVEL_MUSIC = [1, 5, 3, 4, 5, 6, 7, 8]   # music_levels (music.asm): уровень N -> music-level{M}.mus
STRING_AREA_DEMO = 0x7400   # демо: string_area 512 Б, vars короче (до $8000 ровно)
DEMO_DATA_ADDR = 0x0200     # блок данных демо-ROM сразу за jp по $0100
DEMO_FRAMES = 10            # idle, gira, camina x6, cae x2 (см. sprites.asm)

def planes_of_row(pixels, pmap=None, nplanes=4):
    """pmap: список 16->значение (слот); nplanes=3 — плоскости несут биты 2..0 (VRAM 1..3)."""
    if pmap is not None: pixels = [pmap[v] for v in pixels]
    out = [[] for _ in range(nplanes)]
    for i in range(0, len(pixels), 8):
        chunk = pixels[i:i+8]
        for p in range(nplanes):
            bit = nplanes - 1 - p
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

def n_planes(): return 3 if C8MODE == 'c8' else 4
def bg_tile_bytes(rows, pmap=None):
    pl = [planes_of_row(r, pmap, n_planes()) for r in rows]
    out = bytearray()
    for p in range(n_planes()):
        for col in range(2):
            for y in range(16):
                out.append(pl[y][p][col])
    return bytes(out)

def fg_tile_bytes(rows, pmap=None):
    pl = [planes_of_row(r, pmap, n_planes()) for r in rows]
    mk = [mask_of_row(r) for r in rows]     # маска по исходному пикселю (0 = прозрачно), не по слоту
    out = bytearray()
    for p in range(n_planes()):
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

FRAME_BYTES = 576   # 3 колонки x 32 строки x 6 байт

def sprite_frame_bytes(frame, pmap=None):
    """576 Б, строка 6 Б. 16 цветов: [p0,маска,p1,p2,p3,пропуск], маска = ~(p0|..|p3).
    c8 (3 плоскости, биты 2..0): [pl1,маска,pl2,pl3,пропуск,0]; ref8: 4 плоскости переназначенных
    значений (плоскость 0 = нули). Маска и пропуск ВСЕГДА по исходному пикселю (0 = прозрачно):
    слот 0 в спрайте — полноценный чёрный. Адрес кадра: MSX n*384 -> n*576."""
    np = n_planes()
    pl = [planes_of_row(r, pmap, np) for r in frame]
    out = bytearray()
    for col in range(3):
        trans = [all(v == 0 for v in frame[y][col*8:col*8+8]) for y in range(32)] if pmap is not None else \
                [all(pl[y][p][col] == 0 for p in range(np)) for y in range(32)]
        for y in range(31, -1, -1):
            pv = [pl[y][p][col] for p in range(np)]
            if pmap is not None:
                mask = 0
                for k, v in enumerate(frame[y][col*8:col*8+8]):
                    if v == 0: mask |= 0x80 >> k
            else:
                mask = (~(pv[0] | pv[1] | pv[2] | pv[3])) & 0xFF
            skip = 0
            yy = y - 1
            while yy >= 0 and trans[yy]: skip += 1; yy -= 1
            if skip < 2: skip = 0          # код пропуска стоит ~250 тактов — окупается от двух строк
            if np == 3:
                out += bytes((pv[0], mask, pv[1], pv[2], 0, skip))   # пропуск последним: регистры пропуска в движке те же
            else:
                out += bytes((pv[0], mask, pv[1], pv[2], pv[3], skip))
    assert len(out) == FRAME_BYTES
    return bytes(out)

def column_blob(pixels_rows, x0, w_cols, y0, h, pmap=None):
    """[p][col][row 0..h-1] — для стекового блита сверху вниз (DCR L). c8: 3 плоскости (биты 2..0)."""
    np = n_planes()
    out = bytearray()
    for p in range(np):
        for col in range(w_cols):
            for y in range(h):
                chunk = pixels_rows[y0+y][x0+col*8: x0+col*8+8]
                if pmap is not None: chunk = [pmap[v] for v in chunk]
                b = 0
                for k, v in enumerate(chunk):
                    if (v >> (np-1-p)) & 1: b |= 0x80 >> k
                out.append(b)
    return bytes(out)

def sr5_rows(sr5, h):
    return [[(sr5[y*128+x//2] >> 4) if x % 2 == 0 else (sr5[y*128+x//2] & 15) for x in range(256)] for y in range(h)]

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

def bank_tab_lines(banks):
    by = {b: (pg, base) for b, pg, base, _ in banks}
    lines = ['; Таблица банков MSX 2..21 -> (порт стека квазидиска, старший байт базы) кадров спрайтов; неизвестные -> стр.0 $0000',
             'vec_bank_tab:']
    for b in range(2, 22):
        pg, base = by.get(b, (0, 0))
        lines.append(f'\tdb KV_STK_P{pg},${base >> 8:02X}\t; {b} {BANK_FILE.get(b, "-")}{"" if b in by else " (нет)"}')
    return lines

def palette_lines():
    pal = msx_palette((SRC / 'test.plt').read_bytes())
    return ['vec_palette:', '\tdb ' + ', '.join(f'${c:02X}' for c in pal)]

BANK_ENEMY = {7:20, 8:21, 9:22, 10:23, 11:26, 12:24, 13:25, 14:27, 15:27, 16:28, 17:28, 18:29, 19:29, 20:30, 21:30}
def build_kvaz(level_no=1, start=None):
    pages = [bytearray(65536) for _ in range(4)]
    banks = LEVEL_BANKS[level_no]
    if C8MODE:
        import colors8 as c8x
        msx16, pm_tiles, scrsys, scrpals = c8x.level_system(SRC, level_no)
        pm_panel = [0] + [c8x.nearest(msx16[c], c8x.SLOT_RGB) for c in range(1, 16)]
        def bank_pmap(bank):
            if bank in (2, 3, 4, 5, 6): return [c8x.HREMAP[c] for c in range(16)]
            ident = c8x.ENEMY_SLOT6.get(BANK_ENEMY.get(bank), (5, 5, 5))
            pal7 = c8x.SLOT_RGB + [ident]          # слоты 0..6; слот 7 врагу не даём (меняется по экранам)
            return [0] + [c8x.nearest(msx16[c], pal7) for c in range(1, 16)]
    else:
        pm_tiles = pm_panel = None; scrpals = None
        def bank_pmap(bank): return None
    sr5 = pletter_depack((SRC / f'tiles_nivel{level_no:02d}.SR5.plet1').read_bytes())
    assert len(sr5) == 32768
    # Раскладка (кадры спрайтов по 576 Б, банки по 41 кадру = 23616 Б; см. vec_bank_tab в vec_vdp.asm):
    #   стр.0: банк 2 варвар $0000-$5C40, FG $5D00, тайлы BG $8000-$FFFF (256 x 128)
    #   стр.1: банк 7 скелет $0000-$5C40, карта $8000 (8.6К), банк 3 варвар $A200-$E340
    #   стр.2: банк 8 орк $0000, банк 9 мумия $6000
    #   стр.3: банк 12 камень $2800; шрифт/панель/оружие $0000-$27FF, пул $A000, музыка $C980, эффекты $D980
    for n in range(256):
        b = bg_tile_bytes(tile_pixels(sr5, n), pm_tiles)   # c8: 96 Б, шаг 128 (хвост нули)
        pages[0][BG_TILES_BASE + n*128: BG_TILES_BASE + n*128 + len(b)] = b
    def put_bank(page, base, name, limit, pmap):
        frames = parse_sprite_asm(SRC / f'{name}.asm')
        assert base % 256 == 0, (name, hex(base))
        assert base + len(frames)*FRAME_BYTES <= limit, (name, len(frames))
        for k, fr in enumerate(frames):
            pages[page][base + k*FRAME_BYTES: base + (k+1)*FRAME_BYTES] = sprite_frame_bytes(fr, pmap)
    for bank, page, base, limit in banks:
        put_bank(page, base, BANK_FILE[bank], limit, bank_pmap(bank))
    # страница 3: шрифт $0000 (64 символа x 32 Б), панель $1000 (256x32), оружие $2000 (4 x 192), вкл/выкл $2400 (2 x 288)
    font = sr5_rows(pletter_depack((SRC / 'font.SR5.plet1').read_bytes()), 16)
    for c in range(64):
        b = column_blob(font, (c % 32)*8, 1, (c // 32)*8, 8, pm_panel); pages[3][c*32:c*32+len(b)] = b
    from font_ru import extra_glyphs                     # позиции 64..95 А..Я, 96 стрелка (коды 96..128)
    for k, g in enumerate(extra_glyphs(font)):
        b = column_blob(g, 0, 1, 0, 8, pm_panel); pages[3][(64+k)*32:(64+k)*32+len(b)] = b
    # шрифт МЕНЮ (резной, с обводкой) — 128 глифов по $E000 страницы 3, читается стековым режимом
    from font_ru import menu_glyphs
    mfont = sr5_rows(pletter_depack((SRC / 'menu_font.SR5.plet1').read_bytes()), 16)
    for k, g in enumerate(menu_glyphs(mfont)):
        b = column_blob(g, 0, 1, 0, 8, pm_panel); pages[3][0xE000 + k*32: 0xE000 + k*32 + len(b)] = b
    panel = sr5_rows(pletter_depack((SRC / 'marcador.SR5.plet1').read_bytes()), 32)
    b = column_blob(panel, 0, 32, 0, 32, pm_panel); pages[3][0x1000:0x1000+len(b)] = b
    armas = sr5_rows(pletter_depack((SRC / 'armas.SR5.plet1').read_bytes()), 24)
    for w in range(4):
        b = column_blob(armas, w*32, 3, 0, 16, pm_panel); pages[3][0x2000 + w*192: 0x2000 + w*192 + len(b)] = b
    for k, x0 in enumerate((128, 152)):
        b = column_blob(armas, x0, 3, 0, 24, pm_panel); pages[3][0x2400 + k*288: 0x2400 + k*288 + len(b)] = b
    # страница 3: музыка уровня 1 по $C980 и эффекты по $D980 — РОВНО как music_addr/music_sfx на MSX
    # (внутри .mus абсолютные указатели под эти адреса); читаются через окно $A000-$DFFF (пул — ниже $C800)
    pages[3][0xC800:0xC802] = b'IA'   # маркер «квазидиск загружен» для vec_fdd_load
    mus = (SRC / f'music-level{LEVEL_MUSIC[level_no-1]}.mus').read_bytes(); sfx = (SRC / 'iannafx.mus').read_bytes()
    assert len(mus) <= 0x1000 and len(sfx) <= 0x0680
    pages[3][0xC980:0xC980+len(mus)] = mus
    pages[3][0xD980:0xD980+len(sfx)] = sfx
    level = (SRC / f'level{level_no}.map').read_bytes()
    fg = sorted(set().union(*(set(s[160:320]) for s in screens_of(level))) - {0})
    for i, t in enumerate(fg):
        addr = FG_TILES_BASE + i*256
        b = fg_tile_bytes(tile_pixels(sr5, t), pm_tiles)   # c8: 192 Б, шаг 256
        pages[0][addr:addr+len(b)] = b
    assert FG_TILES_BASE + len(fg)*256 <= BG_TILES_BASE
    info = parse_level(level)
    from texts_ru import LEVEL_TEXTS, build_block        # русский блок строк на месте испанского (language=0)
    info['strings']['es'] = build_block(info['strings']['en'], info['nstrings'], info['nscripts'], LEVEL_TEXTS[level_no])
    if start:                                              # стартовый экран (x,y) — для стендов
        hdr = bytearray(info['header']); hdr[17], hdr[18] = start; info['header'] = bytes(hdr)
    sa = STRING_AREA_C8 if C8MODE == 'c8' else STRING_AREA_KVAZ
    level2 = build_level(info, sa)                        # строки/скрипты -> string_area Вектора
    lvl_end = 0x8000 + len(level2)
    for bank, page, base, limit in banks:                  # карта не должна лечь на банк страницы 1
        assert page != 1 or lvl_end <= base or base >= lvl_end or limit <= 0x8000, (bank, hex(lvl_end))
    pages[1][0x8000:lvl_end] = level2
    scrpal_addr = 0
    if C8MODE:
        scrpal_addr = (lvl_end + 15) & ~15
        blob = bytearray()
        for pal in scrpals:
            blob += bytes(((c[2] >> 1) << 6) | (c[1] << 3) | c[0] for c in pal)
        for bank, page, base, limit in banks:
            assert page != 1 or base >= scrpal_addr + len(blob) or limit <= 0x8000, 'палитры легли на банк'
        pages[1][scrpal_addr:scrpal_addr+len(blob)] = blob
    # фаза меню: оверлей + блоб (стр.3 $8440/$9800), песни меню/интро (стр.2 $C000/$D000)
    ovl = BUILD / 'menu_ovl.bin'; blob = BUILD / 'menu_ram.bin'
    if ovl.exists() and blob.exists() and not C8MODE:
        b = ovl.read_bytes(); pages[3][0x8440:0x8440+len(b)] = b
        b = blob.read_bytes(); pages[3][0x9800:0x9800+len(b)] = b
        pz = BUILD / 'pause_ovl.bin'
        if pz.exists():
            b = pz.read_bytes(); pages[3][0x8B00:0x8B00+len(b)] = b
        for slot, mus in ((0xC000, 'music-menu.mus'), (0xD000, 'music-intro.mus')):
            mb = (SRC / mus).read_bytes(); assert len(mb) <= 0x1000
            pages[2][slot:slot+len(mb)] = mb
    assert all(len(p) == 65536 for p in pages), [len(p) for p in pages]
    edd = b''.join(bytes(p) for p in pages)
    (BUILD / 'ianna.edd').write_bytes(edd)
    lines = ['; сгенерировано build_edd.py (квазидиск' + (f', режим {C8MODE}' if C8MODE else '') + ')',
             f'FG_TILES_BASE\tequ ${FG_TILES_BASE:04X}\t; страница 0', f'BG_TILES_BASE\tequ ${BG_TILES_BASE:04X}\t; страница 0']
    if C8MODE:
        if C8MODE == 'c8': lines.append('C8\tequ 1\t\t; 8 цветов: 3 плоскости (VRAM $A000/$C000/$E000), $8000-$9FFF свободна')
        lines.append(f'VEC_SCRPAL\tequ ${scrpal_addr:04X}\t; таблица палитр экранов (8 Б на экран, окно уровня)')
        st = info['header'][18] * info['w'] + info['header'][17]
        pal0 = [(((c[2] >> 1) << 6) | (c[1] << 3) | c[0]) for c in scrpals[st]]
        lines += ['vec_palette:', '\tdb ' + ', '.join(f'${c:02X}' for c in pal0 + pal0) + '\t; стартовый экран, зеркалом (бит 3 = 0)']
    else:
        lines += palette_lines()
    lines += [''] + bank_tab_lines(banks) + [''] + fg_lut_lines(fg)
    if C8MODE == 'c8':
        lines += ['; карта «цвет кода 0..15 -> слот» для fillArea (шкалы панели); лежит сразу за fg_tile_lut (страница)',
                  'vec_color_map:', '\tdb ' + ', '.join(str(v) for v in pm_panel)]
    (BUILD / 'gen_data.asm').write_text('\n'.join(lines) + '\n')
    print(f'ianna.edd:{" "+C8MODE if C8MODE else ""} уровень {level_no}{" старт "+str(start) if start else ""}; {len(edd)} Б; банки спрайтов: {[b for b,*_ in banks]} по {FRAME_BYTES} Б/кадр; FG-тайлов={len(fg)}; level {len(level2)} Б')

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
        lv = int(next((a[8:] for a in sys.argv if a.startswith('--level=')), '1'))
        st = next((tuple(int(v) for v in a[8:].split(',')) for a in sys.argv if a.startswith('--start=')), None)
        build_kvaz(lv, st)
