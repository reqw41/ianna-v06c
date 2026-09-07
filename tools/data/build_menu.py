#!/usr/bin/env python3
"""Ресурсы фазы меню: экран меню и слайды интро/концовки как дампы VRAM Вектора.
Слайд оригинала = 128x128 из половинки файла intro0N/final0N, вставляется в рамку intro_marco по (64,0).
Дамп VRAM: 32К в порядке [плоскость 0..3][колонка 0..31][L=255..0] — байт VRAM $8000+p*$2000+col*256+L,
линейно по адресам, т.е. просто образ $8000-$FFFF; экранные строки картинки y=0..191 кладутся на строки экрана 32..223 (по центру), L=255-(y+32).
Выход: build/menu_screen.vrm (32К), build/slide0..6.vrm (32К), превью build/menu_slides.png.
Слайды 0..2 — интро, 3..5 — концовка (final01 обе половинки + final02 первая), 6 — экран титров
(credits.SR5 целиком, без рамки; полоса под картинкой залита цветом 1 — как fillArea $11 в end_credits)."""
import sys, pathlib, zlib, struct
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_edd import SRC, sr5_rows, color_perm
from pletter import depack as pletter_depack
ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'

# Цвет MSX -> слот палитры Вектора. Слоты 1..3 отданы четырёхцветному спрайту экрана, поэтому
# фон живёт в 0 и 4..15, а vec_palette (LEVELTAB) хранит цвет MSX i в слоте PERM[i]. Тайлы, спрайты
# и шрифт build_edd кладёт уже переставленными; картинки меню клались СЫРЫМИ, и на экране Вектора
# выходили чужие цвета (жёлтая рамка интро вместо красной). Перестановка одна для всех уровней.
PERM = color_perm(1)
PINV = {}                     # слот -> цвет MSX (для превью: показать, что увидит Вектор)
for i, s in enumerate(PERM):
    PINV.setdefault(s, i)

def img_of(name, lines):
    return sr5_rows(pletter_depack((SRC / f'{name}.SR5.plet1').read_bytes()), lines)

VTOP = 32   # картинка 256x192 по центру экрана Вектора 256x256 (как игровое поле: строки 32..223)

def vram_dump(pix, top=VTOP, band1=False):
    """pix: 192 строк x 256 пикселей (0..15) -> 32К образ $8000-$FFFF (незанятые строки = 0).
    Картинка кладётся со строки `top`, поэтому символьная строка N совпадает с строкой N оригинала MSX.
    band1: полосу под картинкой (строки экрана 224..255 = MSX y 192..223) залить цветом 1 —
    ровно то, что делает fillArea $11 в end_credits: там печатается очередная строка титров."""
    out = bytearray(0x8000)
    for y, row in enumerate(pix):
        L = 255 - (y + top)
        for col in range(32):
            for p in range(4):
                b = 0
                for k in range(8):
                    if (PERM[row[col*8+k]] >> (3-p)) & 1: b |= 0x80 >> k
                out[p*0x2000 + col*256 + L] = b
    if band1:
        v = PERM[1]
        for col in range(32):
            for L in range(0, 256 - 192 - VTOP):
                for p in range(4):
                    if (v >> (3-p)) & 1: out[p*0x2000 + col*256 + L] = 0xFF
    return bytes(out)

def compose_slide(slide):
    marco = img_of('intro_marco', 192)
    out = [r[:] for r in marco]
    for y in range(128):
        for x in range(128):
            out[y][64+x] = slide[y][x]
    return out

def slides():
    """интро 0..2, концовка 3..5 (нарезка: файл 256x128 = две половинки 128x128).
    Как в оригинале: intro = 5 экранов из intro01..03, ending = 3 экрана из final01/final02."""
    res = []
    for name, half in (('intro01',0), ('intro01',1), ('intro02',0),
                       ('final01',0), ('final01',1), ('final02',0)):
        im = img_of(name, 128)
        res.append([[im[y][half*128+x] for x in range(128)] for y in range(128)])
    return res

def main():
    menu = img_of('menu_screen', 192)
    (BUILD / 'menu_screen.vrm').write_bytes(vram_dump(menu))
    sl = slides()
    sheets = [menu]
    for i, s in enumerate(sl):
        comp = compose_slide(s)
        (BUILD / f'slide{i}.vrm').write_bytes(vram_dump(comp))
        sheets.append(comp)
    cred = img_of('credits', 192)                       # слайд 6 — экран титров, целиком, без рамки
    (BUILD / 'slide6.vrm').write_bytes(vram_dump(cred, band1=True))
    sheets.append(cred)
    # превью-лист (по одному PNG в строке — надёжнее)
    plt = (SRC / 'test.plt').read_bytes()
    def to255(i):
        b0, b1 = plt[2*i], plt[2*i+1]
        return (((b0>>4)&7)*255//7, (b1&7)*255//7, (b0&7)*255//7)
    W = 256*3; H = 192*3
    grid = [[(0,0,0)]*W for _ in range(H)]
    for idx, sh in enumerate(sheets):
        gy, gx = divmod(idx, 3)
        for y in range(192):
            for x in range(256):
                grid[gy*192+y][gx*256+x] = to255(PINV[PERM[sh[y][x]]])   # что увидит Вектор
    raw = bytearray()
    for row in grid:
        raw.append(0)
        for pxl in row: raw += bytes(pxl)
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d))
    (BUILD / 'menu_slides.png').write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b''))
    print('menu_screen.vrm + slide0..6.vrm + menu_slides.png готовы')

if __name__ == '__main__':
    main()
