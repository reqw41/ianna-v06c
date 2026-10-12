#!/usr/bin/env python3
"""Сторож стека: кто уводит SP из $7Dxx (дефект «смерть машины» 2026-09-09, vec_sp_save = $074E).

Стенд по тактам (прерывание каждые 59904 такта, как measure_vec), клавиши — случайные, тексты
скриптов снимаются сами (fire на wait_till_read). На каждой инструкции проверяется:
  * `ld (vec_sp_save),hl` — сохраняемое значение обязано лежать в игровом стеке;
  * любая стековая команда (push/pop/call/ret/rst) при ВЫКЛЮЧЕННОМ стековом режиме квазидиска —
    SP обязан быть в игровом стеке (исключение — чёрный тайл push'ами в экран: SP >= $8000);
  * вход в ISR ($38) без стекового режима — SP обязан быть в игровом стеке.
  * счётчик грязных прямоугольников больше 48 (tiles_dirty на 48 записей, дальше — SPDATA);
  * исполнение кода в области стека и «дикая» запись в ячейки --watch (изменилась не своей командой).
Первое нарушение печатается с хвостом трассы (метки по листингу) и прогон останавливается.

  python3 tools/spwatch.py <rom> <lst> <edd> X,Y [--frames=3000] [--seed=1] [--trace=80] [--watch=vec_sp_save,vec_key_hook] [--kvwatch=3:C802:C956] [--dump=vec_slot_tab:16,$7FA0:32] [--noseries]
                          [--fdd=build/ianna.fdd --next=1500]   [--goto=2:6,6]   (EDD — пустой файл 256К; ROM из образа)
"""
import sys, os, re, bisect, random, pathlib, collections
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
if len(A) < 4: sys.exit(__doc__)
ROM, LST, EDD, ST = A[:4]
def opt(name, default):
    return next((o[len(name) + 3:] for o in OPTS if o.startswith(f'--{name}=')), default)
FRAMES = int(opt('frames', 3000)); SEED = int(opt('seed', 1)); NTRACE = int(opt('trace', 80))
FDD = opt('fdd', '')              # образ дискеты: ROM берётся из него, EDD должен быть пустым (загрузка с дискеты)
GOTO = opt('goto', '')            # L:X,Y — при входе на уровень L (после загрузки с дискеты) начать с экрана X,Y
GOTO = (int(GOTO.split(':')[0]) - 1, *map(int, GOTO.split(':')[1].split(','))) if GOTO else None
NEXT = int(opt('next', 0))
MAXLV = int(opt('maxlevel', 9))    # дальше этого уровня --next не ведёт        # в дискетном режиме: каждые N кадров игры — переход на следующий уровень
os.environ['IANNA_EDD'] = EDD
if FDD: os.environ['IANNA_FDD'] = FDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
src = open('tools/profile_vec.py').read(); exec(src[src.index('# Такты ВЕКТОРА'):src.index('keys = []')])
FRAME = 59904
rv.STEP_BUDGET = 400000
START = tuple(int(v) for v in ST.split(',')) if ST != '-' else None      # '-' = штатный старт уровня

labels = {}
for line in open(LST, encoding='utf-8', errors='replace'):
    m = re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):', line)
    if m: labels.setdefault(int(m.group(1), 16), m.group(2))
addrs = sorted(labels)
def fn(pc):
    k = bisect.bisect_right(addrs, pc) - 1
    return f'{labels[addrs[k]]}+{pc - addrs[k]}' if k >= 0 else '?'

sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
if not FDD:
    rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100 + len(rom)] = rom; cpu.pc = 0x100
    rv.patch_menu(cpu)
mem = cpu.mem
if '--noseries' in OPTS and 'SERIES_ADDR' in sym:        # серийный блит выключить: se_try = `or a / ret` (серии нет)
    cpu.kvaz[3 * 65536 + sym['SERIES_ADDR']:3 * 65536 + sym['SERIES_ADDR'] + 2] = b'\xB7\xC9'
# ВИ53 счётчик 0 по тактам (как в measure_vec)
pit = {'reload_cyc': 0, 'latched': None, 'wr': 0, 'rd': 0}
base_out = cpu.out_handler; base_in = cpu.in_handler
cyc = [0]
def pit_val(): return (0xFFFF - (((cyc[0] - pit['reload_cyc']) // 2) & 0xFFFF)) & 0xFFFF
def out_h(p, v):
    if p == 0x08:
        if v == 0: pit['latched'] = pit_val(); pit['rd'] = 0
        return
    if p == 0x0B:
        if pit['wr'] == 0: pit['wr'] = 1
        else: pit['wr'] = 0; pit['reload_cyc'] = cyc[0]
        return
    if p == 0x10: kvlog.append((frame[0], cpu.pc, v, mem[KVSH]))
    base_out(p, v)
def in_h(p):
    if p == 0x0B:
        v = pit['latched'] if pit['latched'] is not None else pit_val()
        if pit['rd'] == 0: pit['rd'] = 1; return v & 0xFF
        pit['rd'] = 0; pit['latched'] = None; return v >> 8
    return base_in(p)
cpu.out_handler = out_h; cpu.in_handler = in_h

TOP = sym['vec_stack_top']; LOW = TOP - 0x100
SPS = sym['vec_sp_save']; SPS_LO, SPS_HI = SPS & 0xFF, SPS >> 8
RS = sym['RunScripts']; SC = sym['SaveCheckpoint']; WT = sym.get('wait_till_read', -1)
def waddr(n): return int(n[1:], 16) if n.startswith('$') else sym[n]      # метка или $адрес
wname = {waddr(n): n for n in opt('watch', 'vec_sp_save,vec_key_hook').split(',')}
WATCH = list(wname)
wval = {a: mem[a] | (mem[a + 1] << 8) for a in WATCH}
ring = collections.deque(maxlen=NTRACE)
STATE = [n for n in ('current_level', 'ROMBank1', 'current_levelx', 'current_levely', 'level_width', 'player_dead') if n in sym]
SNAP_AT = {sym[n]: n for n in ('LoadScreen', 'depack', 'RestoreCheckpoint', 'SaveCheckpoint', 'LoadLevel', 'vec_reload_set',
                               'ChangeScreen', 'draw_gameover_string') if n in sym}
INVS = sym.get('InvalidateSTiles', -1); NDR = sym['ndirtyrects']; ndr_max = [0]; ndr_at = [None]
NDR_LIM = int(opt('ndrlimit', 49))      # счётчик больше 48 = запись ушла за список; 48 = проверить и сборку без границы
snaps = collections.deque(maxlen=14)
# поток управления по меткам (без ISR и шумных хелперов) — чтобы видеть, откуда пришли
flow = collections.deque(maxlen=int(opt('flow', 120))); flow_last = [None]; in_isr = [False]
NOISE = ('z_', 'ap_', 'apbranch', 'apskip', 'gj_', 'rev256')
ISR_END = max(a for a in addrs if labels[a] == 'isr_nomusic') if 'isr_nomusic' in labels.values() else -1
# --kvwatch=стр:начало:конец (hex) — область квазидиска, которая в игре меняться не должна (код оверлея)
KVW = None
if opt('kvwatch', ''):
    pg, a0, a1 = (int(x, 16) for x in opt('kvwatch', '').split(':'))
    KVW = (pg * 65536 + a0, pg * 65536 + a1)
kv_ref = [bytes(cpu.kvaz[KVW[0]:KVW[1]]) if KVW else b'']
kvlog = collections.deque(maxlen=24); KVSH = sym['vec_kv_shadow']
frame = [0]; ticks = [0]; hist = []
def ok_sp(v): return LOW <= v <= TOP
# push/pop/call/ret/rst/xthl: всё, что читает или пишет память по SP
STACK_OPS = {o for o in range(0xC0, 0x100) if o & 7 in (0, 4, 5, 7)} | {0xC1, 0xD1, 0xE1, 0xF1, 0xC9, 0xCD, 0xE3}

def fail(what):
    print(f'НАРУШЕНИЕ: {what}')
    print(f'  кадр {frame[0]}, тик {ticks[0]}, фаза кадра {(cyc[0] - (next_irq - FRAME)) / 256:.0f} ед., '
          f'порт квазидиска ${cpu.kv_cw:02X}, клавиши {keys}')
    print(f'  PC=${cpu.pc:04X} {fn(cpu.pc)}  SP=${cpu.sp:04X} HL=${(cpu.h << 8) | cpu.l:04X} '
          f'vec_sp_save=${mem[SPS] | (mem[SPS + 1] << 8):04X} ie={cpu.ie}')
    print(f'  BC=${(cpu.b << 8) | cpu.c:04X} DE=${(cpu.d << 8) | cpu.e:04X} A=${cpu.a:02X}; стек:',
          ' '.join(f'${mem[a] | (mem[a + 1] << 8):04X}({fn(mem[a] | (mem[a + 1] << 8))})'
                   for a in range(cpu.sp, min(TOP, cpu.sp + 24), 2) if ok_sp(a)))
    print('  ' + ', '.join(f'{n}=${mem[sym[n]]:02X}' for n in
          ('current_level', 'ROMBank1', 'current_levelx', 'current_levely', 'level_width', 'level_height') if n in sym))
    print('  вехи (кадр, тик, точка, A, HL, DE, порт, состояние):')
    for f, t, n, a, hl, de, cw, stt in snaps:
        print(f'    кадр {f} тик {t} {n:18s} A=${a:02X} HL=${hl:04X} DE=${de:04X} порт=${cw:02X} ' +
              ' '.join(f'{k}={v:02X}' for k, v in stt.items()))
    print('  стр.3 $C800.. (окно серии): ' + bytes(cpu.kvaz[3 * 65536 + 0xC800:3 * 65536 + 0xC820]).hex())
    for d in opt('dump', '').split(','):          # --dump=метка|$адрес:длина,...
        if d:
            a, n = d.split(':'); a = waddr(a)
            print(f'  дамп {d}: ' + bytes(mem[a:a + int(n)]).hex(' '))
    print('  последние out($10) (кадр, PC после команды, значение, vec_kv_shadow):')
    for f, pc, v, sh in kvlog: print(f'    кадр {f} ${pc:04X} {fn(pc):26s} out ${v:02X}  тень ${sh:02X}')
    print('  клавиши по кадрам (последние):', ' '.join(f'{f}:{"+".join(k) or "-"}' for f, k in hist[-8:]))
    print('  поток по меткам (кадр, PC, метка, SP):')
    for f, pc, nm, sp in flow: print(f'    {f} ${pc:04X} {nm:28s} SP=${sp:04X}')
    print('  трасса (PC SP порт):')
    prev = None; out = []
    for pc, sp, cw in ring:
        name = fn(pc)
        base = name.split('+')[0]
        if base != prev: out.append(f'    ${pc:04X} {name:28s} SP=${sp:04X} порт=${cw:02X}'); prev = base
    print('\n'.join(out[-60:]))
    sys.exit(1)

def opnd(a): return mem[a] if a < 0x8000 else cpu.rb(a)     # код в окне квазидиска читаем через окно
def check(pc):
    op = mem[pc] if pc < 0x8000 else cpu.rb(pc)
    if op == 0x22:
        if (mem[pc + 1] if pc < 0x8000 else cpu.rb(pc + 1)) == SPS_LO and \
           (mem[pc + 2] if pc < 0x8000 else cpu.rb(pc + 2)) == SPS_HI:
            v = (cpu.h << 8) | cpu.l
            if not ok_sp(v): fail(f'в vec_sp_save пишется ${v:04X} (не игровой стек)')
    elif op in STACK_OPS:
        if not cpu.kv_stack_mode and not ok_sp(cpu.sp) and cpu.sp < 0x8000:
            fail(f'стековая команда ${op:02X} при SP=${cpu.sp:04X} без стекового режима')
    return op

next_irq = FRAME + random.Random(SEED).randrange(FRAME)      # фаза прерывания относительно старта — от seed
def run_frame(hook=None):
    global next_irq
    end = cyc[0] + FRAME
    while cyc[0] < end:
        if cpu.halted:
            cyc[0] = next_irq
        else:
            pc = cpu.pc
            if hook: hook(pc)
            ring.append((pc, cpu.sp, cpu.kv_cw))
            k = bisect.bisect_right(addrs, pc) - 1
            if k != flow_last[0] and not in_isr[0]:
                nm = labels[addrs[k]] if k >= 0 else '?'
                if not nm.startswith(NOISE):
                    flow_last[0] = k; flow.append((frame[0], pc, nm, cpu.sp))
            if pc == 0x38: in_isr[0] = True
            elif pc == ISR_END: in_isr[0] = False
            if pc == INVS and mem[NDR] > ndr_max[0]:
                ndr_max[0] = mem[NDR]; ndr_at[0] = (frame[0], ticks[0], mem[sym['current_levelx']], mem[sym['current_levely']])
            if pc == INVS and mem[NDR] >= NDR_LIM:
                fail(f'список грязных прямоугольников переполнен ({mem[NDR]} при 48 местах): '
                     f'B,C,D,E = {cpu.b},{cpu.c},{cpu.d},{cpu.e}')
            if pc in SNAP_AT:
                snaps.append((frame[0], ticks[0], SNAP_AT[pc], cpu.a, (cpu.h << 8) | cpu.l, (cpu.d << 8) | cpu.e, cpu.kv_cw,
                              {n: mem[sym[n]] for n in STATE}))
            op = check(pc)
            cyc[0] += CYC[op]
            if LOW <= pc < TOP: fail(f'исполнение в области стека, PC=${pc:04X}')
            try: cpu.step()
            except RuntimeError as e: fail(f'крах эмулятора: {e}')
            if KVW and bytes(cpu.kvaz[KVW[0]:KVW[1]]) != kv_ref[0]:
                cpu.pc = pc
                fail(f'запись в квазидиск {opt("kvwatch", "")}: команда ${op:02X}')
            # дикая запись: слово-ячейка изменилась, а команда — не `ld (её адрес),hl`
            for a in WATCH:
                v = mem[a] | (mem[a + 1] << 8)
                if v != wval[a]:
                    direct = op in (0x22, 0x32) and (opnd(pc + 1) | (opnd(pc + 2) << 8)) in (a, a + 1)
                    if not direct:
                        cpu.pc = pc
                        fail(f'дикая запись в {wname[a]} (${a:04X}): ${wval[a]:04X} -> ${v:04X}, команда ${op:02X}')
                    wval[a] = v
        if cyc[0] >= next_irq:
            next_irq += FRAME
            if cpu.ie:
                if not cpu.kv_stack_mode and not ok_sp(cpu.sp):
                    fail(f'прерывание при SP=${cpu.sp:04X} без стекового режима')
                cpu.ie = False; cpu.halted = False; cpu.push(cpu.pc); cpu.pc = 0x38

# --- прогрев (как в measure_vec) ---
w = rv.Warmup(sym, keys); st = {'patched': False, 'started': False, 'fr': 0}
def warm(pc):
    if START and not st['patched'] and pc == SC:
        mem[sym['current_levelx']] = START[0]; mem[sym['current_levely']] = START[1]; st['patched'] = True
    if w.step(pc, st['fr']): st['started'] = True
for fr in range(6000 if FDD else 1500):
    st['fr'] = fr; run_frame(warm)
    if st['started']: break
    # дискетный старт: меню ждёт «огонь» — жмём короткими нажатиями, пока не дойдём до игры
    if FDD and w.first is None and fr > 600: keys[:] = ['fire'] if (fr // 25) % 2 else []
if not st['started']:
    sys.exit(f'игра не стартовала: кадр {fr}, PC=${cpu.pc:04X} {fn(cpu.pc)}, SP=${cpu.sp:04X}, порт ${cpu.kv_cw:02X}')
keys.clear()

# --- случайная игра ---
rnd = random.Random(SEED)
MOVES = [[], ['left'], ['right'], ['up'], ['down'], ['fire'], ['fire', 'left'], ['fire', 'right'],
         ['up', 'left'], ['up', 'right'], ['down', 'fire'], ['up', 'fire'], ['left'], ['right'],
         ['fire', 'right'], ['fire', 'left'], ['z'], ['action']]
wait = {'on': False}
RELOAD = sym.get('vec_reload_set', -1)
LLT = sym.get('vec_load_leveltab', -1)
zp_ref = [None]; zp_pending = [False]
def play(pc):
    if GOTO and pc == SC and mem[sym['current_level']] == GOTO[0]:
        mem[sym['current_levelx']] = GOTO[1]; mem[sym['current_levely']] = GOTO[2]
    if pc == LLT: zp_pending[0] = True            # копия блита в нулевой странице сейчас обновится
    if pc == RELOAD and not FDD:      # смена набора (следующий уровень / меню) — без дискеты стенду дальше идти некуда
        print(f'{ST} seed {SEED}: кадр {frame[0]}, тик {ticks[0]} — уход на дискету (vec_reload_set), '
              f'нарушений нет'); sys.exit(0)
    if pc == RS:
        ticks[0] += 1
        if wait['on']: wait['on'] = False; keys.clear()
        if zp_pending[0] or zp_ref[0] is None: zp_ref[0] = bytes(mem[0x38:0x100]); zp_pending[0] = False
        elif bytes(mem[0x38:0x100]) != zp_ref[0]:
            bad = [0x38 + i for i in range(0xC8) if mem[0x38 + i] != zp_ref[0][i]]
            fail(f'нулевая страница изменилась вне vec_load_leveltab: ${bad[0]:02X}..${bad[-1]:02X}, {len(bad)} Б; '
                 f'теперь {bytes(mem[bad[0]:bad[0] + 8]).hex()}')
    elif pc == WT and not wait['on']:
        wait['on'] = True; keys[:] = ['fire']
left = 0
for f in range(FRAMES):
    frame[0] = f
    if not wait['on']:
        if left <= 0:
            keys[:] = rnd.choice(MOVES); left = rnd.randint(3, 40); hist.append((f, list(keys)))
        left -= 1
    if NEXT and f and f % NEXT == 0 and mem[sym['vec_in_game']] and mem[sym['current_level']] < MAXLV - 1:
        mem[sym['current_level']] += 1; mem[sym['player_dead']] = 3      # как скрипт finish_level
        hist.append((f, [f'->уровень{mem[sym["current_level"]] + 1}']))
    run_frame(play)
print(f'{ST} seed {SEED}: {FRAMES} кадров, {ticks[0]} тиков — нарушений нет; макс. грязных прямоугольников {ndr_max[0]} '
      f'(кадр, тик, экран: {ndr_at[0]}); '
      f'уровень {mem[sym["current_level"]] + 1}, экран в конце {mem[sym["current_levelx"]]},{mem[sym["current_levely"]]}')
