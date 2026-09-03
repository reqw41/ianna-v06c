"""Какие кадры каких банков рисуются ЗЕРКАЛЬНО: (банк, кадр) с частотой, по сцене.

  python3 tools/mirrframes.py <rom> <lst> <edd> X,Y <уровень> [тиков] [--lr]

Стенд тот же, что у gates.sh/abcyc/cmpbuild: --norand, клавиша «вправо», N тиков.
С --lr вместо этого 120 тиков влево / 120 вправо / 120 без клавиш — так видно кадры,
которые на гейт-сцене не всплывают, но встречаются в живой игре.

Хук стоит на входе vec_mirror_src (vec_vdp.asm зовёт его для КАЖДОГО спрайта сразу после
`ld (vec_spr_dir),a`): там vec_spr_src/dir/port уже свои, а подмена ещё не произошла.
Прежняя версия ловила вход drawSprite, где vec_spr_src ещё от ПРЕДЫДУЩЕГО спрайта.

Столбцы: сколько выводов банка всего, сколько из них зеркальных, сколько зеркальных уже
закрыто готовыми копиями (MIRRORS_BY_LEVEL) и какие кадры остались разворачиваться на лету.
"""
import sys, os, pathlib, collections
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
A = [a for a in sys.argv[1:] if not a.startswith('--')]
ROM, LST, EDD, ST, L = A[0], A[1], A[2], A[3], int(A[4])
N = int(A[5]) if len(A) > 5 else 60
LR = '--lr' in OPTS
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
rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)

VM = sym['vec_mirror_src']; SRC = sym['vec_spr_src']; DIR = sym['vec_spr_dir']; PORT = sym['vec_spr_port']
RS = sym['RunScripts']; FC = sym['FrameCounter']; mem = cpu.mem
two = B.BANK_2PLANE_BY_LEVEL.get(L, set())
banks = list(B.LEVEL_BANKS[L])
MIRR = B.MIRRORS_BY_LEVEL.get(L, {})
cnt = collections.Counter(); tot = collections.Counter(); mtot = collections.Counter()

def hit():
    src = mem[SRC] | (mem[SRC+1] << 8); pg = (mem[PORT] >> 2) & 3; d = mem[DIR]
    for b, bpg, base, lim in banks:
        if bpg == pg and base <= src < lim:
            fb = 288 if b in two else 576
            k = (src - base) // fb
            tot[b] += 1
            if d: cnt[(b, k)] += 1; mtot[b] += 1
            return

ticks = 0; step = cpu.step
if LR:
    keys.append('left'); NT = 360
else:
    keys.append('right'); NT = N
while ticks < NT:
    if LR and ticks == 120: keys.clear(); keys.append('right')
    if LR and ticks == 240: keys.clear()
    while not cpu.halted:
        if cpu.pc == VM: hit()
        elif cpu.pc == RS: ticks += 1; mem[FC] = ticks & 0xFF
        step()
    cpu.halted = False
    if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38

NAME = {b: B.BANK_FILE[b].replace('sprite_', '') for b in B.BANK_FILE}
print(f'ур.{L} сцена {ST}, {NT} тиков{" (влево/вправо/стоя)" if LR else ""}: зеркальных выводов '
      f'{sum(mtot.values())} из {sum(tot.values())}')
for b, bpg, base, lim in banks:
    if not tot[b]: continue
    fb = 288 if b in two else 576
    spec = MIRR.get(b)
    covered = set(range(spec[1], spec[1]+spec[2])) if spec else set()
    got = [f'{k}x{n}' for (bb, k), n in sorted(cnt.items()) if bb == b and k in covered]
    left = [f'{k}x{n}' for (bb, k), n in sorted(cnt.items()) if bb == b and k not in covered]
    nleft = sum(n for (bb, k), n in cnt.items() if bb == b and k not in covered)
    tag = '2пл' if b in two else '16ц'
    print(f'  банк {b:2} {NAME[b]:22} {tag} стр.{bpg} ${base:04X}: выводов {tot[b]:5}, зеркальных {mtot[b]:5}'
          f' (копиями закрыто {mtot[b]-nleft}, на лету {nleft})')
    if got:  print(f'      закрыто копиями: {" ".join(got)}')
    if left: print(f'      РАЗВОРОТ НА ЛЕТУ: {" ".join(left)}   (кадр {fb} Б)')
