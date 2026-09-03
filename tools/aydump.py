#!/usr/bin/env python3
"""ОРАКУЛ ЗВУКА: дамп всех записей в регистры AY на детерминированном игровом прогоне.

  python3 tools/aydump.py <rom> <lst> <edd> <сцена> <кадров> [--route=...] [--out=файл]
                          [--cycles] [--rand]

<сцена> — либо «X,Y» (стартовый экран уровня, как в cmpbuild), либо «menu»: без старта игры,
меню/интро (там играет своя песня music_menu и свои эффекты).

Зачем не «кадр эмулятора»: кадр headless-стенда кончается по HALT, а HALT наступает раньше у
более быстрого кода — привязка к номеру кадра эмулятора сделала бы дамп зависимым от скорости.
Поэтому запись адресуется НОМЕРОМ ВЫЗОВА ПЛЕЕРА (MUSIC_Play из ISR): плеер обязан на N-м своём
вызове выдать ту же последовательность (регистр, значение), какой бы быстрой ни была сборка.
Записи вне плеера (atInit/atStop/atSfxPlay из FX_Play) относятся к текущему номеру вызова.

Порты AY Вектора: $15 — выбор регистра, $14 — данные (см. build_vec.py: out (#a0)/(#a1)).

ГПСЧ нейтрализуется, как в cmpbuild --norand (иначе любая правка байтов ROM сдвигает случайные
числа, траектория расходится и эффекты играют в другие моменты). --rand отключает нейтрализацию.

Печатает: число вызовов плеера, число записей в AY, md5 потока; с --cycles ещё и такты внутри
MUSIC_Play (среднее на вызов и всего) по модели тактов Вектора из tools/profile_vec.py.
"""
import sys, os, re, pathlib, hashlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
if len(A) < 5:
    sys.exit(__doc__)
ROM, LST, EDD, SCENE, NFRAMES = A[0], A[1], A[2], A[3], int(A[4])
ROUTE = next((o[8:] for o in OPTS if o.startswith('--route=')), 'right')
OUT = next((o[6:] for o in OPTS if o.startswith('--out=')), None)
CYCLES = '--cycles' in OPTS
NORAND = '--rand' not in OPTS
os.environ['IANNA_EDD'] = EDD
if 'demo' in pathlib.Path(ROM).name:
    sys.exit('ОТКАЗ: в демо-ROM музыки нет (DEMO выкидывает music.asm/arkos.asm из сборки).')

sys.argv = [sys.argv[0]]
sys.path.insert(0, 'tools')
import run_vec as rv
rv.STEP_BUDGET = 400000

if CYCLES:
    src = open('tools/profile_vec.py').read()
    i = src.index('# Такты ВЕКТОРА'); j = src.index('keys = []')
    exec(src[i:j])

sym = rv.load_syms(pathlib.Path(LST))
keys = []
cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes()
cpu.mem[0x100:0x100 + len(rom)] = rom
cpu.pc = 0x100


def norand_patch(cpu, sym):
    """Тело random -> 'A := randData += $4D' (как в cmpbuild --norand)."""
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))


# --- перехват записей в AY поверх штатного out_handler стенда ---
stream = []          # (номер вызова плеера, регистр, значение)
state = {'call': 0, 'reg': 0}
_out = cpu.out_handler


def out_handler(port, val):
    if port == 0x15:
        state['reg'] = val
    elif port == 0x14:
        stream.append((state['call'], state['reg'], val))
    return _out(port, val)


cpu.out_handler = out_handler

MP = sym['MUSIC_Play']
if SCENE == 'menu':
    # меню/интро: игру не стартуем, ROM грузим как есть (patch_menu уже применён в make_cpu —
    # при наборе без оверлея меню фаза заглушена, тогда сцена вырождается: об этом предупредим)
    mo = pathlib.Path('build/menu_ovl.bin')
    head = mo.read_bytes()[:16] if mo.exists() else b''
    if not head or bytes(cpu.kvaz[3 * 65536 + 0x8440: 3 * 65536 + 0x8450]) != head:
        print('ВНИМАНИЕ: в наборе нет оверлея меню — сцена «menu» бессмысленна (нужен набор уровня 1)')
    if NORAND: norand_patch(cpu, sym)
else:
    if NORAND: norand_patch(cpu, sym)
    rv.START = tuple(int(v) for v in SCENE.split(','))
    rv.start_game(cpu, keys, sym)
    keys.clear()
    keys.extend(k for k in ROUTE.split('+') if k != 'none')

tot_cyc = 0
in_music = False
sp0 = 0
step = cpu.step
mem = cpu.mem
for _ in range(NFRAMES):
    c = 0
    while not cpu.halted and c < rv.STEP_BUDGET:
        pc = cpu.pc
        if pc == MP:
            state['call'] += 1
            if CYCLES and not in_music:
                in_music = True; sp0 = cpu.sp
        if CYCLES and in_music:
            if cpu.sp > sp0:
                in_music = False
            else:
                tot_cyc += CYC[mem[pc]]
        step(); c += 1
    cpu.halted = False
    if cpu.ie:
        cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38

blob = b''.join(bytes((r, v)) + state_call.to_bytes(2, 'little')
                for state_call, r, v in stream)
h = hashlib.md5(blob).hexdigest()[:12]
byreg = collections.Counter(r for _, r, _ in stream)
print(f'сцена {SCENE}, кадров {NFRAMES}: вызовов плеера {state["call"]}, записей в AY {len(stream)}, md5 {h}')
print('  регистры:', ' '.join(f'R{r}={n}' for r, n in sorted(byreg.items())))
if CYCLES:
    n = max(1, state['call'])
    print(f'  такты в MUSIC_Play: всего {tot_cyc}, на вызов {tot_cyc / n:.0f}, на тик (6 кадров) {tot_cyc / n * 6:.0f}')
if OUT:
    with open(OUT, 'w') as f:
        for c, r, v in stream:
            f.write(f'{c} {r} {v}\n')
    print('  дамп:', OUT)
