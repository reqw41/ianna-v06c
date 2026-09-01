#!/usr/bin/env python3
"""Отладка адаптивного темпа анимации: гистограмма (FrameCounter - vec_tick_fc) на входе в vec_anim_calc
и хода долга vec_anim_debt. Запуск: python3 tools/anim_debug.py [--start=X,Y] [--frames=600]"""
import sys, pathlib, collections
sys.argv_keep=sys.argv[1:]
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FRAMES=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'600'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=[]; cpu=rv.make_cpu(keys)
rom=open('build/ianna.rom','rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100
mem=cpu.mem
CALC=sym['vec_anim_calc']; FC=sym['FrameCounter']; PREV=sym['vec_tick_fc']; DEBT=sym['vec_anim_debt']
SC=sym.get('setup_current_screen', sym.get('game'))
cyc=[0]; next_irq=FRAME; delivered=lost=0
w=rv.Warmup(sym,keys); started=False; patched=False
def stepframe():
    global next_irq, delivered, lost
    end=cyc[0]+FRAME
    while cyc[0]<end:
        pc=cpu.pc
        yield pc
        if cpu.halted: cyc[0]=next_irq
        else: cyc[0]+=CYC[mem[pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1
for fr in range(1500):
    for pc in stepframe():
        if START and not patched and pc==SC:
            mem[sym['current_levelx']]=START[0]; mem[sym['current_levely']]=START[1]; patched=True
        if w.step(pc,fr): started=True
    if started: break
assert started,'игра не стартовала'
keys.clear()
hist=collections.Counter(); debts=[]; trace=[]
for fr in range(FRAMES):
    for pc in stepframe():
        if pc==CALC:
            hist[(mem[FC]-mem[PREV])&0xFF]+=1
            debts.append(mem[DEBT])
            trace.append(((mem[FC]-mem[PREV])&0xFF, mem[DEBT]))
print('frames_lock =', mem[sym['frames_lock']], ' FRAMES_LOCK equ:', [l for l in open('build/ianna_vec.lst') if 'FRAMES_LOCK' in l and 'equ' in l][:1])
print('разница FrameCounter за тик (кадров: сколько тиков):',
      ' '.join(f'{k}:{v}' for k,v in sorted(hist.items())))
print('первые 25 тиков (разница, долг на входе):', trace[:25])
if debts:
    print(f'долг: мин {min(debts)}, макс {max(debts)}, сред {sum(debts)/len(debts):.1f}; '
          f'замедлено {sum(1 for d in debts if d>=8)/len(debts)*100:.0f} % тиков')
