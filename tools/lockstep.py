#!/usr/bin/env python3
"""lockstep.py — сверка ПОРТА и ОРИГИНАЛА тик-в-тик по одному сценарию клавиш.

Один сценарий (уровень, стартовый экран, маршрут по тикам) исполняется на двух стендах:
  порт     — i8080 + квазидиск (tools/run_vec.py), тик = вход в RunScripts;
  оригинал — MSX2 headless WebMSX (tools/msxemu/lockstep_oracle.js), тик = крючок перед
             тем же RunScripts (патч в копии ROM, см. заголовок оракула).
После каждого тика снимается нормализованное состояние: спрайты (банк, кадр, x, y, зеркало),
сущности (индекс спрайта + байты 2..11), player_dead, current_levelx/y, global_timer. Панель и
VRAM не сравниваются: рендер у платформ разный.

  python3 tools/lockstep.py --level=2 --route=none:30,left:40,fire+left:30 [--start=5,6]
        [--hero=x,y] [--settle=20] [--build] [--side=both|vec|msx] [--tag=имя] [--curlevel]

ГПСЧ. Обе стороны исполняют ОДИН И ТОТ ЖЕ подменённый алгоритм A := randData += $4D
(на порте — патч в ОЗУ после прогрева, на MSX — патч в копии ROM), и в момент синхронизации
randData := 0. Штатный `random` оригинала читает `ld a,r` — воспроизвести его на i8080
невозможно в принципе, поэтому без подмены локстеп бессмыслен.

Синхронизация. Прогрев доводится до ОДНОГО номера игрового тика (--settle) от самого первого
RunScripts — обе стороны считают тики одинаково. Стартовый экран уровня: порт грузит набор уровня
(build_edd --level), MSX ставит current_level до LoadLevel — герой у обоих в initial_coordx/y.
Не стартовый экран (--start): обе стороны подменяют current_levelx/y ПЕРЕД SaveCheckpoint, чтобы
экран попал и в контрольную точку (иначе после смерти оригинал возродится не там, где порт).
--hero=x,y — принудительная посадка героя, если сцену иначе не свести.
--curlevel ставит порту номер уровня (обычно его проставляет меню; стенд запускает набор
напрямую и оставляет 0). Для уровней 1..9 разница видна только на экране пароля (оригинал его
показывает и ждёт огня, порт — нет) и в выборе песни, на сущности и спрайты не влияет.

Клавиши. Набор keys[k] выставляется на границе тика k и держится весь тик. Снимок тика k — это
состояние НА ВХОДЕ в RunScripts тика k, то есть результат тика k-1; joystick_state защёлкивается
в ISR ещё на тик раньше, поэтому нажатие, поставленное на тике k, видно в снимке тика k+2.
Смещение меток одинаково на обеих сторонах (проверено на ур.1: 100 тиков совпали байт в байт),
и на сверку не влияет.
Сообщение («нажми огонь», в том числе после смерти) снимается автоматически: увидев
wait_till_read, обе стороны держат fire до следующего тика — иначе тики просто не идут.
"""
import sys, os, re, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRATCH = pathlib.Path('/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/agent_lock')


def level_index(level):
    """Номер уровня в игре (current_level) по имени файла карты levelN.map.

    Таблица LEVEL_PAGE в ianna.asm перечисляет карты в порядке
    level1..level8, level0, level9: индекс 8 — это level0.map (ATTRACT/девятый уровень),
    а level9.map (секретный уровень) стоит под индексом 9. Прямолинейное level-1 для --level=9
    выбирало на оригинале ATTRACT, а на порте в наборе лежала карта level9 — сцены не совпадали
    ни одним байтом (найдено 2026-09-07)."""
    return level - 1 if level <= 8 else 9


def parse_route(r):
    out = []
    for seg in r.split(','):
        k, n = seg.split(':')
        keys = [x for x in k.split('+') if x not in ('none', '')]
        out += [keys] * int(n)
    return out


def run_vec_side(level, start, hero, plan, settle, out_path, rom=None, lst=None, edd=None):
    """Прогон порта. Возвращает dict того же формата, что оракул."""
    os.environ['IANNA_EDD'] = str(edd or ROOT / 'build/ianna.edd')
    sys.path.insert(0, str(ROOT / 'tools'))
    argv = sys.argv; sys.argv = [argv[0]]
    import run_vec as rv
    sys.argv = argv
    # Кадр — штатный run_vec (HALT или ~13000 инструкций). Здесь, в отличие от сверки СБОРОК
    # между собой (cmpticks ставит 400000), важна верность железу: на Векторе прерывание приходит
    # каждые 20 мс независимо от того, крутится код в busy-loop или нет.
    rv.STEP_BUDGET = rv.STEP_BUDGET
    sym = rv.load_syms(pathlib.Path(lst or ROOT / 'build/ianna_vec.lst'))
    keys = []
    cpu = rv.make_cpu(keys)
    if rom:
        data = pathlib.Path(rom).read_bytes()
        cpu.mem[0x100:0x100 + len(data)] = data
        cpu.pc = 0x100; rv.patch_menu(cpu)
    # ГПСЧ как на MSX-копии: A := randData += $4D
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
    RS = sym['RunScripts']; WTL = sym['wait_till_read_loop']; SC = sym['SaveCheckpoint']
    LL = sym['LoadLevel']; CL = sym['current_level']
    # Порт всегда стартует набор с current_level=0 (номер уровня ему проставляет меню, а стенд
    # запускает набор напрямую). Видно это только по экрану пароля (оригинал его
    # показывает и ждёт огня, порт — нет) и по выбору песни; на сущности и спрайты не влияет.
    # --curlevel ставит номер там же, где его ставит оракул, — перед LoadLevel. ВНИМАНИЕ: индекс 8
    # (level0.map, attract) порту недоступен — build_edd таких наборов не делает.
    curlevel = [level_index(level)] if '--curlevel' in sys.argv else []
    SP = sym['SPDATA']; EN = sym['ENTITY_DATA']
    LX = sym['current_levelx']; LY = sym['current_levely']
    startpatch = [tuple(start)] if start else []     # одноразовая подмена стартового экрана
    dismissed = []
    state = {'t': -1}

    def tick(scen):
        """Догнать точку снимка — вход в RunScripts (та же точка, что крючок оракула).

        Сообщение («нажми огонь», в том числе после смерти) снимаем огнём: пока игра стоит в
        wait_till_read, RunScripts не зовётся и тик не придёт. То же делает оракул и rv.Warmup.

        Кадр здесь — как в run_vec.run_frames: до HALT ИЛИ rv.STEP_BUDGET инструкций, и только
        потом прерывание. Без второго условия busy-loop wait_till_read не получает прерываний
        вовсе, joystick_state не обновляется, и порт висит в сообщении навечно (ловилось на
        стартовом экране ур.4: второе сообщение приходит на тике 29)."""
        budget = 0
        frame = rv.STEP_BUDGET
        while budget < 40_000_000:
            c = 0
            while not cpu.halted and c < frame:
                pc = cpu.pc
                if pc == RS:
                    cpu.step()                            # снимок берём тут же, до тела RunScripts
                    if 'fire' in keys and 'fire' not in scen:
                        keys.clear(); keys.extend(scen)   # сообщение снято, вернуть сценарные клавиши
                    return True
                if pc == WTL and 'fire' not in keys:
                    dismissed.append(state['t'] + 1)
                    keys.append('fire')
                if startpatch and pc == SC:       # то же, что крючок оракула перед SaveCheckpoint
                    cpu.mem[LX], cpu.mem[LY] = startpatch.pop()
                if curlevel and pc == LL:
                    cpu.mem[CL] = curlevel.pop()
                cpu.step(); c += 1; budget += 1
            cpu.halted = False
            if cpu.ie:
                cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
        return False

    def snap(t, k):
        spr = []
        for i in range(16):
            r = cpu.mem[SP + i * 8:SP + i * 8 + 8]
            ad = r[0] | (r[1] << 8)
            spr.append(None if ad == 0 else [r[2] & 0x7F, (ad - 0x8000) // 384, r[3], r[4], (r[2] >> 7) & 1])
        ent = []
        for i in range(8):
            r = cpu.mem[EN + i * 12:EN + i * 12 + 12]
            p = r[0] | (r[1] << 8)
            idx = (p - SP) // 8 if SP <= p < SP + 128 else -1
            ent.append(None if p == 0 else [idx] + list(r[2:12]))
        return {'t': t, 'keys': k, 'spr': spr, 'ent': ent,
                'pd': cpu.mem[sym['player_dead']], 'lx': cpu.mem[sym['current_levelx']],
                'ly': cpu.mem[sym['current_levely']], 'gt': cpu.mem[sym['global_timer']]}

    # Прогрев отсчитывается В ИГРОВЫХ ТИКАХ от самого первого RunScripts — так же, как оракул
    # считает свой TICKC. Ждать «столько-то кадров» нельзя: на экране, где герой сразу падает
    # (стартовый экран ур.4), разная длина прогрева даёт разную фазу падения, и сверка расходится
    # уже на нулевом тике (порт был на 16 пикселей правее и на 32 ниже оригинала).
    keys.clear()
    for _ in range(settle):
        if not tick([]): sys.exit('порт: тик не пришёл (прогрев)')
    if hero:
        cpu.mem[SP + 3] = hero[0]; cpu.mem[SP + 4] = hero[1]
    cpu.mem[rd] = 0; cpu.mem[rd + 1] = 0        # точка синхронизации ГПСЧ
    ticks = []
    for k, ks in enumerate(plan):
        keys.clear(); keys.extend(ks)
        state['t'] = k
        if k % 10 == 0:
            sys.stderr.write('  порт: тик %d/%d (%d млн инстр.)\n' % (k, len(plan), cpu.icount // 1000000))
            sys.stderr.flush()
        if not tick(ks):
            print('порт: тик не пришёл на', k); break
        ticks.append(snap(k, ks))
    res = {'side': 'vec', 'level': level, 'start': start, 'route': None, 'settle': settle,
           'dismissed': dismissed, 'ticks': ticks}
    pathlib.Path(out_path).write_text(json.dumps(res))
    print('порт: тиков %d, снятых сообщений %d' % (len(ticks), len(dismissed)))
    return res


# ---------------------------------------------------------------- сравнение
def diff_tick(a, b):
    """Список расхождений одного тика: (поле, значение порта, значение оригинала)."""
    out = []
    for f in ('pd', 'lx', 'ly'):
        if a[f] != b[f]: out.append((f, a[f], b[f]))
    NAMES = ('spr', 'frame', 'x', 'y', 'mir')
    for i in range(16):
        x, y = a['spr'][i], b['spr'][i]
        if (x is None) != (y is None):
            out.append(('spr%d' % i, 'нет' if x is None else x, 'нет' if y is None else y)); continue
        if x is None: continue
        for j, nm in enumerate(('банк', 'кадр', 'x', 'y', 'зерк')):
            if x[j] != y[j]: out.append(('spr%d.%s' % (i, nm), x[j], y[j]))
    for i in range(8):
        x, y = a['ent'][i], b['ent'][i]
        if (x is None) != (y is None):
            out.append(('ent%d' % i, 'нет' if x is None else x, 'нет' if y is None else y)); continue
        if x is None: continue
        for j in range(11):
            nm = 'спрайт' if j == 0 else 'b%d' % (j + 1)
            if x[j] != y[j]: out.append(('ent%d.%s' % (i, nm), x[j], y[j]))
    return out


def compare(vec, msx, ctx=3):
    n = min(len(vec['ticks']), len(msx['ticks']))
    first = None
    for k in range(n):
        d = diff_tick(vec['ticks'][k], msx['ticks'][k])
        if d:
            first = (k, d); break
    print('=' * 72)
    print('тиков сверено: %d (порт %d, оригинал %d)' % (n, len(vec['ticks']), len(msx['ticks'])))
    if first is None:
        print('РАСХОЖДЕНИЙ НЕТ')
        return None
    k, d = first
    print('ПЕРВОЕ РАСХОЖДЕНИЕ на тике %d (клавиши %s):' % (k, '+'.join(vec['ticks'][k]['keys']) or 'none'))
    for f, x, y in d[:40]:
        print('   %-16s порт=%-14s оригинал=%s' % (f, x, y))
    if len(d) > 40: print('   ... всего полей: %d' % len(d))
    print('-- контекст, последние %d тиков до расхождения:' % ctx)
    for j in range(max(0, k - ctx), k + 1):
        a, b = vec['ticks'][j], msx['ticks'][j]
        print('  t%-4d кл=%-12s герой порт%s орг%s  враг1 порт%s орг%s  pd=%d/%d' % (
            j, '+'.join(a['keys']) or 'none', a['spr'][0], b['spr'][0], a['spr'][1], b['spr'][1], a['pd'], b['pd']))
    # сколько ещё тиков расходится дальше
    bad = sum(1 for j in range(n) if diff_tick(vec['ticks'][j], msx['ticks'][j]))
    print('расходящихся тиков в окне: %d из %d' % (bad, n))
    return first


def main():
    def arg(name, default=None):
        p = next((a for a in sys.argv if a.startswith('--%s=' % name)), None)
        return default if p is None else p.split('=', 1)[1]
    level = int(arg('level', '1'))
    start = [int(v) for v in arg('start').split(',')] if arg('start') else None
    hero = [int(v) for v in arg('hero').split(',')] if arg('hero') else None
    route = arg('route', 'none:30')
    settle = int(arg('settle', '10'))
    side = arg('side', 'both')
    tag = arg('tag', 'ls')
    SCRATCH.mkdir(parents=True, exist_ok=True)
    vec_json = SCRATCH / ('%s_vec.json' % tag)
    msx_json = SCRATCH / ('%s_msx.json' % tag)
    plan = parse_route(route)

    if '--build' in sys.argv:
        cmd = [sys.executable, str(ROOT / 'tools/data/build_edd.py'), '--level=%d' % level]
        if start: cmd.append('--start=%d,%d' % tuple(start))
        subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(ROOT / 'tools/build_vec.py')], check=True, cwd=ROOT,
                       stdout=subprocess.DEVNULL)

    if side in ('both', 'msx'):
        cmd = ['node', str(ROOT / 'tools/msxemu/lockstep_oracle.js'), '--level=%d' % level_index(level),
               '--route=' + route, '--settle=%d' % settle, '--out=' + str(msx_json)]
        if start: cmd.append('--start=%d,%d' % tuple(start))
        if hero: cmd.append('--hero=%d,%d' % tuple(hero))
        r = subprocess.run(cmd, cwd=ROOT, stderr=subprocess.PIPE, text=True)
        sys.stderr.write('\n'.join(l for l in r.stderr.splitlines() if 'msx:' in l or 'не ' in l) + '\n')
        if r.returncode != 0: sys.exit('оракул MSX упал')
    if side in ('both', 'vec'):
        run_vec_side(level, start, hero, plan, settle, vec_json)
    if side == 'both':
        compare(json.loads(vec_json.read_text()), json.loads(msx_json.read_text()))


if __name__ == '__main__':
    main()
