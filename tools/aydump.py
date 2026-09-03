#!/usr/bin/env python3
"""ОРАКУЛ ЗВУКА: дамп всех записей в регистры AY на детерминированном игровом прогоне.

  python3 tools/aydump.py <rom> <lst> <edd> <сцена> <кадров> [--route=...] [--out=файл]
                          [--fxlog=файл] [--cycles] [--rand]

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

--out пишет поток «вызов регистр значение», --fxlog — события «вызов K номер»: L=MUSIC_Load с
номером песни, F=FX_Play с номером эффекта, S=MUSIC_Stop, Z=игра ИЗВНЕ плеера обнулила теневые
_atVAR_Reg6/Reg11/Reg12 (LoadScreen после MUSIC_Load — «сбросить шум и огибающую от песни
меню/интро», см. build_vec.py). Z — часть интерфейса: любой новый плеер обязан держать эти три
теневых байта по этим же меткам. Этой парой файлов сверяется модель
tools/arkos_model.py --check-game: она загружает ту же песню в тот же момент и отыгрывает те же
эффекты в те же кадры. Перехват включён С ЗАГРУЗКИ (прогрев тоже пишется) — иначе неизвестно,
сколько кадров песня уже отыграла к началу окна.

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
FXLOG = next((o[8:] for o in OPTS if o.startswith('--fxlog=')), None)
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
FXP = sym['FX_Play']
MLD = sym['MUSIC_Load']
MST = sym['MUSIC_Stop']
R6 = sym['_atVAR_Reg6']
PLO, PHI = sym['atPlay'], sym['atSfxStop'] + 64      # диапазон кода плеера
_r6 = [cpu.mem[R6]]
fxlog = []          # (номер вызова, 'L'|'F'|'S', параметр)
tot_cyc = [0]
_in_music = [False, 0]


def watch(pc):
    """Перехват на каждой инструкции: события плеера и такты внутри MUSIC_Play."""
    if pc == MP:
        state['call'] += 1
        if CYCLES and not _in_music[0]:
            _in_music[0] = True; _in_music[1] = cpu.sp
    elif pc == FXP:
        fxlog.append((state['call'], 'F', cpu.a))
    elif pc == MLD:
        fxlog.append((state['call'], 'L', cpu.a))
    elif pc == MST:
        fxlog.append((state['call'], 'S', 0))
    v = cpu.mem[R6]
    if v != _r6[0]:
        if not (PLO <= pc <= PHI):
            fxlog.append((state['call'], 'Z', v))
        _r6[0] = v
    if CYCLES and _in_music[0]:
        if cpu.sp > _in_music[1]:
            _in_music[0] = False
        else:
            tot_cyc[0] += CYC[cpu.mem[pc]]


_step = cpu.step
def step():
    watch(cpu.pc)
    _step()
cpu.step = step
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

rv.run_frames(cpu, NFRAMES, sym=sym)
tot_cyc = tot_cyc[0]

blob = b''.join(bytes((r, v)) + state_call.to_bytes(2, 'little')
                for state_call, r, v in stream)
h = hashlib.md5(blob).hexdigest()[:12]
byreg = collections.Counter(r for _, r, _ in stream)
print(f'сцена {SCENE}, кадров {NFRAMES}: вызовов плеера {state["call"]}, записей в AY {len(stream)}, md5 {h}')
print('  регистры:', ' '.join(f'R{r}={n}' for r, n in sorted(byreg.items())))
if CYCLES:
    n = max(1, state['call'])
    print(f'  такты в MUSIC_Play: всего {tot_cyc}, на вызов {tot_cyc / n:.0f}, на тик (6 кадров) {tot_cyc / n * 6:.0f}')
if FXLOG:
    with open(FXLOG, 'w') as f:
        for c, k, n in fxlog:
            f.write(f'{c} {k} {n}\n')
    print('  события: MUSIC_Load %d, FX_Play %d, MUSIC_Stop %d -> %s'
          % (sum(1 for x in fxlog if x[1] == 'L'), sum(1 for x in fxlog if x[1] == 'F'),
             sum(1 for x in fxlog if x[1] == 'S'), FXLOG))
if OUT:
    with open(OUT, 'w') as f:
        for c, r, v in stream:
            f.write(f'{c} {r} {v}\n')
    print('  дамп:', OUT)
