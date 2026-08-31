#!/usr/bin/env python3
"""Сборка загрузочного ianna.fdd: [дескриптор ПЗУ][ROM с raw $80][EDD с дорожки 4].
Конвенция штатного ПЗУ Вектора (снята с loader.rom / boots): дескриптор 32 Б в начале
дорожки 0 (байт 4 = число КБ для загрузки в $0080.., байт 31 = сумма байтов 0..30 с сеедом $66),
вход $0100 (raw $80). Геометрия 80x2x5x1024."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
rom = (ROOT / 'build/ianna.rom').read_bytes()
edd = (ROOT / 'build/ianna.edd').read_bytes()
assert len(rom) <= 32 * 1024 - 0x80 and len(edd) == 262144
img = bytearray(80 * 2 * 5 * 1024)
desc = bytearray(32)
desc[0:4] = b'\x00\x00\x00\x00'
desc[4] = 32                      # 32К -> $0080-$807F (вход $0100)
s = 0x66
for i in range(31): s = (s + desc[i]) & 0xFF
desc[31] = s
img[0:32] = desc
img[0x80:0x80 + len(rom)] = rom
img[4 * 10240:4 * 10240 + len(edd)] = edd     # дорожка 4+ — EDD, читает vec_fdd_load
menu = ROOT / 'build/menu_screen.vrm'
if menu.exists():
    img[40*10240:40*10240+0x8000] = menu.read_bytes()
    for i in range(5):
        sl = (ROOT / f'build/slide{i}.vrm').read_bytes()
        base = (44 + i*4) * 10240
        img[base:base+len(sl)] = sl
    print('меню: экран на дорожке 40, слайды на 44/48/52/56/60 (шаг 4 дорожки, 32К каждый)')
out = ROOT / 'build/ianna.fdd'
out.write_bytes(img)
print(f'{out}: {len(img)} Б; ROM {len(rom)} Б, EDD с дорожки 4 (raw {4*10240})')
