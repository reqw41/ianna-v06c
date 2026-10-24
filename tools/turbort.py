#!/usr/bin/env python3
"""Стенд «дискета на Векторе Турбо+»: как fddrt.py (загрузка с дискеты, прерывания по тактам, меню, читы),
но память и порты ведут себя как на Турбо+ (docs/TURBO.md, модель vturbo-js `vt_address`, ядро MiSTer):
  - окно квазидиска порта 10h: бит 5 и маска порта 42h по 8 КБ (бит N — адреса N*8К..), биты 6 и 7 порта 10h
    не действуют; до turbo_init 42h = FFh (как оставляет ПЗУ);
  - стековый режим (бит 4 порта 10h) — только для PUSH, POP и XTHL; CALL, RET, RST и адрес возврата
    прерывания идут в обычную память;
  - порт 45h: б7 = 1 в первые такты кадра (кадровый импульс) — по нему turbo_init узнаёт машину.
Считает, что на Турбо+ сломалось бы: прерывания, принятые в стековом режиме, `ei` и `halt` в стековом режиме,
`halt` при запрещённых прерываниях (зависание), обращения к 8000–9FFF, где окно на 06Ц и на Турбо+ разное.
  python3 tools/turbort.py [--frames=7200] [--cheat] [--intro] [--shot=dir]
"""
import sys, os, pathlib, re, bisect, collections
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
ROOT = pathlib.Path(__file__).resolve().parents[1]
FR = int(next((o[9:] for o in OPTS if o.startswith('--frames=')), '7200'))
edd = ROOT / 'build/_turbort.edd'
edd.write_bytes(bytes(262144))
os.environ['IANNA_EDD'] = str(edd); os.environ['IANNA_FDD'] = str(ROOT / 'build/ianna.fdd')
sys.argv = [sys.argv[0]]; sys.path.insert(0, str(ROOT / 'tools')); import run_vec as rv
src = open(ROOT / 'tools/profile_vec.py').read(); i = src.index('# Такты ВЕКТОРА'); j = src.index('keys = []'); exec(src[i:j])
LST = ROOT / 'build/ianna_vec.lst'; sym = rv.load_syms(LST)
_s = {}
for line in open(LST, encoding='utf-8', errors='replace'):
    m = re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):', line)
    if m: _s.setdefault(int(m.group(1), 16), m.group(2))
_a = sorted(_s); _n = [_s[a] for a in _a]
def fn(pc):
    if pc >= 0x8000: return '$%04X' % (pc & 0xFF00)
    k = bisect.bisect_right(_a, pc) - 1; return _n[k] if k >= 0 else '?'

keys = []; cpu = rv.make_cpu(keys); mem = cpu.mem
_img = open(os.environ['IANNA_FDD'], 'rb').read(); mem[0x100:0x100 + 32512] = _img[0x80:0x80 + 32512]
STACKOPS = {0xC1, 0xC5, 0xD1, 0xD5, 0xE1, 0xE5, 0xF1, 0xF5, 0xE3}
T = {'p42': 0xFF, 'sop': False, 'p44': 0xC0, 'spmin': (0x7E00, '')}
EV = collections.defaultdict(collections.Counter)     # вид события -> (функция, адрес) -> раз

def _kv_turbo(a, stackrq=False):
    cw = cpu.kv_cw
    if (cw & 0x10) and stackrq and T['sop']:
        return True, ((cw & 0x0C) >> 2) * 65536 + a
    if (cw & 0x20) and (T['p42'] >> (a >> 13)) & 1:
        tur = True
    else:
        tur = False
    v06 = (cw & 0x20 and 0xA000 <= a <= 0xDFFF) or (cw & 0x40 and 0x8000 <= a <= 0x9FFF) or (cw & 0x80 and 0xE000 <= a)
    if tur != bool(v06): EV['окно расходится с 06Ц'][(fn(cpu.pc), '%02X/%02X' % (cw, T['p42']))] += 1
    return (True, (cw & 3) * 65536 + a) if tur else (False, a)
cpu._kv_addr = _kv_turbo

_step = cpu.step
def step():
    op = cpu.rb(cpu.pc)
    T['sop'] = op in STACKOPS
    if cpu.kv_cw & 0x10:
        if op == 0xFB: EV['ei в стековом режиме'][(fn(cpu.pc), '%04X' % cpu.pc)] += 1
        if op == 0x76: EV['halt в стековом режиме'][(fn(cpu.pc), '%04X' % cpu.pc)] += 1
        if op in (0xCD, 0xC9) or (op & 0xC7) in (0xC4, 0xC0, 0xC7):
            EV['call/ret/rst в стековом режиме'][(fn(cpu.pc), '%04X' % cpu.pc)] += 1
    _step()
    T['sop'] = False
    if not (cpu.kv_cw & 0x10) and 0x7C00 <= cpu.sp < 0x7E00 and cpu.sp < T['spmin'][0]: T['spmin'] = (cpu.sp, fn(cpu.pc))
cpu.step = step

_oh = cpu.out_handler; _ih = cpu.in_handler
def oh(p, v):
    if p == 0x42: T['p42'] = v
    elif p == 0x44: T['p44'] = v
    elif p in (0x40, 0x41, 0x43, 0x46, 0x45, 0x47): pass
    else: return _oh(p, v)
def ih(p):
    if p == 0x45: return 0x80 if cyc - (nxt - FRAME) < 3000 else 0x00
    return _ih(p)
cpu.out_handler = oh; cpu.in_handler = ih

CHEAT = '--cheat' in OPTS; INTRO = '--intro' in OPTS
SHOTDIR = next((o[7:] for o in OPTS if o.startswith('--shot=')), None)
if SHOTDIR: os.makedirs(SHOTDIR, exist_ok=True)
FRAME = 59904; cyc = 0; nxt = FRAME; fr = 0; lost = 0; ev = []; seen = collections.Counter(); hang = None
names = {sym[k]: k for k in ('vec_start', 'turbo_init', 'vfl_go', 'vfl_done', 'vec_menu_phase', 'vec_begin_level', 'RunScripts', 'vec_reload_set') if k in sym}
while fr < FR:
    pc = cpu.pc
    if pc in names:
        seen[names[pc]] += 1
        if seen[names[pc]] <= 2: ev.append((fr, names[pc]))
    if cpu.halted:
        if not cpu.ie: hang = (fr, fn(pc), pc); break
        cyc = nxt
    else:
        c = CYC[mem[pc]]
        cyc += c // 4 if (T['p44'] & 0xC0) == 0 else c       # 12 МГц: команда вчетверо короче
        try: cpu.step()
        except RuntimeError as e: ev.append((fr, 'КРАХ pc=%04X %s' % (pc, str(e)[:60]))); break
    if cyc >= nxt:
        nxt += FRAME; fr += 1
        if CHEAT:
            plan = {2300: ['f1', 'f3'], 2320: [], 2400: ['fire'], 2420: [], 2600: ['fire'], 2620: [], 2800: ['fire'], 2820: [], 3000: ['fire'], 3020: [],
                    3250: ['fire'], 3270: [], 3400: ['fire'], 3420: [], 3600: ['i'], 3610: [], 3700: ['g'], 3710: [], 3800: ['right'], 4500: ['l'], 4510: []}
            if fr in plan: keys[:] = plan[fr]
            if fr > 4600 and fr % 200 == 0: keys[:] = ['fire']
            if fr > 4600 and fr % 200 == 20: keys[:] = []
        elif INTRO:
            ip = {2350: ['fire'], 2370: [], 2750: ['fire'], 2770: [], 3150: ['fire'], 3170: [], 3550: ['fire'], 3570: [], 3900: ['fire'], 3920: []}
            if fr in ip: keys[:] = ip[fr]
        else:
            if fr in range(2000, FR, 200): keys[:] = ['fire']
            if fr in range(2020, FR, 200): keys[:] = []
        if SHOTDIR and fr % 300 == 0:
            rv.render(bytes(mem[0x8000:0x10000]), list(mem[sym['vec_palette']:sym['vec_palette'] + 16]), f'{SHOTDIR}/t_{fr}.png')
        if cpu.ie:
            if cpu.kv_cw & 0x10: EV['прерывание в стековом режиме'][(fn(cpu.pc), '%04X' % cpu.pc)] += 1
            cpu.ie = False; cpu.halted = False; T['sop'] = False; cpu.push(cpu.pc); cpu.pc = 0x38
        else: lost += 1
print('события (кадр, точка):', ev[:24])
print('потеряно прерываний', lost, '; RunScripts', seen['RunScripts'], '; кадров', fr, '; в конце PC=%04X (%s)' % (cpu.pc, fn(cpu.pc)))
print('Турбо+: vec_turbo =', mem[sym['vec_turbo']] if 'vec_turbo' in sym else '?', '; 42h = %02X, 44h = %02X' % (T['p42'], T['p44']))
print('глубина стека: SP до $%04X (%s), %d Б от $7E00; место под стек — 147 Б' % (T['spmin'][0], T['spmin'][1], 0x7E00 - T['spmin'][0]))
if hang: print('ЗАВИСАНИЕ: halt при запрещённых прерываниях на кадре %d, %s ($%04X)' % hang)
for k, c in EV.items():
    print(f'{k}: {sum(c.values())} раз;', ', '.join(f'{a} {b}: {n}' for (a, b), n in c.most_common(12)))
if not EV and not hang: print('нарушений нет')
