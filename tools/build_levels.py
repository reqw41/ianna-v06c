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
import pathlib, subprocess, sys

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

def build_level(n):
    """Собрать EDD уровня n и упаковать. Возвращает (путь, размер)."""
    r = subprocess.run([sys.executable, str(ROOT / 'tools/data/build_edd.py'), f'--level={n}'],
                       capture_output=True, text=True, cwd=str(ROOT))
    if r.returncode != 0:
        raise RuntimeError(f'уровень {n}: build_edd упал\n{r.stdout}{r.stderr}')
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
    out = OUT / f'level{n}.pak'
    out.write_bytes(bytes(table) + bytes(body))
    return out, len(table) + len(body)

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
