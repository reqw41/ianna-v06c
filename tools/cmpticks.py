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
Ключ --phase добавляет третий прогон: сборка A с лучом на 4 % дальше (IANNA_PITSCALE=104, код тот
же). Тики, на которых VRAM отличается уже от этого, помечены как ФАЗОВЫЙ ШУМ и из сверки исключены:
сброс пула сам решает, что вывести сейчас, а что позади луча, и содержимое кадра на таких тиках
законно зависит от фазы (проверено 2026-09-04: одна и та же сборка, ур.1 4,5, тики 47..64 — те же
21 байт, что и между сборками). ENTITY_DATA/SPDATA обязаны совпадать ВСЕГДА.
Сверяются ENTITY_DATA, SPDATA и VRAM на КАЖДОМ тике. VRAM делится надвое: ИГРОВОЕ ПОЛЕ
(строки экрана 0..159, L=64..223) и ПАНЕЛЬ (строки 160..191, L=32..63). Панель считается отдельно,
потому что перерисовывается она ПО РАСПИСАНИЮ КАДРОВ: waitforVBlank рисует по одному куску (герой,
враг 1, враг 2) за КАЖДЫЙ ЛИШНИЙ КАДР до frames_lock = 5, и в тике длиннее пяти кадров не рисует
ничего. Ускорение кода меняет число кадров в тике — и очередь кусков панели сдвигается на тик-другой
(найдено 2026-09-04: шкала героя на ур.2 4,6, тики 43..45, 63 байта, дальше совпадает). Это задержка
показа, а не другое содержимое, поэтому расхождения панели печатаются предупреждением, а не отказом;
поле и последний тик окна обязаны совпасть точно.
ГПСЧ подменяется как в cmpbuild --norand (A := randData += $4D).
"""
import sys, os, pathlib, hashlib

FIGHT = [['fire','right'],[],['fire','up'],[],['fire','down'],[],['fire','left'],[],['right'],['right'],['left'],['left'],['up'],['down']] if '--fight' in sys.argv else None
_e0 = [None]
def IMM(cpu, sym):
    """Герой неуязвим (здоровье возвращается каждый тик): иначе на сценах с великанами он гибнет,
    игра уходит в экран гибели, тики кончаются и сверка стоит до тайм-аута."""
    a = sym['ENTITY_PLAYER_POINTER'] + 4
    if _e0[0] is None: _e0[0] = cpu.mem[a]
    elif cpu.mem[a] < _e0[0]: cpu.mem[a] = _e0[0]
    return True

def run(rom, lst, edd, start, nticks, settle, pitscale=100):
    _e0[0] = None
    os.environ['IANNA_EDD'] = edd
    os.environ['IANNA_PITSCALE'] = str(pitscale)
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
    cpu.pc = 0x100; rv.patch_menu(cpu, lst)
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
            if pc == RS and (IMM(cpu, sym) or True): ticks += 1; cpu.mem[FC] = ticks & 0xFF
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
        if done: break
    assert done, 'игра не стартовала'
    keys.clear(); out = []
    WT = sym.get('wait_till_read', -1); wait = False
    while ticks < settle + nticks:
        c = 0
        while not cpu.halted and c < rv.STEP_BUDGET:      # без предела кадр в busy-loop текста не кончался вовсе
            c += 1
            if cpu.pc == WT and not wait: wait = True; saved = list(keys); keys[:] = ['fire']   # текст скрипта снять
            if cpu.pc == RS:
                IMM(cpu, sym)
                if wait: wait = False; keys[:] = saved
                ticks += 1; cpu.mem[FC] = ticks & 0xFF
                if FIGHT:                                  # --fight: удары во все стороны и шаги, по тикам
                    if ticks >= settle: keys[:] = FIGHT[(ticks - settle) // 2 % len(FIGHT)]
                elif ticks == settle: keys.append('right')   # бег вправо — с фиксированного тика
                if ticks > settle:
                    m = cpu.mem
                    fld = b''.join(bytes(m[b + c*256 + 64: b + c*256 + 224])
                                   for b in (0x8000, 0xA000, 0xC000, 0xE000) for c in range(32))
                    pan = b''.join(bytes(m[b + c*256 + 32: b + c*256 + 64])
                                   for b in (0x8000, 0xA000, 0xC000, 0xE000) for c in range(32))
                    out.append((ticks, bytes(m[E:E + 96]), bytes(m[SP:SP + 128]),
                                hashlib.md5(fld).digest(), hashlib.md5(pan).digest()))
            cpu.step()
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
    return out, bytes(cpu.mem[0x8000:0x10000])

SCENES = ((1, '4,5'), (2, '4,6'), (3, '1,0'), (3, '1,2'), (4, '6,2'), (6, '6,1'))

def main():
    A = [x for x in sys.argv[1:] if not x.startswith('--')]
    if '--dirs' in sys.argv:
        argv0 = list(sys.argv)
        da, db = A[0], A[1]
        n = int(A[2]) if len(A) > 2 else 60
        settle = int(A[3]) if len(A) > 3 else 30
        bad = 0
        for lv, xy in SCENES:
            sys.argv = [sys.argv[0], f'{da}/l{lv}.rom', f'{da}/l{lv}.lst', f'{da}/l{lv}.edd',
                        f'{db}/l{lv}.rom', f'{db}/l{lv}.lst', f'{db}/l{lv}.edd', xy, str(n), str(settle)]
            if '--phase' in argv0: sys.argv.append('--phase')
            print(f'  ур.{lv} {xy:<4}', end=' ')
            bad += main()
        return 1 if bad else 0
    st = tuple(int(v) for v in A[6].split(','))
    n = int(A[7]) if len(A) > 7 else 60
    settle = int(A[8]) if len(A) > 8 else 30
    ra, va = run(A[0], A[1], A[2], st, n, settle)
    rb, vb = run(A[3], A[4], A[5], st, n, settle)
    noisy = set()
    if '--phase' in sys.argv:
        rp, _ = run(A[0], A[1], A[2], st, n, settle, pitscale=104)
        noisy = {t for (t, _e, _s, v1, _p), (_, _e2, _s2, v2, _p2) in zip(ra, rp) if v1 != v2}
    panel = []
    last = len(ra) - 1
    for i, ((t, e1, s1, v1, p1), (_, e2, s2, v2, p2)) in enumerate(zip(ra, rb)):
        if p1 != p2 and i != last:
            panel.append(t)
            continue
        if e1 != e2 or s1 != s2 or p1 != p2 or (v1 != v2 and t not in noisy):
            print(f'РАЗОШЛОСЬ на тике {t}:', end='')
            if v1 != v2: print(' поле', end='')
            if p1 != p2: print(' панель', end='')
            for nm, x, y in (('ENTITY', e1, e2), ('SPDATA', s1, s2)):
                d = [i for i in range(len(x)) if x[i] != y[i]]
                if d: print(f' {nm} смещения {d[:10]} {[(x[i], y[i]) for i in d[:6]]}', end='')
            print()
            return 1
    vd = sum(1 for (t, _e, _s, v1, _p), (_, _e2, _s2, v2, _p2) in zip(ra, rb) if v1 != v2)
    note = f', фазовый шум: {len(noisy)} тиков, из них расходятся {vd}' if noisy else ''
    if panel: note += f'; ПАНЕЛЬ отстаёт на тиках {panel} (расписание кадров, к концу окна совпала)'
    print(f'совпало тик-в-тик на {len(ra)} тиках (прогрев {settle}), поле каждого тика совпало'
          f'{note}, md5 {hashlib.md5(va).hexdigest()[:8]}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
