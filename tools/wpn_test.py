#!/usr/bin/env python3
"""Стенд «герой с выбранным оружием»: подкачка страницы спрайтов с дискеты (fdd_banks.fb_wpn).

  python3 tools/wpn_test.py            — смена оружия в паузе (быстро, ~1 с)
  python3 tools/wpn_test.py --real     — подкачка ПРИ ЗАГРУЗКЕ УРОВНЯ, набор читается с дискеты
  ключи: --changes=N (смен подряд), --weapon=W (какое оружие подложить к загрузке), --png=КАТАЛОГ

Что где проверяется.
  Обычный прогон — ПАУЗА. Смена оружия обязана быть МГНОВЕННОЙ и безобидной: панель меняет
    название и значок, поле не трогается вовсе, палитра не гаснет, чтения с дискеты нет.
    (Чтение прямо из паузы снято 2026-09-08: на живой машине оно рвало картинку, а headless-модель
    дефект не воспроизводила. Стенд сторожит, что оно не вернулось незаметно: вход в wpn_load
    по WPN_ORG считается отдельно и обязан быть нулевым.)
  --real — ЗАГРУЗКА УРОВНЯ. Квазидиск пуст, набор читается с дискеты, как на железе; перед
    вызовом vec_fdd_load подкладываем player_current_weapon (движок читает его в fb_wpn).
    Проверяем, что страница героя в квазидиске побайтно совпала с build_edd.weapon_blob(оружие)
    и что соседние кадры банка 2 (0..13 и 37..40, общие у всех видов) целы.

Почему стенд отдельный. Обычный путь «дойти до игры по дискете» — это чтение 45 КБ набора и
распаковка 256 КБ квазидиска питоновским i8080: 10 с на прогон. Для сцены паузы это лишнее,
поэтому по умолчанию квазидиск заполняется готовым build/ianna.edd (маркер 'IA' в стр.3 $C800 —
vec_fdd_load набор тогда не перечитывает), а образ дискеты всё равно подан: из него берётся ROM
с прошитыми vfl_dirtab/vec_wpntab. Прогон 1 с вместо десятков минут.

Перед запуском собрать образ:
  python3 tools/build_vec.py && python3 tools/build_levels.py &&
  python3 tools/build_vec.py && python3 tools/build_fdd.py
"""
import sys, os, pathlib, functools, io, contextlib
print = functools.partial(print, flush=True)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
NCH = int(next((o[10:] for o in OPTS if o.startswith('--changes=')), '3'))
WANT = int(next((o[9:] for o in OPTS if o.startswith('--weapon=')), '1'))
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
WPN_ORG = 0xE800                # куда оверлей паузы копировал подкачку; сейчас не должен звать


def track_palette(cpu):
    """НАСТОЯЩАЯ палитра железа (порты $02/$0C). Теневая копия vec_palette в ОЗУ для этой
    проверки не годится: подкачка гасила палитру портами, ОЗУ при этом не трогая, и снимок
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


def make_cpu(keys, before_fdd=None):
    cpu = rv.make_cpu(keys)
    mp = SYM['vec_menu_phase']                 # фазу меню глушим: слайды интро тут ни при чём
    call = bytes((0xCD, mp & 0xFF, mp >> 8))
    for a in range(0x100, 0x8000 - 3):
        if bytes(cpu.mem[a:a + 3]) == call: cpu.mem[a:a + 3] = b'\x00\x00\x00'
    track_palette(cpu)
    if before_fdd is not None:
        # player_current_weapon движок читает в fb_wpn (bl_wpn) ПОСРЕДИ загрузки набора, а
        # инициализирует позже — подкладываем значение на входе в загрузчик, как это делает
        # переход на следующий уровень с оружием в руках.
        # Стартовая загрузка с заставкой идёт через bl_load (vec_bootload.asm) — ловим оба входа.
        fdd = {SYM['vec_fdd_load'], SYM.get('bl_load', -1)}; cw = SYM['player_current_weapon']
        done = [False]
        orig = cpu.step
        def step():
            if not done[0] and cpu.pc in fdd:
                cpu.mem[cw] = before_fdd; done[0] = True
            orig()
        cpu.step = step
    return cpu


def test_load():
    """--real: страница героя, положенная при ЗАГРУЗКЕ УРОВНЯ, против эталона."""
    import build_edd as B
    with contextlib.redirect_stdout(io.StringIO()):
        B.build_kvaz(1)
    pg2, base2, blob2 = B.BANK_BLOBS[2]
    kvbase = pg2 * 65536 + base2
    at = kvbase + B.WPN_OFF
    ref = B.weapon_blob(WANT)
    print(f'банк 2: стр.{pg2} база ${base2:04X}; кадр 14 по ${base2 + B.WPN_OFF:04X}, '
          f'подкачка {len(ref)} Б; оружие при загрузке {WANT}')
    keys = []
    cpu = make_cpu(keys, before_fdd=WANT)
    rv.start_game(cpu, keys, SYM)
    frames(cpu, 5, keys)
    shot(cpu, 'wpn_load')
    page = bytes(cpu.kvaz[at:at + len(ref)]) == ref
    pre = bytes(cpu.kvaz[kvbase:at]) == blob2[:B.WPN_OFF]
    post = bytes(cpu.kvaz[at + len(ref):kvbase + len(blob2)]) == blob2[B.WPN_OFF + len(ref):]
    print(f'страница == эталон weapon_blob({WANT}): {page}; кадры 0..13 целы: {pre}; '
          f'кадры 37..40 целы: {post}')
    return page and pre and post


def test_pause():
    """Смена оружия в паузе: мгновенная, поле не трогается, дискета не читается."""
    import build_edd as B
    with contextlib.redirect_stdout(io.StringIO()):
        B.build_kvaz(1)
    pg2, base2, blob2 = B.BANK_BLOBS[2]
    kvbase = pg2 * 65536 + base2
    keys = []
    cpu = make_cpu(keys)
    rv.start_game(cpu, keys, SYM)
    cpu.mem[SYM['player_available_weapons']:SYM['player_available_weapons'] + 4] = b'\x01\x01\x01\x01'
    frames(cpu, 3, keys)
    base_vram = bytes(cpu.mem[0x8000:0x10000])
    kv0 = bytes(cpu.kvaz)
    pal0 = list(cpu.hwpal)
    shot(cpu, 'wpn_0before')

    frames(cpu, 3, keys, ('h',))
    frames(cpu, 5, keys, ())
    shot(cpu, 'wpn_1pause')

    hit = [0]                       # входов в снятую подкачку (обязан остаться нулём)
    dark = [False]
    def hook(c):
        if c.pc == WPN_ORG: hit[0] += 1
    ok = True
    for k in range(NCH):
        frames(cpu, 3, keys, ('down',), hook=hook)
        keys[:] = []
        for i in range(12):
            frames(cpu, 1, keys, (), hook=hook)
            if not any(cpu.hwpal): dark[0] = True
        w = cpu.mem[SYM['player_current_weapon']]
        pal = list(cpu.hwpal) == pal0
        ok &= pal
        print(f'смена {k+1}: оружие {w}; палитра не гасла: {pal}; кадров ожидания: 15')
    shot(cpu, 'wpn_2after')

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
    # Банк героя в квазидиске обязан остаться нетронутым: пауза его больше не переписывает.
    # Считать «сколько байт изменилось во всём квазидиске» бесполезно — движок штатно гоняет пул
    # супертайлов (стр.3 $A000+) и состояние музыки, это полторы тысячи байт за десяток кадров.
    bank = bytes(cpu.kvaz[kvbase:kvbase + len(blob2)]) == kv0[kvbase:kvbase + len(blob2)]
    print(f'после выхода из паузы: поле отличается в {fld} Б, панель в {pan} Б'
          + (f' (габарит x {box[0]}..{box[1]}, y {box[2]}..{box[3]})' if pan else ''))
    print(f'экран гас: {dark[0]} (не должен); входов в wpn_load: {hit[0]} (не должно быть); '
          f'банк 2 в квазидиске цел: {bank}')
    return ok and fld == 0 and not dark[0] and hit[0] == 0 and bank


def main():
    ok = test_load() if REAL else test_pause()
    print('ИТОГ:', 'OK' if ok else 'ПРОВАЛ')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
