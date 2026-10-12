#!/usr/bin/env python3
"""Сборка загрузочного ianna.fdd: [дескриптор ПЗУ][ROM][сжатые наборы уровней][экран меню][слайды].
Конвенция штатного ПЗУ Вектора (снята с loader.rom / boots): дескриптор 32 Б в начале дорожки 0
(байт 4 = число КБ для загрузки в $0080.., байт 31 = сумма байтов 0..30 с сеедом $66), вход $0100.
Геометрия 80x2x5x1024 = 800 КБ; дорожка = 10 КБ.

Раскладка дорожек:
   0..3   ROM (32 КБ) + экран меню в хвосте дорожки 3
   4..72  сжатые наборы уровней (build/levels/level{N}.pak) и библиотека банков
   73..79 семь слайдов интро/концовки (по одной дорожке на слайд)
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
SEC = 1024
TRACK = 10 * SEC
LEVEL_TRACKS = list(range(4, 73))   # один непрерывный блок: наборы уровней по 5-9 дорожек каждый
MENU_TRACK, MENU_SEC = 3, 3         # экран меню — в хвосте дорожек ROM (образ кончается на 32-м секторе)
PIC_TRACK = 73                      # семь слайдов — по дорожке на каждый (73..79)

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
    for name in ('menu_ovl.bin', 'pause_ovl.bin', 'menu_ram.bin', 'arkos.bin'):
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
        blob = pack_picture((ROOT / f'build/slide{i}.vrm').read_bytes())
        img[(PIC_TRACK + i)*TRACK:(PIC_TRACK + i)*TRACK + len(blob)] = blob
        placed_pics.append((i + 1, PIC_TRACK + i, len(blob)))

out = ROOT / 'build/ianna.fdd'
out.write_bytes(img)
for n, tr, ln in placed:
    print(f'уровень {n}: дорожка {tr}, {ln/1024:.1f} КБ')
for i, tr, ln in placed_pics:
    print(f'{"экран меню" if i == 0 else f"слайд {i-1}":11s} дорожка {tr}, {ln/1024:.1f} КБ (сжат)')
print(f'{out}: {len(img)} Б; ROM {len(rom)} Б')
