#!/usr/bin/env python3
"""Профиль headless-прогона: инструкции по функциям (метки из build/ianna_vec.lst).
python3 tools/profile_vec.py [frames_run=300]  — ждём сообщение, Z, бег вправо."""
import os, sys, re, bisect, collections, pathlib
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
# Такты ВЕКТОРА-06Ц по опкоду: модель слотов шины (cpu_ready — не более одного обращения к шине
# за 4 такта): слоты = M1 + обращения к памяти + порты + ceil(внутренние/4), такт = 4 слота;
# внутренние = T(8080) - 4*M1 - 3*память - 4*порты. Совпадает с таблицей vector06js (MOV r,r=8, LHLD=20,
# CALL=24, PUSH=16). Условные переходы/вызовы — как взятые (верхняя граница).
def _vec_cycles(t, mem, port=0):
    internal = t - 4 - 3*mem - 4*port
    slots = 1 + mem + port + max(0, (internal + 3)//4)
    return 4*slots
CYC=[4]*256
for op in range(256):
    hi,lo=op>>6,op&7; d=(op>>3)&7
    if hi==1: CYC[op]=_vec_cycles(7,1) if (lo==6 or d==6) else _vec_cycles(5,0)        # MOV (HLT: op 0x76)
    elif hi==2: CYC[op]=_vec_cycles(7,1) if lo==6 else _vec_cycles(4,0)                   # ALU r/M
    elif hi==0:
        if lo==6: CYC[op]=_vec_cycles(10,2) if d==6 else _vec_cycles(7,1)                 # MVI M / MVI r
        elif lo==1: CYC[op]=_vec_cycles(10,2) if (op&8)==0 else _vec_cycles(10,0)          # LXI / DAD
        elif lo==2: CYC[op]={0x22:_vec_cycles(16,4),0x2A:_vec_cycles(16,4),0x32:_vec_cycles(13,3),0x3A:_vec_cycles(13,3)}.get(op,_vec_cycles(7,1))  # SHLD/LHLD/STA/LDA/STAX/LDAX
        elif lo==3: CYC[op]=_vec_cycles(5,0)                                                # INX/DCX
        elif lo in (4,5): CYC[op]=_vec_cycles(10,2) if d==6 else _vec_cycles(5,0)           # INR/DCR
        else: CYC[op]=_vec_cycles(4,0)
    else:
        if lo==0: CYC[op]=_vec_cycles(11,2)     # Rcc (взятый)
        elif lo==1: CYC[op]={0xC9:_vec_cycles(10,2),0xE9:_vec_cycles(5,0),0xF9:_vec_cycles(5,0)}.get(op,_vec_cycles(10,2))  # POP/RET/PCHL/SPHL
        elif lo==2: CYC[op]=_vec_cycles(10,2)   # Jcc
        elif lo==3: CYC[op]={0xC3:_vec_cycles(10,2),0xD3:_vec_cycles(10,1,1),0xDB:_vec_cycles(10,1,1),0xE3:_vec_cycles(18,4),0xEB:_vec_cycles(4,0),0xF3:_vec_cycles(4,0),0xFB:_vec_cycles(4,0)}.get(op,_vec_cycles(10,2))
        elif lo==4: CYC[op]=_vec_cycles(17,4)   # Ccc (взятый)
        elif lo==5: CYC[op]=_vec_cycles(17,4) if op==0xCD else _vec_cycles(11,2)   # CALL / PUSH
        elif lo==6: CYC[op]=_vec_cycles(7,1)    # ALU imm
        else: CYC[op]=_vec_cycles(11,2)         # RST
CYC[0x76]=_vec_cycles(7,0)
keys = []
cpu = rv.make_cpu(keys)
sym = rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
rv.start_game(cpu, keys, sym)
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
for k, v in cnt.most_common(int(os.environ.get('PROFILE_TOP', '32'))): print(f'  {v/total*100:5.1f}%  {k}')
