#!/usr/bin/env python3
"""Стенд смены оружия в паузе: подкачка страницы героя с дискеты (wpn_load + fdd_banks).

  python3 tools/wpn_test.py [--changes=3] [--real] [--png=КАТАЛОГ]

Что проверяет за один прогон:
  * страница героя в квазидиске побайтно совпала с эталоном build_edd.weapon_blob(оружие);
  * соседние кадры банка 2 (0..13 и 37..40) целы — подкачка не залезла за свои границы;
  * палитра железа вернулась к исходной (снимаем порты $02/$0C, а не теневую копию в ОЗУ);
  * поле после выхода из паузы совпало с исходным кадром, панель отличается только блоком оружия;
  * сколько кадров занимают чтение и возврат картинки.

Почему нужен отдельный стенд. Обычный путь «дойти до игры по дискете» — это чтение 45 КБ
набора и распаковка 256 КБ квазидиска питоновским i8080: 10 с на прогон и невозможность
цикла правок. Поэтому по умолчанию квазидиск заполняется ГОТОВЫМ build/ianna.edd (в нём
маркер 'IA' в стр.3 $C800, и vec_fdd_load набор с дискеты не перечитывает), а образ дискеты
всё равно подан: из него берётся ROM (там прошиты vfl_dirtab и vec_wpntab) и читается сама
библиотека страниц героя — 6 секторов. Прогон 1 с. Ключ --real проверяет, что быстрый путь
не врёт: квазидиск пуст, набор читается с дискеты, результат тот же (10 с).

Перед запуском собрать образ:
  python3 tools/build_vec.py && python3 tools/build_levels.py &&
  python3 tools/build_vec.py && python3 tools/build_fdd.py
"""
import sys, os, re, pathlib, functools, io, contextlib
print = functools.partial(print, flush=True)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
NCH = int(next((o[10:] for o in OPTS if o.startswith('--changes=')), '3'))
PNG = next((o[6:] for o in OPTS if o.startswith('--png=')), None)
REAL = '--real' in OPTS

os.environ.setdefault('IANNA_FDD', str(ROOT / 'build/ianna.fdd'))
if REAL:                        # честный путь: квазидиск пуст, набор читается с дискеты
    zero = ROOT / 'build/_wpn_zero.edd'
    if not zero.exists() or zero.stat().st_size != 262144:
        zero.write_bytes(bytes(262144))
    os.environ['IANNA_EDD'] = str(zero)
else:
    os.environ.setdefault('IANNA_EDD', str(ROOT / 'build/ianna.edd'))

sys.argv = [sys.argv[0]]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/data'))
import run_vec as rv

SYM = rv.load_syms(ROOT / 'build/ianna_vec.lst')
# Конец подкачки — метка wl_bail: через неё проходят оба выхода wpn_load (и «прочитали»,
# и «дисковода нет»). Адрес берём из листинга, чтобы не протухал при правках.
WL_END = int(re.search(r'^wl_bail\s+=\s+\$([0-9A-F]{4})',
                       (ROOT / 'build/wpn_load.bin.lst').read_text(errors='replace'), re.M).group(1), 16)


def track_palette(cpu):
    """НАСТОЯЩАЯ палитра железа (порты $02/$0C). Теневая копия vec_palette в ОЗУ для этой
    проверки не годится: подкачка гасит палитру портами, ОЗУ при этом не трогая, и снимок
    по vec_palette показывал буфер загрузки в старых цветах там, где экран чёрен."""
    cpu.hwpal = [0] * 16
    st = {'idx': 0, 'n': 0}
    orig = cpu.out_handler
    def out(port, val):
        if port == 0x02: st['idx'] = val & 15; st['n'] = 0
        elif port == 0x0C:
            st['n'] += 1
            if st['n'] == 1: cpu.hwpal[st['idx']] = val
        orig(port, val)
    cpu.out_handler = out


def frames(cpu, n, keys=None, k=(), hook=None):
    """Кадр = до HALT или бюджета инструкций, затем RST7. Прерывание отдаём, только когда оно
    РАЗРЕШЕНО: бюджет кадра часто кончается внутри блока di..ei (vec_ovl_call), и тогда кадр за
    кадром машина вставала в одну и ту же точку с ie=0 — ISR не звался, vec_keys не обновлялся,
    и меню паузы навсегда считало клавишу H нажатой."""
    if keys is not None: keys[:] = list(k)
    for _ in range(n):
        c = 0
        while not cpu.halted and c < rv.STEP_BUDGET:
            if hook: hook(cpu)
            cpu.step(); c += 1
        cpu.halted = False
        c = 0
        while not cpu.ie and c < 4000 and not cpu.halted:
            if hook: hook(cpu)
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie:
            cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38


def shot(cpu, name):
    if not PNG: return
    d = pathlib.Path(PNG); d.mkdir(parents=True, exist_ok=True)
    rv.render(bytes(cpu.mem[0x8000:0x10000]), list(cpu.hwpal), str(d / f'{name}.png'))
    print('   PNG:', d / f'{name}.png')


def main():
    import build_edd as B
    with contextlib.redirect_stdout(io.StringIO()):
        B.build_kvaz(1)
    pg2, base2, blob2 = B.BANK_BLOBS[2]
    kvbase = pg2 * 65536 + base2
    at = kvbase + B.WPN_OFF
    ref = {w: B.weapon_blob(w) for w in range(4)}
    print(f'банк 2: стр.{pg2} база ${base2:04X}; кадр 14 по ${base2 + B.WPN_OFF:04X}, '
          f'подкачка {len(ref[0])} Б')

    keys = []
    cpu = rv.make_cpu(keys)
    mp = SYM['vec_menu_phase']                 # фазу меню глушим: слайды интро тут ни при чём
    call = bytes((0xCD, mp & 0xFF, mp >> 8))
    for a in range(0x100, 0x8000 - 3):
        if bytes(cpu.mem[a:a + 3]) == call: cpu.mem[a:a + 3] = b'\x00\x00\x00'
    track_palette(cpu)
    rv.start_game(cpu, keys, SYM)
    cpu.mem[SYM['player_available_weapons']:SYM['player_available_weapons'] + 4] = b'\x01\x01\x01\x01'
    frames(cpu, 3, keys)
    base_vram = bytes(cpu.mem[0x8000:0x10000])
    pal0 = list(cpu.hwpal)
    shot(cpu, 'wpn_0before')
    assert bytes(cpu.kvaz[kvbase:kvbase + len(blob2)]) == blob2, 'банк 2 в квазидиске не совпал с эталоном'

    frames(cpu, 3, keys, ('h',))
    frames(cpu, 5, keys, ())
    pause_vram = bytes(cpu.mem[0x8000:0x10000])
    shot(cpu, 'wpn_1pause')
    bad = 0
    for k in range(NCH):
        done, lit, fr = [None], [None], [0]
        def hook(c):
            if c.pc == WL_END and done[0] is None: done[0] = fr[0]
        frames(cpu, 3, keys, ('down',), hook=hook)
        keys[:] = []
        for i in range(400):
            fr[0] = i
            frames(cpu, 1, keys, (), hook=hook)
            if done[0] is not None and lit[0] is None and any(cpu.hwpal): lit[0] = i
            if lit[0] is not None and i >= lit[0] + 3: break
        w = cpu.mem[SYM['player_current_weapon']]
        page = bytes(cpu.kvaz[at:at + len(ref[w])]) == ref[w]
        pre = bytes(cpu.kvaz[kvbase:at]) == blob2[:B.WPN_OFF]
        post = bytes(cpu.kvaz[at + len(ref[w]):kvbase + len(blob2)]) == blob2[B.WPN_OFF + len(ref[w]):]
        pal = list(cpu.hwpal) == pal0
        bad += not (page and pre and post and pal)
        print(f'смена {k+1}: оружие {w}; чтение {done[0]} кадров, картинка вернулась на {lit[0]} '
              f'({((lit[0] or 0) + 3) / 50:.1f} с); страница == эталон: {page}; '
              f'кадры 0..13 целы: {pre}; кадры 37..40 целы: {post}; палитра вернулась: {pal}')
    shot(cpu, 'wpn_2after')
    print('VRAM отличается от кадра паузы в',
          sum(1 for x, y in zip(pause_vram, cpu.mem[0x8000:0x10000]) if x != y), 'Б')

    frames(cpu, 3, keys, ('h',))
    frames(cpu, 25, keys, ())
    shot(cpu, 'wpn_3resume')
    after = bytes(cpu.mem[0x8000:0x10000])
    fld = pan = 0
    box = [999, -1, 999, -1]
    for pl in range(4):
        for off in range(8192):
            if base_vram[pl*8192 + off] != after[pl*8192 + off]:
                x, y = (off >> 8) * 8, 255 - (off & 255)
                if y < 160: fld += 1
                else:
                    pan += 1
                    box = [min(box[0], x), max(box[1], x + 7), min(box[2], y), max(box[3], y)]
    print(f'после выхода из паузы: поле отличается в {fld} Б, панель в {pan} Б'
          + (f' (габарит x {box[0]}..{box[1]}, y {box[2]}..{box[3]})' if pan else ''))
    ok = bad == 0 and fld == 0
    print('ИТОГ:', 'OK' if ok else 'ПРОВАЛ')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
