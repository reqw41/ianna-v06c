#!/usr/bin/env python3
"""Наборы уровней для дискеты: build_edd на каждый уровень -> 32 блока по 8К -> aPLib -> build/levels/.

Квазидиск (256К) целиком на дискету не влезает больше одного раза: 9 уровней = 2.3 МБ при ёмкости 800 КБ.
Зато набор жмётся втрое (уровень 1: 256 -> 78 КБ, уровень 2: 256 -> 64 КБ), поэтому на дискете лежат
сжатые блоки, а загрузчик распаковывает их в квазидиск (aPLib-распаковщик уже есть в ROM).

Формат файла уровня (build/levels/level{N}.pak):
  [32 записи по 2 байта: длина сжатого блока (0 = блок целиком нулевой)][сжатые блоки подряд]
Блок = 8192 Б квазидиска: блок i -> страница i/8, смещение (i%8)*8192.

Использование: build_levels.py [номера уровней]   (по умолчанию — все, для которых есть LEVEL_BANKS)
"""
import pathlib, subprocess, sys, hashlib, json

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/data'))
APACK = ROOT / 'tools/bin/apack'
OUT = ROOT / 'build/levels'
BLOCK = 8192

def pack_block(data, tmp_in, tmp_out):
    if not any(data):
        return b''                      # нулевой блок: длина 0, данных нет
    tmp_in.write_bytes(data)
    r = subprocess.run([str(APACK), str(tmp_in), str(tmp_out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)
    return tmp_out.read_bytes()

RECIPE = 128        # фиксированное место под рецепт банков в заголовке набора

def build_level(n):
    """Собрать EDD уровня n БЕЗ банков спрайтов и упаковать; банки уходят в общую библиотеку.
    Возвращает (путь, размер)."""
    import os
    sys.path.insert(0, str(ROOT / 'tools/data'))
    import build_edd as B
    B.SKIP_BANKS = True
    B.build_kvaz(n)
    banks = dict(B.BANK_BLOBS)          # банк -> (страница, база, содержимое)
    two = set(B.BANK_2PLANE_BY_LEVEL.get(n, ()))
    edd = (ROOT / 'build/ianna.edd').read_bytes()
    assert len(edd) == 262144, len(edd)
    OUT.mkdir(parents=True, exist_ok=True)
    tmp_in, tmp_out = ROOT / 'build/_pk.bin', ROOT / 'build/_pk.ap'
    table, body = bytearray(), bytearray()
    for i in range(0, len(edd), BLOCK):
        blob = pack_block(edd[i:i+BLOCK], tmp_in, tmp_out)
        assert len(blob) < 0x10000
        table += bytes([len(blob) & 0xFF, len(blob) >> 8])
        body += blob
    # рецепт: какой банк из библиотеки куда положить. Дорожку и сектор проставит build_fdd —
    # он один знает, где на дискете легла библиотека.
    rec, keys = bytearray([len(banks)]), []
    for b, (pg, base, blob) in sorted(banks.items()):
        key = f'{b}_{"4" if b in two else "16"}'
        keys.append({'key': key, 'off': 64 + 1 + len(rec) - 1})
        rec += bytes([0, 0, 0x10 | (pg << 2) | (1 if b in two else 0), base & 0xFF, base >> 8])
        lib_write(key, blob)
    assert len(rec) <= RECIPE, f'рецепт не влез: {len(rec)} Б'
    out = OUT / f'level{n}.pak'
    out.write_bytes(bytes(table) + bytes(rec).ljust(RECIPE, b'\x00') + bytes(body))
    (OUT / f'level{n}.rec.json').write_text(json.dumps(keys, indent=1))
    # Отпечаток оверлеев, попавших в набор. Оверлеи меню и паузы живут В КВАЗИДИСКЕ и зовут функции
    # движка по адресам ТОЙ сборки ROM, при которой собраны. Пересобрал ROM, не пересобрав наборы —
    # оверлей уходит по чужим адресам, и игра срывается сразу после загрузки (экран чёрный).
    out.with_suffix('.ovl').write_text(json.dumps(overlay_digest(), indent=1))
    return out, len(table) + len(body)

LIB = {}            # ключ банка -> сжатый файл библиотеки

def lib_write(key, blob):
    """Банк в библиотеку: куски по 8 КБ, каждый сжат отдельно (распаковщик работает через буфер
    в 8 КБ). Заголовок файла: число кусков и их длины."""
    path = OUT / f'bank{key}.pak'
    if path.exists(): return path
    tmp_in, tmp_out = ROOT / 'build/_bk.bin', ROOT / 'build/_bk.ap'
    raw = [blob[i:i+BLOCK] for i in range(0, len(blob), BLOCK)]
    parts = [pack_block(r, tmp_in, tmp_out) for r in raw]
    head = bytearray([len(parts)])
    for pz, r in zip(parts, raw):              # по четыре байта на кусок: сжатая и распакованная длины
        head += bytes([len(pz) & 0xFF, len(pz) >> 8, len(r) & 0xFF, len(r) >> 8])
    path.write_bytes(bytes(head) + b''.join(parts))
    LIB[key] = path
    return path

def overlay_digest():
    d = {}
    for name in ('menu_ovl.bin', 'pause_ovl.bin', 'menu_ram.bin'):
        f = ROOT / 'build' / name
        if f.exists():
            d[name] = hashlib.md5(f.read_bytes()).hexdigest()
    return d

if __name__ == '__main__':
    from build_edd import LEVEL_BANKS
    levels = [int(a) for a in sys.argv[1:] if a.isdigit()] or sorted(LEVEL_BANKS)
    total = 0
    for n in levels:
        path, size = build_level(n)
        total += size
        print(f'уровень {n}: {path.name} {size:6d} Б ({size/1024:5.1f} КБ, {(size+10239)//10240} дорожек)')
    print(f'итого {total/1024:.1f} КБ на {len(levels)} уровней; дискета 800 КБ')
    # ВАЖНО: build_edd уровнезависим — он же генерирует gen_data.asm (палитра, таблица банков, LUT
    # передних тайлов), которую вкомпилировали в ROM. После цикла по уровням gen_data остаётся от
    # ПОСЛЕДНЕГО уровня, и ROM, собранный после этого, будет ссылаться на чужие адреса банков
    # (герой в прыжке рисовался скелетом). Восстанавливаем состояние для уровня 1.
    subprocess.run([sys.executable, str(ROOT / 'tools/data/build_edd.py')], capture_output=True, cwd=str(ROOT))
    print('gen_data.asm и build/ianna.edd восстановлены для уровня 1')
