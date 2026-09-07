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
        [--hero=x,y] [--settle=10] [--build] [--side=both|vec|msx] [--tag=имя]

ГПСЧ. Обе стороны исполняют ОДИН И ТОТ ЖЕ подменённый алгоритм A := randData += $4D
(на порте — патч в ОЗУ после прогрева, на MSX — патч в копии ROM), и в момент синхронизации
randData := 0. Штатный `random` оригинала читает `ld a,r` — воспроизвести его на i8080
невозможно в принципе, поэтому без подмены локстеп бессмыслен.

Синхронизация. Стартовый экран уровня: порт грузит набор уровня (build_edd --level), MSX ставит
current_level до LoadLevel — герой у обоих в initial_coordx/y уровня. Не стартовый экран
(--start): порт патчит current_levelx/y в SaveCheckpoint (run_vec.START), MSX переходит на экран
инъекцией ChangeScreen; герой при инъекции остаётся на прежнем месте, поэтому для сцен «войти
на экран сбоку» задаётся --hero=x,y (равный тому, что показал порт на тике 0).

Клавиши. keys[k] выставляются на границе тика k-1 и держатся весь тик k — одинаково на обеих
сторонах, поэтому задержка защёлкивания joystick_state в ISR у сторон одна и та же.
Сообщение («нажми огонь», в том числе после смерти) снимается автоматически: увидев
wait_till_read, обе стороны держат fire до следующего тика — иначе тики просто не идут.
"""
import sys, os, re, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRATCH = pathlib.Path('/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/agent_lock')


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
    rv.STEP_BUDGET = 400000            # тик считаем сами, кадр обрывать по числу инструкций нельзя
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
    rv.START = tuple(start) if start else None
    rv._start_done[0] = False
    rv.start_game(cpu, keys, sym)
    if hero:
        cpu.mem[sym['SPDATA'] + 3] = hero[0]; cpu.mem[sym['SPDATA'] + 4] = hero[1]

    RS = sym['RunScripts']; WTL = sym['wait_till_read_loop']
    SP = sym['SPDATA']; EN = sym['ENTITY_DATA']
    cpu.mem[rd] = 0; cpu.mem[rd + 1] = 0        # точка синхронизации
    dismissed = []
    state = {'t': -1}

    def tick(scen):
        """Догнать следующий вход в RunScripts. Сообщение снимаем огнём, как оракул."""
        budget = 0
        while budget < 40_000_000:
            while not cpu.halted:
                pc = cpu.pc
                if pc == RS:
                    cpu.step(); return True
                if pc == WTL and 'fire' not in keys:
                    dismissed.append(state['t'] + 1)
                    keys.append('fire')
                cpu.step(); budget += 1
            cpu.halted = False
            if cpu.ie:
                cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
            if 'fire' in keys and 'fire' not in scen:
                # сообщение снято прерыванием-другим: вернуть сценарные клавиши на следующем кадре
                pass
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

    keys.clear()
    for _ in range(settle):
        if not tick([]): sys.exit('порт: тик не пришёл (settle)')
    ticks = []
    for k, ks in enumerate(plan):
        keys.clear(); keys.extend(ks)
        state['t'] = k
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
        cmd = ['node', str(ROOT / 'tools/msxemu/lockstep_oracle.js'), '--level=%d' % level,
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
