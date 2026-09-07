#!/usr/bin/env python3
"""Минимум SP за прогон: сколько ОЗУ реально съедает стек.

Нужен, когда переменные растут вверх и отъедают у стека (vec_vars: за последней ячейкой
идёт `ds N` и выравнивание до vec_stack_top). Комментарий «нужно 140 Б» был снят один раз
на одной сцене — этот стенд даёт число по всем гейт-сценам.

  python3 tools/stackmin.py <rom> <lst> <edd> X,Y [тиков=60] [--route=left:20,none:5,fire+left:35]

Печатает vec_stack_top, минимальный SP и глубину = vec_stack_top - min SP.
"""
import sys, os, pathlib
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST = A[0], A[1], A[2], A[3]
N = int(A[4]) if len(A) > 4 else 60
ROUTE = next((o[8:] for o in OPTS if o.startswith('--route=')), None)
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100
rv.patch_menu(cpu)
a = sym['random']; rd = sym['randData']
cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
TOP = sym['vec_stack_top']
# Метод — «канарейка», а не минимум SP: стековый блит (dsp_body/vb_col/dtd_ok) уводит SP в
# чужие адреса, и по минимуму SP выходили ложные 1024 Б. Незанятый хвост перед vec_stack_top
# заполняем $A5 и смотрим, докуда его затёрли.
LOW = max((v for v in sym.values() if isinstance(v, int) and v < TOP and TOP - v < 0x400),
          default=TOP - 0x100) + 2      # +2: последняя переменная перед `ds` — слово (vec_fdd_ptr)
RT = [(int(s.split(':')[1]), [k for k in s.split(':')[0].split('+') if k != 'none'])
      for s in ROUTE.split(',')] if ROUTE else [(N, ['right'])]
NT = sum(n for n, _ in RT)
RS = sym['RunScripts']; FC = sym['FrameCounter']; mem = cpu.mem; step = cpu.step
# Заполняем только НИЖЕ текущего SP: выше лежат живые адреса возврата прогрева
CAN = cpu.sp
for i in range(LOW, CAN): mem[i] = 0xA5
ticks = 0
while ticks < NT:
    while not cpu.halted:
        if cpu.pc == RS:
            ticks += 1; mem[FC] = ticks & 0xFF
            acc = 0
            for n, ks in RT:
                acc += n
                if ticks - 1 < acc: keys[:] = ks; break
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
d = next((TOP - i for i in range(LOW, CAN) if mem[i] != 0xA5), TOP - CAN)
print(f'{ST}: vec_stack_top=${TOP:04X}, канарейка ${LOW:04X}..${CAN:04X}, затёрто с ${TOP-d:04X} — '
      f'глубина {d} Б (свободно до переменных ${LOW:04X}: {TOP - LOW - d} Б)')
