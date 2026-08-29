#!/usr/bin/env python3
"""Профиль headless-прогона: инструкции по функциям (метки из build/ianna_vec.lst).
python3 tools/profile_vec.py [frames_run=300]  — ждём сообщение, Z, бег вправо."""
import sys, re, bisect, collections, pathlib
sys.argv = [sys.argv[0]]  # run_vec разбирает argv
sys.path.insert(0, 'tools')
import run_vec as rv
n_run = 300
syms = {}
for line in open('build/ianna_vec.lst', encoding='utf-8', errors='replace'):
    m = re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):', line)
    if m: syms.setdefault(int(m.group(1), 16), m.group(2))
addrs = sorted(syms); names = [syms[a] for a in addrs]
def fn(pc):
    i = bisect.bisect_right(addrs, pc) - 1
    return names[i] if i >= 0 else '?'
# такты i8080 по опкоду (условные переходы/вызовы — по максимуму)
CYC=[4]*256
for op in range(256):
    hi,lo=op>>6,op&7
    if hi==1: CYC[op]=7 if (op&7)==6 or ((op>>3)&7)==6 else 5      # MOV
    elif hi==2: CYC[op]=7 if lo==6 else 4                            # ALU r/M
    elif hi==0:
        if lo==6: CYC[op]=10 if op==0x36 else 7                     # MVI
        elif lo==1: CYC[op]=10                                       # LXI/DAD
        elif lo==2: CYC[op]={0x22:16,0x2A:16,0x32:13,0x3A:13}.get(op,7)  # STAX/LDAX/SHLD/LHLD/STA/LDA
        elif lo in (3,): CYC[op]=5                                   # INX/DCX
        elif lo in (4,5): CYC[op]=10 if (op>>3)&7==6 else 5          # INR/DCR
        else: CYC[op]=4
    else:
        if lo==0: CYC[op]=11    # Rcc
        elif lo==1: CYC[op]={0xC9:10,0xE9:5,0xF9:5}.get(op,10)       # POP/RET/PCHL/SPHL
        elif lo==2: CYC[op]=10  # Jcc
        elif lo==3: CYC[op]={0xC3:10,0xD3:10,0xDB:10,0xE3:18,0xEB:4,0xF3:4,0xFB:4}.get(op,10)
        elif lo==4: CYC[op]=17  # Ccc
        elif lo==5: CYC[op]={0xCD:17}.get(op,11)                     # PUSH/CALL
        elif lo==6: CYC[op]=7   # ALU imm
        else: CYC[op]=11        # RST
CYC[0x76]=7
keys = []
cpu = rv.make_cpu(keys)
sym = rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
rv.run_frames(cpu, 500, sym=sym); keys.append('fire'); rv.run_frames(cpu, 40, sym=sym); keys.clear(); rv.run_frames(cpu, 10, sym=sym)
keys.append('right')
cnt = collections.Counter(); total = 0; per_frame = []
WATCH = ['RedrawScreen','drawTile','drawFGTile','drawSprite','drawChar','fillArea','draw_barbarian_state','draw_enemy_state','draw_score_status','z_exx','Div16_8','vec_pool_flush','LoadScreen','InvalidateSTiles','AnimateSTiles','RunScripts','CheckSprOverlap']
ent = {}
for a,nm in syms.items():
    if nm in WATCH: ent[a]=nm
calls = collections.Counter()
step = cpu.step; mem = cpu.mem
for _ in range(n_run):
    c = 0; fc = 0
    while not cpu.halted and c < 13000:
        w = CYC[mem[cpu.pc]]; cnt[fn(cpu.pc)] += w
        if cpu.pc in ent: calls[ent[cpu.pc]] += 1
        step(); c += 1; total += w; fc += w
    per_frame.append(fc)
    cpu.halted = False
    if cpu.ie:
        cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
cat = collections.Counter()
for k, v in cnt.items():
    if k.startswith('z_'): cat['хелперы Z80 (z_*)'] += v
    elif k.startswith(('vec_isr', 'isr_', 'get_joystick')): cat['ISR (палитра/клавиатура)'] += v
    elif k.startswith(('PLY', 'MUSIC', 'FX_', 'Ply')): cat['музыка (Arkos)'] += v
    elif k.startswith(('vec_', 'draw', 'dt_', 'dtb', 'dft', 'ds_', 'dsp', 'vpf', 'vb_', 'vbc', 'vss', 'dso', 'fill')): cat['блиттер/пул (vec_vdp)'] += v
    else: cat['логика игры (перевод)'] += v
print(f'кадров {n_run}, тиков ~{n_run//5}, тактов всего {total}, на кадр {total/n_run:.0f}, на тик {total/(n_run/5):.0f} (кадр = 59904)')
ticks = [sum(per_frame[i:i+5]) for i in range(0, n_run, 5)]
nt = max(1, calls['RedrawScreen']); print(f'реальных тиков (RedrawScreen): {nt} -> {total/nt:.0f} тактов/тик = {total/nt/59904:.2f} кадра')
for k in WATCH: print(f'  {k}: {calls[k]} вызовов, {calls[k]/nt:.1f}/тик')
print('такты по тикам (5 кадров):', ' '.join(str(t//1000)+'K' for t in ticks))
for k, v in cat.most_common(): print(f'  {v/total*100:5.1f}%  {k}')
print('топ функций:')
for k, v in cnt.most_common(32): print(f'  {v/total*100:5.1f}%  {k}')
