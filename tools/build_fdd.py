#!/usr/bin/env python3
"""Сборка загрузочного ianna.fdd: [дескриптор ПЗУ][ROM][сжатые наборы уровней][экран меню][слайды].
Конвенция штатного ПЗУ Вектора (снята с loader.rom / boots): дескриптор 32 Б в начале дорожки 0
(байт 4 = число КБ для загрузки в $0080.., байт 31 = сумма байтов 0..30 с сеедом $66), вход $0100.
Геометрия 80x2x5x1024 = 800 КБ; дорожка = 10 КБ.

Раскладка дорожек:
   0..3   ROM (32 КБ)
   4..39  сжатые наборы уровней (build/levels/level{N}.pak) — 360 КБ
   40..43 экран меню (дамп VRAM 32 КБ)
   44..63 слайды интро/концовки (5 x 32 КБ)
   64..79 продолжение уровней (160 КБ)
Сырой образ квазидиска (256 КБ) влез бы на дискету ровно один раз, поэтому наборы лежат сжатыми
(aPLib, блоками по 8 КБ). Дорожку начала каждого набора прошиваем прямо в ROM (таблица vfl_dirtab
из vec_fdd.asm) — тогда загрузчику не нужно отдельное чтение каталога.
"""
import pathlib, re, sys, json, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
SEC = 1024
TRACK = 10 * SEC
LEVEL_TRACKS = list(range(4, 40)) + list(range(64, 80))

rom = bytearray((ROOT / 'build/ianna.rom').read_bytes())
assert len(rom) <= 32 * 1024 - 0x80

def check_overlays(n, pak):
    """Оверлеи меню и паузы лежат В КВАЗИДИСКЕ, то есть внутри набора уровня, и вызывают функции
    движка по адресам той сборки ROM, при которой собраны. Пересобрал ROM, не пересобрав наборы —
    оверлей уходит по чужим адресам, игра срывается сразу после загрузки, экран остаётся чёрным
    (ловилось вживую: меню не появлялось, FrameCounter замирал, PC гулял по случайным адресам).
    Отпечаток пишет build_levels.py рядом с набором."""
    meta = pak.with_suffix('.ovl')
    now = {}
    for name in ('menu_ovl.bin', 'pause_ovl.bin', 'menu_ram.bin'):
        f = ROOT / 'build' / name
        if f.exists():
            now[name] = hashlib.md5(f.read_bytes()).hexdigest()
    if not meta.exists():
        sys.exit(f'!! у набора уровня {n} нет отпечатка оверлеев — пересоберите: python3 tools/build_levels.py')
    was = json.loads(meta.read_text())
    if was != now:
        bad = [k for k in now if was.get(k) != now[k]]
        sys.exit(f'!! набор уровня {n} собран с другими оверлеями ({", ".join(bad)}): в квазидиске окажется '
                 f'меню от прежней сборки ROM и игра сорвётся после загрузки.\n'
                 f'   Порядок: python3 tools/build_vec.py && python3 tools/build_levels.py && '
                 f'python3 tools/build_vec.py && python3 tools/build_fdd.py')

# --- разложить наборы уровней и собрать таблицу дорожек ---
dirtab = bytearray(16)
free = list(LEVEL_TRACKS)
placed = []
level_data = []
for n in range(1, 17):
    pak = ROOT / f'build/levels/level{n}.pak'
    if not pak.exists(): continue
    data = pak.read_bytes()
    check_overlays(n, pak)
    ntr = (len(data) + TRACK - 1) // TRACK
    start = None
    for i in range(len(free) - ntr + 1):
        if free[i:i+ntr] == list(range(free[i], free[i] + ntr)):
            start = free[i]; del free[i:i+ntr]; break
    if start is None:
        print(f'!! уровень {n} не влез: нужно {ntr} дорожек подряд'); continue
    dirtab[n-1] = start          # индекс = current_level (0 = уровень 1)
    level_data.append((start, data))
    placed.append((n, start, len(data)))

# --- прошить таблицу дорожек в образ ROM ---
lst = (ROOT / 'build/ianna_vec.lst').read_text(errors='replace')
m = re.search(r'^([0-9A-F]{4}):.*?\svfl_dirtab:', lst, re.M)
if m and placed:
    addr = int(m.group(1), 16)
    off = addr - 0x100           # образ ассемблирован с org $0100
    assert 0 <= off < len(rom), (hex(addr), off, len(rom))
    rom[off:off+16] = dirtab
    print(f'таблица дорожек уровней прошита в ROM по ${addr:04X}: {list(dirtab[:8])}')
elif placed:
    print('!! vfl_dirtab не найден в листинге — таблица не прошита')

img = bytearray(80 * 2 * 5 * SEC)
desc = bytearray(32)
desc[4] = 32                      # 32К -> $0080-$807F (вход $0100)
s = 0x66
for i in range(31): s = (s + desc[i]) & 0xFF
desc[31] = s
img[0:32] = desc
img[0x80:0x80 + len(rom)] = rom
for start, data in level_data:
    img[start*TRACK:start*TRACK + len(data)] = data

menu = ROOT / 'build/menu_screen.vrm'
if menu.exists():
    img[40*TRACK:40*TRACK+0x8000] = menu.read_bytes()
    for i in range(5):
        sl = (ROOT / f'build/slide{i}.vrm').read_bytes()
        base = (44 + i*4) * TRACK
        img[base:base+len(sl)] = sl

out = ROOT / 'build/ianna.fdd'
out.write_bytes(img)
for n, tr, ln in placed:
    print(f'уровень {n}: дорожка {tr}, {ln/1024:.1f} КБ')
print('меню: экран на дорожке 40, слайды на 44/48/52/56/60')
print(f'{out}: {len(img)} Б; ROM {len(rom)} Б')
