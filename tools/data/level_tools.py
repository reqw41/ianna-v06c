"""Перестройка карты уровня Ianna под другой адрес string_area и/или другую базу карты.

Формат карты (ianna.asm LoadLevel):
  0-7 'LEVELXXX', 8-9 offset строк EN, 10-11 offset строк ES, 12 nscreens, 13 w, 14 h,
  15 nscripts, 16 nstrings, 17-18 стартовый экран, 19-20 стартовые координаты, 21 резерв,
  22.. таблица адресов экранов (nscreens слов, АБСОЛЮТНЫЕ адреса при карте по $8000),
  далее aPLib-блоки: экраны, строки EN, строки ES.
Блок строк (распакованный, рассчитан на string_area=$C000):
  [ptr таблицы строк][ptr таблицы скриптов][nstrings ptr][nscripts ptr][строки][скрипты]
"""
import subprocess, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from aplib import depack

ROOT = pathlib.Path(__file__).resolve().parents[2]
APACK = ROOT / 'tools/bin/apack'
MSX_STRING_AREA = 0xC000

def pack(data):
    tmp = ROOT / 'build/_pack_in.bin'; out = ROOT / 'build/_pack_out.bin'
    tmp.write_bytes(data)
    r = subprocess.run([str(APACK), str(tmp), str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)
    packed = out.read_bytes()
    dec, _ = depack(packed, 0)
    assert dec == data, 'apultra: распаковка не совпала'
    return packed

def relocate_strings(block, nstrings, nscripts, new_base):
    """Сдвинуть все абсолютные указатели блока строк с $C000 на new_base."""
    b = bytearray(block)
    delta = new_base - MSX_STRING_AREA
    def rd(o): return b[o] | (b[o+1] << 8)
    def wr(o, v): b[o] = v & 0xff; b[o+1] = (v >> 8) & 0xff
    st = rd(0) - MSX_STRING_AREA; sc = rd(2) - MSX_STRING_AREA
    wr(0, rd(0) + delta); wr(2, rd(2) + delta)
    for i in range(nstrings): wr(st + 2*i, rd(st + 2*i) + delta)
    for i in range(nscripts): wr(sc + 2*i, rd(sc + 2*i) + delta)
    return bytes(b)

def parse_level(level):
    n = level[12]
    addrs = [level[22+2*i] | (level[23+2*i] << 8) for i in range(n)]
    screens = []
    for a in addrs:
        off = a - 0x8000
        _, end = depack(level, off)
        screens.append(level[off:end])
    packs = {}
    for key, o in (('en', 8), ('es', 10)):
        a = level[o] | (level[o+1] << 8)
        dec, end = depack(level, a - 0x8000)
        packs[key] = dec
    return {'n': n, 'w': level[13], 'h': level[14], 'nscripts': level[15], 'nstrings': level[16],
            'header': bytes(level[:22]), 'screens': screens, 'strings': packs}

def build_level(info, string_base, level_base=0x8000, screen_map=None, langs=('en', 'es')):
    """Собрать карту заново. screen_map: список индексов исходных экранов для каждой
    ячейки (None = как было). langs: какие блоки строк включать ('es' указывает на 'en', если нет)."""
    n = info['n']
    idx = screen_map if screen_map is not None else list(range(n))
    assert len(idx) == n
    hdr = bytearray(info['header'])
    table_off = 22
    body_off = table_off + 2*n
    body = bytearray()
    # экраны: уникальные копии
    placed = {}
    addrs = []
    for k in idx:
        if k not in placed:
            placed[k] = body_off + len(body)
            body += info['screens'][k]
        addrs.append(level_base + placed[k])
    str_addr = {}
    for lang in ('en', 'es'):
        src = lang if lang in langs else 'en'
        if src not in str_addr:
            rel = relocate_strings(info['strings'][src], info['nstrings'], info['nscripts'], string_base)
            str_addr[src] = level_base + body_off + len(body)
            body += pack(rel)
        str_addr[lang] = str_addr[src]
    hdr[8] = str_addr['en'] & 0xff; hdr[9] = str_addr['en'] >> 8
    hdr[10] = str_addr['es'] & 0xff; hdr[11] = str_addr['es'] >> 8
    table = b''.join(bytes([a & 0xff, a >> 8]) for a in addrs)
    return bytes(hdr) + table + bytes(body)
