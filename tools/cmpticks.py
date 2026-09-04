"""Сверка двух сборок ТИК-В-ТИК: прогрев считает игровые тики, а не кадры.

Зачем отдельно от cmpbuild.py: штатный прогрев (run_vec.start_game) после старта игры добивает
10 КАДРОВ. Более быстрая сборка успевает за эти кадры больше игровых тиков, и сцена с врагами
начинается с другой фазы анимации — ENTITY_DATA расходится на ускоряющей правке, которая логику
не трогала (найдено 2026-09-04 на ур.2 4,6: у обоих врагов поле anim отличалось на 1 уже на первом
тике). Здесь прогрев доводится до ЗАДАННОГО номера тика, поэтому обе сборки стартуют из одного
состояния и любое расхождение — настоящее.

  python3 tools/cmpticks.py <romA> <lstA> <eddA> <romB> <lstB> <eddB> X,Y [тиков=60] [прогрев=30]
  python3 tools/cmpticks.py --dirs <каталогA> <каталогB> [тиков=60] [прогрев=30]
Второй вид проходит те же шесть сцен, что gates.sh (каталоги из gates.sh snap).
Печатает первый разошедшийся тик и смещения в ENTITY_DATA/SPDATA либо «совпало».
ГПСЧ подменяется как в cmpbuild --norand (A := randData += $4D).
"""
import sys, os, pathlib, hashlib

def run(rom, lst, edd, start, nticks, settle):
    os.environ['IANNA_EDD'] = edd
    for m in ('run_vec',):
        sys.modules.pop(m, None)
    argv = sys.argv; sys.argv = [argv[0]]
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import run_vec as rv
    sys.argv = argv
    rv.STEP_BUDGET = 400000
    sym = rv.load_syms(pathlib.Path(lst))
    keys = []; cpu = rv.make_cpu(keys)
    data = pathlib.Path(rom).read_bytes(); cpu.mem[0x100:0x100 + len(data)] = data
    cpu.pc = 0x100; rv.patch_menu(cpu)
    a = sym['random']; rd = sym['randData']       # --norand: ГПСЧ без чтения байтов кода
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
    rv.START = start; rv._start_done[0] = False
    RS = sym['RunScripts']; FC = sym['FrameCounter']; E = sym['ENTITY_DATA']; SP = sym['SPDATA']
    w = rv.Warmup(sym, keys); done = False; ticks = 0
    for fr in range(1500):
        c = 0
        while not cpu.halted and c < rv.STEP_BUDGET:
            pc = cpu.pc
            if not rv._start_done[0] and pc == sym['SaveCheckpoint']:
                cpu.mem[sym['current_levelx']] = start[0]; cpu.mem[sym['current_levely']] = start[1]
                rv._start_done[0] = True
            if w.step(pc, fr): done = True
            if pc == RS: ticks += 1; cpu.mem[FC] = ticks & 0xFF
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
        if done: break
    assert done, 'игра не стартовала'
    keys.clear(); out = []
    while ticks < settle + nticks:
        while not cpu.halted:
            if cpu.pc == RS:
                ticks += 1; cpu.mem[FC] = ticks & 0xFF
                if ticks == settle: keys.append('right')   # бег вправо — с фиксированного тика
                if ticks > settle:
                    out.append((ticks, bytes(cpu.mem[E:E + 96]), bytes(cpu.mem[SP:SP + 128])))
            cpu.step()
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
    return out, bytes(cpu.mem[0x8000:0x10000])

SCENES = ((1, '4,5'), (2, '4,6'), (3, '1,0'), (3, '1,2'), (4, '6,2'), (6, '6,1'))

def main():
    A = [x for x in sys.argv[1:] if not x.startswith('--')]
    if '--dirs' in sys.argv:
        da, db = A[0], A[1]
        n = int(A[2]) if len(A) > 2 else 60
        settle = int(A[3]) if len(A) > 3 else 30
        bad = 0
        for lv, xy in SCENES:
            sys.argv = [sys.argv[0], f'{da}/l{lv}.rom', f'{da}/l{lv}.lst', f'{da}/l{lv}.edd',
                        f'{db}/l{lv}.rom', f'{db}/l{lv}.lst', f'{db}/l{lv}.edd', xy, str(n), str(settle)]
            print(f'  ур.{lv} {xy:<4}', end=' ')
            bad += main()
        return 1 if bad else 0
    st = tuple(int(v) for v in A[6].split(','))
    n = int(A[7]) if len(A) > 7 else 60
    settle = int(A[8]) if len(A) > 8 else 30
    ra, va = run(A[0], A[1], A[2], st, n, settle)
    rb, vb = run(A[3], A[4], A[5], st, n, settle)
    for (t, e1, s1), (_, e2, s2) in zip(ra, rb):
        if e1 != e2 or s1 != s2:
            print(f'РАЗОШЛОСЬ на тике {t}:', end='')
            for nm, x, y in (('ENTITY', e1, e2), ('SPDATA', s1, s2)):
                d = [i for i in range(len(x)) if x[i] != y[i]]
                if d: print(f' {nm} смещения {d[:10]} {[(x[i], y[i]) for i in d[:6]]}', end='')
            print()
            return 1
    ok = 'VRAM совпал' if va == vb else 'VRAM РАЗОШЁЛСЯ'
    print(f'совпало тик-в-тик на {len(ra)} тиках (прогрев {settle}), {ok}, '
          f'md5 {hashlib.md5(va).hexdigest()[:8]}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
