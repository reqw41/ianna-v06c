#!/usr/bin/env python3
"""СЧЁТНАЯ МОДЕЛЬ РЕНДЕРА: минимум против факта по каждому пути блиттера.

Прогон детерминированный (как cmpbuild/abcyc, по умолчанию --norand). Каждая операция вывода
(drawTile / drawFGTile / готовый тайл fgc / drawSprite / сброс пула / панель) прослеживается от
входной метки до возврата по адресу, снятому со стека при входе. Внутри операции считаются:

  W    — сколько БАЙТ реально записано в VRAM ($8000-$FFFF, не через окно квазидиска);
  R    — сколько байт VRAM прочитано (маскированные пути: read-modify-write);
  SRC  — сколько байт источника вытащено из квазидиска стеком (pop в стековом режиме);
  такты — по модели шины Вектора (tools/profile_vec.py, cpu_ready) с разбивкой на
          «блит» (внутренние циклы), «бюджет» (vec_budget/vec_spr_colbud), «стек» (вход/выход
          стекового режима) и «обвязка» (всё остальное внутри операции).

ТЕОРЕТИЧЕСКИЙ МИНИМУМ на i8080 при cpu_ready (такт = 8 на одно обращение к шине):
  источник:      pop даёт 2 байта за 12 тактов          ->  6 т/байт источника
  запись байта:  ld (hl),r                              ->  8 т
  маскирование:  and (hl) (чтение) 8 + ld a,mask 8 + or data 8 -> 24 т на прочитанный байт
  шаг адреса:    считается по ФАКТИЧЕСКОЙ последовательности адресов назначения —
                 сосед по L (та же страница):        8  (inc l / dec l)
                 та же страница, произвольный L:     8  (ld l,r)
                 соседняя страница (dH = +-1):       8  (inc h / dec h) + 8, если сменился L
                 дальняя страница (плоскость +$20): 24  (ld a,h / add a,n / ld h,a) + 8 за L
  ИТОГО  min = SRC*6 + W*8 + R*24 + STEPS
Проверка на известных циклах: непрозрачный тайл 128 Б (SRC=W=128, R=0, шаги 120*8 внутри колонок,
4*16 между колонками, 3*24 между плоскостями) -> 2888 тактов; это ровно лучший возможный цикл
`pop bc/ld (hl),c/dec l/ld (hl),b/dec l` (44 т на 2 байта = 2816) плюс неизбежные переходы колонок.
Оговорка: у двухплоскостного пути плоскости 0 и 1 гасятся без `or` (на 8 т/байт дешевле) — там
минимум завышен, то есть доля обвязки ЗАНИЖЕНА; всякая оценка обвязки здесь — оценка СНИЗУ.

  python3 tools/blit_model.py <rom> <lst> <edd> X,Y <тиков> [--rand] [--ops]
"""
import sys, os, re, bisect, pathlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, N = A[0], A[1], A[2], A[3], int(A[4])
os.environ['IANNA_EDD'] = EDD
if 'demo' in pathlib.Path(ROM).name:
    sys.exit('ОТКАЗ: демо-ROM не несёт сцен — мерить только build/ianna.rom того же коммита.')
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); import run_vec as rv
src = open('tools/profile_vec.py').read()
exec(src[src.index('# Такты ВЕКТОРА'):src.index('keys = []')])
rv.STEP_BUDGET = 400000

# --- метки: СТРОГИЙ разбор lst. Свободный (как в profile_vec/abcyc) ловит слова с двоеточием
# из КОММЕНТАРИЕВ («SPR3CLR: плоскость 3 только чистим») и вешает на них чужие такты.
syms = {}
for line in open(LST, encoding='utf-8', errors='replace'):
    m = re.match(r'([0-9A-F]{4}):\s+([A-Za-z_][A-Za-z_0-9.]*):', line)
    if m: syms.setdefault(int(m.group(1), 16), m.group(2))
addrs = sorted(syms); names = [syms[a] for a in addrs]
def fn(pc):
    k = bisect.bisect_right(addrs, pc) - 1
    return names[k] if k >= 0 else '?'

sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100 + len(rom)] = rom; cpu.pc = 0x100
rv.patch_menu(cpu)
if '--rand' not in OPTS:
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
keys.append('right')

# --- точки входа операций вывода (имя -> подпись) и внутренние циклы (метка -> путь)
ENTRY = {'drawTile': 'тайл фона', 'drawFGTile': 'тайл FG', 'drawSprite': 'спрайт',
         'vec_pool_flush': 'сброс пула', 'drawChar': 'символ панели', 'fillArea': 'шкала панели',
         'fgc_entry': 'готовый тайл FGC', 'vec_load_panel': 'картинка панели'}
INNER = {'vb_col': 'блит128', 'vb_plane': 'блит128', 'vbc_row': 'колонки', 'vbc_col': 'колонки',
         'dtb_loop': 'тайл->пул', 'dft_col': 'FG прямой', 'dft_plane': 'FG прямой',
         'dftb_loop': 'FG->пул', 'ds_row': 'спр16 прямой', 'ds_k': 'спр16 прямой',
         'dsm_row': 'спр16 зерк', 'dsm_k': 'спр16 зерк', 'dsp_row': 'спр16 прямой пул',
         'dsp_k': 'спр16 прямой пул', 'dspm_row': 'спр16 зерк пул', 'dspm_k': 'спр16 зерк пул',
         'b2_row': 'спр2пл прямой', 'b2m_row': 'спр2пл зерк',
         # двухплоскостной спрайт в слот пула: тело строки своё, пролог сегмента общий
         'b2p_row': 'спр2пл прямой пул', 'b2p_rowb': 'спр2пл прямой пул',
         'b2p_endA': 'спр2пл прямой пул', 'b2p_endB': 'спр2пл прямой пул',
         'b2pm_row': 'спр2пл зерк пул', 'b2pm_rowb': 'спр2пл зерк пул',
         'b2pm_endA': 'спр2пл зерк пул', 'b2pm_endB': 'спр2пл зерк пул',
         # хвосты циклов после перевода счётчика строк на L (самомодифицируемый предел)
         'b2_endA': 'спр2пл прямой', 'b2_endB': 'спр2пл прямой',
         'ds_end': 'спр16 прямой', 'ds_rem': 'спр16 прямой',
         'dsp_end': 'спр16 прямой пул', 'dsp_rem': 'спр16 прямой пул',
         'dspm_end': 'спр16 зерк пул', 'dspm_rem': 'спр16 зерк пул',
         'dsm_k': 'спр16 зерк'}
BUDGET = {'vec_budget', 'vbg_again', 'vbg_wait', 'vbg_ok', 'vec_phase', 'vph_ok', 'vec_spr_colbud'}
STK = {'vec_stk_enter', 'vec_stk_leave'}
entry_pc = {sym[k]: v for k, v in ENTRY.items() if k in sym}
# Оверлеи в ОЗУ своих меток в ianna_vec.lst не имеют — их адреса известны из набора уровня:
# $7200 = fgc_ovl (готовые тайлы фон+FG), $7F00 = blit2_ovl (зеркальный двухплоскостной блит).
FGC = sym.get('FGC_ENTRY', 0x7200); B2M = 0x7F00
entry_pc[FGC] = 'готовый тайл FGC'
def bucket(pc, lab):
    if B2M <= pc < B2M + 0x100: return 'блит', 'спр2пл зерк'
    if FGC <= pc < FGC + 0x100: return 'обвязка', None
    if lab in INNER: return 'блит', INNER[lab]
    if lab in BUDGET: return 'бюджет', None
    if lab in STK: return 'стек', None
    return 'обвязка', None

STORE_HL = set(range(0x70, 0x78)) - {0x76} | {0x36, 0x34, 0x35}
LOAD_HL = {0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E,
           0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE, 0x34, 0x35}
POPS = {0xC1, 0xD1, 0xE1, 0xF1}

RS = sym['RunScripts']; FC = sym['FrameCounter']
mem = cpu.mem; step = cpu.step
ticks = 0; tot = 0
cur = None          # [имя, retaddr, корзины тактов, W, R, SRC, пути, шаги адреса, прошлый адрес]
stat = collections.defaultdict(lambda: dict(n=0, cyc=collections.Counter(), W=0, R=0, SRC=0, ST=0))

def stepcost(prev, a):
    """Минимальная цена перевода указателя назначения с адреса prev на a (см. шапку)."""
    if prev is None: return 0
    if (prev ^ a) < 0x100: return 8                       # та же страница: inc l / dec l / ld l,r
    dh = (a >> 8) - (prev >> 8)
    return (8 if dh in (1, -1) else 24) + (0 if (a & 0xFF) == (prev & 0xFF) else 8)

def wrote(c, a):
    c[7] += stepcost(c[8], a); c[8] = a; c[3] += 1
ops = []
outside = 0

def vram(addr):
    """Байт НАЗНАЧЕНИЯ: либо сама VRAM ($8000-$FFFF), либо слот пула — окно $A000-$DFFF на
    страницу 3 квазидиска (буфер под ту же VRAM: путь «в пул» платит за байт дважды, и модель
    показывает обе операции — сборку в пул и сброс пула в VRAM)."""
    return addr >= 0x8000

while ticks < N:
    while not cpu.halted:
        pc = cpu.pc; op = mem[pc] if pc < 0x8000 else cpu.rb(pc)
        w = CYC[op]; tot += w
        if pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        if cur is None:
            if pc in entry_pc:
                cur = [entry_pc[pc], cpu.rb(cpu.sp) | (cpu.rb(cpu.sp + 1) << 8),
                       collections.Counter(), 0, 0, 0, [], 0, None]
            else:
                outside += w
        if cur is not None:
            b, path = bucket(pc, fn(pc))
            cur[2][b] += w
            if path and (not cur[6] or cur[6][-1] != path): cur[6].append(path)
            if op in STORE_HL:
                a = (cpu.h << 8) | cpu.l
                if vram(a): wrote(cur, a)
            elif op == 0x02 and vram((cpu.b << 8) | cpu.c): wrote(cur, (cpu.b << 8) | cpu.c)
            elif op == 0x12 and vram((cpu.d << 8) | cpu.e): wrote(cur, (cpu.d << 8) | cpu.e)
            elif op == 0x32 and vram(cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)): wrote(cur, cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8))
            elif op == 0x22 and vram(cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)):
                wrote(cur, cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)); wrote(cur, (cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)) + 1)
            elif op in (0xC5, 0xD5, 0xE5, 0xF5) and not cpu.kv_stack_mode and vram(cpu.sp - 2):
                wrote(cur, cpu.sp - 1); wrote(cur, cpu.sp - 2)
            if op in LOAD_HL:
                a = (cpu.h << 8) | cpu.l
                if vram(a): cur[4] += 1
            elif op == 0x0A and vram((cpu.b << 8) | cpu.c): cur[4] += 1
            elif op == 0x1A and vram((cpu.d << 8) | cpu.e): cur[4] += 1
            elif op == 0x3A and vram(cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)): cur[4] += 1
            elif op == 0x2A and vram(cpu.rb(pc + 1) | (cpu.rb(pc + 2) << 8)): cur[4] += 2
            if op in POPS and cpu.kv_stack_mode: cur[5] += 2
        step()
        if cur is not None and cpu.pc == cur[1]:
            key = cur[0] + (' / ' + '+'.join(cur[6]) if cur[6] else ' / без блита')
            s = stat[key]; s['n'] += 1; s['cyc'] += cur[2]; s['W'] += cur[3]; s['R'] += cur[4]
            s['SRC'] += cur[5]; s['ST'] += cur[7]
            if '--ops' in OPTS: ops.append((key, sum(cur[2].values()), cur[3], cur[4], cur[5]))
            cur = None
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38

print(f'сцена {ST}: {N} тиков, всего {tot} тактов, на тик {tot/N:.0f}')
print(f'{"путь":34s} {"опер/тик":>8s} {"такт/тик":>8s} {"%тика":>6s} {"такт/оп":>7s} '
      f'{"W":>5s} {"R":>5s} {"мин":>7s} {"обвяз":>6s} | блит бюджет стек обвязка')
rows = sorted(stat.items(), key=lambda kv: -sum(kv[1]['cyc'].values()))
sum_c = sum_min = 0
for k, s in rows:
    c = sum(s['cyc'].values()); n = s['n']
    mn = s['SRC'] * 6 + s['W'] * 8 + s['R'] * 24 + s['ST']
    sum_c += c; sum_min += mn
    print(f'{k:34s} {n/N:8.1f} {c/N:8.0f} {c/tot*100:6.2f} {c/max(n,1):7.0f} '
          f'{s["W"]/max(n,1):5.0f} {s["R"]/max(n,1):5.0f} {mn/max(n,1):7.0f} '
          f'{(c-mn)/c*100 if c else 0:5.0f} % | ' +
          ' '.join(f'{s["cyc"][b]/max(n,1):.0f}' for b in ('блит', 'бюджет', 'стек', 'обвязка')))
print(f'{"ВСЕГО вывод":34s} {"":8s} {sum_c/N:8.0f} {sum_c/tot*100:6.2f} {"":7s} {"":5s} {"":5s} '
      f'{sum_min/N:7.0f} {(sum_c-sum_min)/sum_c*100:5.0f} %')
print(f'вне операций вывода: {outside/N:.0f} такт/тик ({outside/tot*100:.1f} %)')
