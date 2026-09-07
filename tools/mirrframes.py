"""Какие кадры каких банков рисуются ЗЕРКАЛЬНО: (банк, кадр) с частотой, по сцене.

  python3 tools/mirrframes.py <rom> <lst> <edd> X,Y <уровень> [тиков] [--lr]

Стенд тот же, что у gates.sh/abcyc/cmpbuild: --norand, клавиша «вправо», N тиков.
С --lr вместо этого 120 тиков влево / 120 вправо / 120 без клавиш — так видно кадры,
которые на гейт-сцене не всплывают, но встречаются в живой игре.
С --route=left:20,none:5,fire+left:35 (тики) прогон идёт ровно тем маршрутом и с тем
прогревом (--settle=30, номер тика от НАЧАЛА прогрева), что у tools/proftick.py: иначе
кадры меча (bank 2, 22..36) не всплывают вовсе, а именно они дают dspm_row в профиле.

Хук стоит на входе vec_mirror_src (vec_vdp.asm зовёт его для КАЖДОГО спрайта сразу после
`ld (vec_spr_dir),a`): там vec_spr_src/dir/port уже свои, а подмена ещё не произошла.
Прежняя версия ловила вход drawSprite, где vec_spr_src ещё от ПРЕДЫДУЩЕГО спрайта.

Столбцы: сколько выводов банка всего, сколько из них зеркальных, сколько зеркальных уже
закрыто готовыми копиями (подмена ловится по метке vm_hit) и какие кадры остались на лету.
"""
import sys, os, pathlib, collections
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, L = A[0], A[1], A[2], A[3], int(A[4])
N = int(A[5]) if len(A) > 5 else 60
LR = '--lr' in OPTS
ROUTE = next((o[8:] for o in OPTS if o.startswith('--route=')), None)
SETTLE = int(next((o[9:] for o in OPTS if o.startswith('--settle=')), '30'))
os.environ['IANNA_EDD'] = EDD
sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools'); sys.path.insert(0, 'tools/data')
import run_vec as rv; import build_edd as B
rv.STEP_BUDGET = 400000
sym = rv.load_syms(pathlib.Path(LST))
keys = []; cpu = rv.make_cpu(keys)
rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100
rv.patch_menu(cpu)
# ГПСЧ отвязываем ровно как cmpbuild --norand: иначе сцена другая, чем та, что меряют гейты
a = sym['random']; rd = sym['randData']
cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
rv.START = tuple(int(v) for v in ST.split(','))
if ROUTE is None:
    rv.start_game(cpu, keys, sym)
    warm_ticks = 0
else:
    # прогрев ровно как в proftick: тики считаются С НАЧАЛА, маршрут включается на тике SETTLE
    rv._start_done[0] = False
    _RS = sym['RunScripts']; _FC = sym['FrameCounter']
    w = rv.Warmup(sym, keys); done = False; warm_ticks = 0
    for fr in range(1500):
        c = 0
        while not cpu.halted and c < rv.STEP_BUDGET:
            pc = cpu.pc
            if not rv._start_done[0] and pc == sym['SaveCheckpoint']:
                cpu.mem[sym['current_levelx']] = rv.START[0]; cpu.mem[sym['current_levely']] = rv.START[1]
                rv._start_done[0] = True
            if w.step(pc, fr): done = True
            if pc == _RS: warm_ticks += 1; cpu.mem[_FC] = warm_ticks & 0xFF
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
        if done: break
    assert done
    keys.clear()

VM = sym['vec_mirror_src']; HIT = sym['vm_hit']; SRC = sym['vec_spr_src']; DIR = sym['vec_spr_dir']
PORT = sym['vec_spr_port']
RS = sym['RunScripts']; FC = sym['FrameCounter']; mem = cpu.mem
two = B.BANK_2PLANE_BY_LEVEL.get(L, set())
banks = list(B.LEVEL_BANKS[L])
cnt = collections.Counter(); tot = collections.Counter(); mtot = collections.Counter()
sub = collections.Counter()          # (банк, кадр) -> сколько раз подменён готовой копией
last = [None]

def hit():
    src = mem[SRC] | (mem[SRC+1] << 8); pg = (mem[PORT] >> 2) & 3; d = mem[DIR]
    last[0] = None
    for b, bpg, base, lim in banks:
        if bpg == pg and base <= src < lim:
            fb = 288 if b in two else 576
            k = (src - base) // fb
            tot[b] += 1
            if d: cnt[(b, k)] += 1; mtot[b] += 1; last[0] = (b, k)
            return

ticks = warm_ticks; step = cpu.step
RT = None
if ROUTE is not None:
    RT = [(int(s.split(':')[1]), [k for k in s.split(':')[0].split('+') if k != 'none'])
          for s in ROUTE.split(',')]
    NT = SETTLE + sum(n for n, _ in RT); count_from = SETTLE
elif LR:
    keys.append('left'); NT = 360; count_from = 0
else:
    keys.append('right'); NT = N; count_from = 0
counting = [count_from == 0]
while ticks < NT:
    if LR and ticks == 120: keys.clear(); keys.append('right')
    if LR and ticks == 240: keys.clear()
    while not cpu.halted:
        if cpu.pc == VM:
            if counting[0]: hit()
        elif cpu.pc == HIT:
            if counting[0] and last[0]: sub[last[0]] += 1   # подмена состоялась: дальше прямой блит
        elif cpu.pc == RS:
            ticks += 1; mem[FC] = ticks & 0xFF
            if RT is not None and ticks >= SETTLE:
                counting[0] = True
                k = ticks - SETTLE; acc = 0
                for n, ks in RT:
                    acc += n
                    if k < acc: keys[:] = ks; break
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38

NAME = {b: B.BANK_FILE[b].replace('sprite_', '') for b in B.BANK_FILE}
tag_route = f' (маршрут {ROUTE}, прогрев {SETTLE})' if ROUTE else (' (влево/вправо/стоя)' if LR else '')
print(f'ур.{L} сцена {ST}, {NT - (SETTLE if ROUTE else 0)} тиков{tag_route}: зеркальных выводов '
      f'{sum(mtot.values())} из {sum(tot.values())}')
for b, bpg, base, lim in banks:
    if not tot[b]: continue
    fb = 288 if b in two else 576
    got = [f'{k}x{sub[(b,k)]}' for (bb, k), n in sorted(cnt.items()) if bb == b and sub[(b, k)]]
    left = [f'{k}x{n-sub[(b,k)]}' for (bb, k), n in sorted(cnt.items()) if bb == b and n > sub[(b, k)]]
    nleft = sum(n - sub[(b, k)] for (bb, k), n in cnt.items() if bb == b)
    tag = '2пл' if b in two else '16ц'
    print(f'  банк {b:2} {NAME[b]:22} {tag} стр.{bpg} ${base:04X}: выводов {tot[b]:5}, зеркальных {mtot[b]:5}'
          f' (копиями закрыто {mtot[b]-nleft}, на лету {nleft})')
    if got:  print(f'      закрыто копиями: {" ".join(got)}')
    if left: print(f'      РАЗВОРОТ НА ЛЕТУ: {" ".join(left)}   (кадр {fb} Б)')
