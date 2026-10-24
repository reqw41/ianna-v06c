#!/usr/bin/env python3
"""Сборка загрузочного ianna.fdd: [дескриптор ПЗУ][ROM][сжатые наборы уровней][экран меню][слайды].
Конвенция штатного ПЗУ Вектора (снята с loader.rom / boots): дескриптор 32 Б в начале дорожки 0
(байт 4 = число КБ для загрузки в $0080.., байт 31 = сумма байтов 0..30 с сеедом $66), вход $0100.
Дискета — МикроДОС на 82 дорожки (2x5x1024 на дорожку, 839 680 Б): раскладка и каталог — в
tools/disk_layout.py. Первый файл каталога — IANNA.COM (копия ROM): с ним игру запускают из CP/M 4.0 и
со стартового экрана ПЗУ Вектора Турбо+.
Картинки (экран меню и семь слайдов) лежат СЖАТЫМИ и по одной на дорожку: дамп VRAM — это 32 КБ,
и вшестером они занимали 24 дорожки из 80, из-за чего девять наборов уровней (660 КБ) на дискету
не помещались. Каждая плоскость жмётся отдельно (aPLib, 1-2.6 КБ), в начале дорожки — заголовок
из четырёх смещений по два байта. Читает и распаковывает mb_slide_i (menu_ram.asm).
Сырой образ квазидиска (256 КБ) влез бы на дискету ровно один раз, поэтому наборы лежат сжатыми
(aPLib, блоками по 8 КБ). Дорожку начала каждого набора прошиваем прямо в ROM (таблица vfl_dirtab
из vec_fdd.asm) — тогда загрузчику не нужно отдельное чтение каталога.
"""
import pathlib, re, sys, json, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import disk_layout as DL            # раскладка дискеты МикроДОС — см. tools/disk_layout.py
SEC, TRACK = DL.SEC, DL.TRACK
LEVEL_TRACKS = DL.LEVEL_TRACKS       # один непрерывный блок: наборы уровней по 5-9 дорожек каждый
MENU_TRACK, MENU_SEC = DL.MENU_TRACK, DL.MENU_SEC   # экран меню — в хвосте загрузочной области
PIC_TRACK = DL.PIC_TRACK             # семь слайдов — по дорожке на каждый

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
    for name in ('menu_ovl.bin', 'pause_ovl.bin', 'menu_ram.bin', 'arkos.bin', 'arkos_dat.bin'):
        f = ROOT / 'build' / name
        if f.exists():
            now[name] = hashlib.md5(f.read_bytes()).hexdigest()
    # FDDCOPY — примитивы ВГ93 из образа ROM, лежащие копией в наборе (см. build_levels)
    now['FDDCOPY'] = hashlib.md5(bytes(rom[0x7E00 - 0x100:0x7E00 - 0x100 + 512])).hexdigest()
    if not meta.exists():
        sys.exit(f'!! у набора уровня {n} нет отпечатка оверлеев — пересоберите: python3 tools/build_levels.py')
    was = json.loads(meta.read_text())
    if was != now:
        bad = [k for k in now if was.get(k) != now[k]]
        sys.exit(f'!! набор уровня {n} собран с другой сборкой ROM ({", ".join(bad)}): в квазидиске окажется '
                 f'меню (или примитивы ВГ93) от прежней сборки, и игра сорвётся после загрузки.\n'
                 f'   Порядок: python3 tools/build_vec.py && python3 tools/build_levels.py && '
                 f'python3 tools/build_vec.py && python3 tools/build_fdd.py')

# --- разложить наборы уровней и собрать таблицу дорожек ---
dirtab = bytearray(10)          # vfl_dirtab: ds 10 (уровни 1..8, attract-демо, секретный)
free = list(LEVEL_TRACKS)
placed = []
level_data = []
for n in range(1, 10):
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
    # индекс = current_level: level1..8 -> 0..7; индекс 8 — attract-демо оригинала (набора нет),
    # секретный level9 -> 9 (LEVEL_PAGE в ianna.asm: level1..8, level0, level9)
    dirtab[9 if n == 9 else n-1] = start
    level_data.append((start, data))
    placed.append((n, start, len(data)))

# --- прошить таблицу дорожек в образ ROM ---
lst = (ROOT / 'build/ianna_vec.lst').read_text(errors='replace')
m = re.search(r'^([0-9A-F]{4}):.*?\svfl_dirtab:', lst, re.M)
if m and placed:
    addr = int(m.group(1), 16)
    off = addr - 0x100           # образ ассемблирован с org $0100
    assert 0 <= off < len(rom), (hex(addr), off, len(rom))
    rom[off:off+len(dirtab)] = dirtab
    print(f'таблица дорожек уровней прошита в ROM по ${addr:04X}: {list(dirtab[:10])}')
elif placed:
    print('!! vfl_dirtab не найден в листинге — таблица не прошита')

img = bytearray(DL.DISK)
desc = bytearray(32)
desc[4] = 32                      # 32К -> $0080-$807F (вход $0100)
desc[5:31] = DL.DPB               # блок параметров диска МикроДОС (для CP/M и плагина FAR)
s = 0x66
for i in range(31): s = (s + desc[i]) & 0xFF
desc[31] = s
img[0:32] = desc
img[0x80:0x80 + len(rom)] = rom
for start, data in level_data:
    img[start*TRACK:start*TRACK + len(data)] = data

# --- библиотека банков: каждый банк лежит на дискете ОДИН раз, наборы ссылаются на него рецептом ---
# Один и тот же тролль нужен пяти уровням; раньше он лежал в каждом наборе, потому что банк в наборе
# стоит по своему для этого уровня адресу. Теперь наборы идут без банков (см. build_levels), а куда
# какой банк положить в квазидиске, сказано в рецепте — дорожку и сектор проставляем здесь.
# Банк читается одним заходом и дорожку не пересекает, то есть это раскладка по корзинам по 10
# секторов. Кладём БОЛЬШИЕ ВПЕРЁД в первую подходящую дорожку (first-fit-decreasing): 25 банков
# укладываются в 18 дорожек вместо 20 у последовательной раскладки, а лишние две дорожки нужны
# под слайды концовки. Порядок в рецептах от этого не зависит — позиция каждого банка своя.
import json
lib_at = {}
track_free = {tr: 10 for tr in free}     # свободных секторов в дорожке (счёт с сектора 1)
track_free[DL.LIB_TAIL[0]] = DL.LIB_TAIL[1]  # хвост дорожки за IANNA.COM
# Хвост ПОСЛЕДНЕЙ дорожки каждого набора тоже свободен: наборы кратны сектору, а не дорожке, и
# в сумме девять хвостов дают 56 КБ. Без них четыре страницы героя (22 сект.) в библиотеку уже
# не помещались: целых свободных дорожек в области уровней остаётся всего пара.
for start, data in level_data:
    n = (len(data) + SEC - 1) // SEC
    last = start + (n - 1) // 10
    used = ((n - 1) % 10) + 1
    if used < 10:
        track_free[last] = 10 - used
paks = sorted((ROOT / 'build/levels').glob('bank*.pak'), key=lambda p: -p.stat().st_size)
for pak in paks:
    data = pak.read_bytes()
    nsec = (len(data) + SEC - 1) // SEC
    assert nsec <= 10, f'банк {pak.name} больше дорожки: {len(data)} Б'
    # Банк может начинаться и на стороне 1 (сектор 6..10): vfl_seek переводит его в сторону 1, сектор 1..5
    tr = next((t for t in sorted(track_free) if track_free[t] >= nsec), None)
    if tr is None:
        sys.exit(f'!! библиотека не влезла: {pak.name} ({nsec} сект.), свободно {sum(track_free.values())} сект.')
    sc = 10 - track_free[tr] + 1
    at = tr*TRACK + (sc - 1)*SEC
    assert not any(img[at:at + len(data)]), f'библиотека наехала на чужие данные: {pak.name} дор.{tr} сект.{sc}'
    img[at:at + len(data)] = data
    lib_at[pak.stem[4:]] = (tr, sc)      # bank{key}.pak -> ключ
    track_free[tr] -= nsec
# Позиции страниц героя (ключи w0..w3) — в таблицу vec_wpntab образа ROM: fb_wpn берёт оттуда
# дорожку и сектор по player_current_weapon. Прошиваем так же, как vfl_dirtab, но уже В ОБРАЗЕ:
# ROM лёг в img выше, а библиотека раскладывается только сейчас.
mw = re.search(r'^([0-9A-F]{4}):.*?\svec_wpntab:', lst, re.M)
if mw:
    waddr = int(mw.group(1), 16)
    woff = 0x80 + waddr - 0x100
    wt = bytearray(8)
    for w in range(4):
        if f'w{w}' in lib_at:
            tr, sc = lib_at[f'w{w}']
            wt[2*w], wt[2*w + 1] = tr, sc
    img[woff:woff + 8] = wt
    print(f'страницы героя прошиты в ROM по ${waddr:04X}: ' +
          ', '.join(f'{w}=дор.{wt[2*w]}/сект.{wt[2*w+1]}' for w in range(4)))
else:
    print('!! vec_wpntab не найден в листинге — страницы оружия не прошиты')

print(f'библиотека банков: {len(lib_at)} банков, '
      f'{sum((ROOT / "build/levels" / f"bank{k}.pak").stat().st_size for k in lib_at)/1024:.0f} КБ')

for n, start, ln in placed:                     # прошить позиции банков в рецепты наборов
    rec = ROOT / f'build/levels/level{n}.rec.json'
    if not rec.exists(): continue
    for e in json.loads(rec.read_text()):
        tr, sc = lib_at[e['key']]
        at = start*TRACK + e['off']
        img[at] = tr; img[at + 1] = sc

def pack_picture(vrm):
    """Дамп VRAM 32 КБ -> [4 смещения по 2 байта][сжатые плоскости подряд]. Плоскость жмётся
    отдельно: распаковщик кладёт каждую по своему адресу VRAM, а целиком 32 КБ распаковывать
    некуда — приёмник перекрыл бы буфер источника."""
    import subprocess
    tin, tout = ROOT / 'build/_pic.bin', ROOT / 'build/_pic.ap'
    head, body = bytearray(), bytearray()
    for pl in range(4):
        tin.write_bytes(vrm[pl*8192:(pl+1)*8192])
        r = subprocess.run([str(ROOT / 'tools/bin/apack'), str(tin), str(tout)], capture_output=True)
        assert r.returncode == 0, r.stdout + r.stderr
        blob = tout.read_bytes()
        head += bytes((len(head) if False else (8 + len(body)) & 0xFF, (8 + len(body)) >> 8))
        body += blob
    out = bytes(head) + bytes(body)
    assert len(out) <= TRACK, f'картинка не влезла в дорожку: {len(out)} Б'
    return out

# Слайды интро 1 и 2 отличаются от нулевого только серединой: рамка с колоннами и подложка текста те же.
# На дискете от них лежит одна середина, а игра меняет её, не трогая остального (vec_intro.asm).
CENTER_SLIDES = (1, 2)
C_COL0, C_NCOL, C_ROW0, C_NROW = 8, 16, 32, 128      # колонки 8..23, строки экрана 32..159

def pack_center(vrm, base):
    """Середина слайда -> [4 смещения][4 сжатые плоскости по 2048 Б]: по колонкам, в колонке сверху вниз
    (L = 255 - строка экрана, убывает). Вне середины слайд обязан совпадать с нулевым."""
    import subprocess
    inside = lambda k: C_COL0 <= ((k >> 8) & 31) < C_COL0 + C_NCOL and C_ROW0 <= 255 - (k & 255) < C_ROW0 + C_NROW
    bad = [k for k in range(32768) if vrm[k] != base[k] and not inside(k)]
    assert not bad, f'слайд отличается от нулевого вне середины: {len(bad)} Б, первый ${0x8000 + bad[0]:04X}'
    tin, tout = ROOT / 'build/_pic.bin', ROOT / 'build/_pic.ap'
    head, body = bytearray(), bytearray()
    for pl in range(4):
        raw = bytes(vrm[pl*8192 + c*256 + (255 - y)] for c in range(C_COL0, C_COL0 + C_NCOL) for y in range(C_ROW0, C_ROW0 + C_NROW))
        tin.write_bytes(raw)
        r = subprocess.run([str(ROOT / 'tools/bin/apack'), str(tin), str(tout)], capture_output=True)
        assert r.returncode == 0, r.stdout + r.stderr
        head += bytes(((8 + len(body)) & 0xFF, (8 + len(body)) >> 8))
        body += tout.read_bytes()
    out = bytes(head) + bytes(body)
    assert len(out) <= 0x1800, f'середина слайда не влезла в 6 КБ перед буфером распаковки: {len(out)} Б'
    return out

placed_pics = []
menu = ROOT / 'build/menu_screen.vrm'
if menu.exists():
    blob = pack_picture(menu.read_bytes())
    at = MENU_TRACK*TRACK + (MENU_SEC - 1)*SEC
    assert len(blob) <= TRACK - (MENU_SEC - 1)*SEC, f'экран меню не влез в хвост дорожки ROM: {len(blob)}'
    assert at >= 0x80 + len(rom), 'экран меню наехал на ROM'
    img[at:at + len(blob)] = blob
    placed_pics.append((0, MENU_TRACK, len(blob)))
    for i in range(7):
        vrm = (ROOT / f'build/slide{i}.vrm').read_bytes()
        blob = pack_center(vrm, (ROOT / 'build/slide0.vrm').read_bytes()) if i in CENTER_SLIDES else pack_picture(vrm)
        img[(PIC_TRACK + i)*TRACK:(PIC_TRACK + i)*TRACK + len(blob)] = blob
        placed_pics.append((i + 1, PIC_TRACK + i, len(blob)))

# заставка стартовой загрузки (build_vec.cover_asm): вне наборов, на своей дорожке
cover = (ROOT / 'build/cover.bin').read_bytes()
ct = DL.COVER_TRACK * TRACK
assert not any(img[ct:ct + 2 * TRACK]), 'дорожки заставки заняты'
img[ct:ct + len(cover)] = cover
print(f'заставка    дорожки {DL.COVER_TRACK}..{DL.COVER_TRACK + 1}, {len(cover)/1024:.1f} КБ (сжата)')

# --- каталог МикроДОС: IANNA.COM (копия ROM уже с прошитыми таблицами) и IANNA.DAT поверх всего остального ---
com = bytes(img[0x80:0x80 + len(rom)])
ca = DL.COM_LBA * SEC
assert not any(img[ca:ca + len(com)]), 'IANNA.COM наехал на данные'
img[ca:ca + len(com)] = com
assert DL.COM_LBA * SEC + len(com) <= DL.DAT_LBA * SEC, 'IANNA.COM не влез до IANNA.DAT'
assert not any(img[DL.DIR_LBA * SEC:DL.DATA_LBA * SEC]), 'каталог наехал на данные'
img[DL.DIR_LBA * SEC:DL.DATA_LBA * SEC] = DL.msdos_dir([
    (('IANNA', 'COM'), DL.COM_LBA, len(com)),
    (('IANNA', 'DAT'), DL.DAT_LBA, (2 * (DL.DSM + 1) + DL.DIR_LBA - DL.DAT_LBA) * SEC),
])

out = ROOT / 'build/ianna.fdd'
out.write_bytes(img)
for n, tr, ln in placed:
    print(f'уровень {n}: дорожка {tr}, {ln/1024:.1f} КБ')
for i, tr, ln in placed_pics:
    print(f'{"экран меню" if i == 0 else f"слайд {i-1}":11s} дорожка {tr}, {ln/1024:.1f} КБ (сжат)')
print(f'{out}: {len(img)} Б; ROM {len(rom)} Б')
