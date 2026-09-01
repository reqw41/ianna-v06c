#!/usr/bin/env python3
"""Headless-замер по тактам (Вектор-06Ц, i8080 3 МГц, кадр 59904 тактов): прерывание в начале обратного
хода НЕ защёлкивается — если INTE=0, теряется (как Emu80/MiSTer). ВИ53 счётчик 0 эмулируется (1.5 МГц,
режим 0, latch по out $08=0) — для таймерного бюджета. Печатает: доставлено/потеряно прерываний,
тиков, кадров/тик, где терялись (по функциям).
  python3 tools/measure_vec.py [rom lst] [--route=right:300] [--start=3,1] [--frames=600] [--fixrand]
  IANNA_EDD=<edd> — образ квазидиска для этой сборки
"""
import sys, re, bisect, collections, pathlib
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]; OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROM=ARGS[0] if ARGS else 'build/ianna.rom'; LST=ARGS[1] if len(ARGS)>1 else 'build/ianna_vec.lst'
FRAMES=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'600'))
ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'none:300,right:300')
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FIXRAND='--fixrand' in OPTS   # FrameCounter := номер тика перед RunScripts — логика не зависит от скорости сборки (сравнение A/B на сценах с врагами)
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100
mem=cpu.mem
# --- ВИ53 счётчик 0 ---
pit={'reload_cyc':0,'latched':None,'wr':0,'rd':0,'lo':0}
base_out=cpu.out_handler; base_in=cpu.in_handler
cyc=[0]
def out_h(p,v):
    if p==0x08:
        if v==0: pit['latched']=(0xFFFF-(((cyc[0]-pit['reload_cyc'])//2)&0xFFFF))&0xFFFF; pit['rd']=0
        return
    if p==0x0B:
        if pit['wr']==0: pit['lo']=v; pit['wr']=1
        else: pit['wr']=0; pit['reload_cyc']=cyc[0]
        return
    base_out(p,v)
def in_h(p):
    if p==0x0B:
        v=pit['latched'] if pit['latched'] is not None else (0xFFFF-(((cyc[0]-pit['reload_cyc'])//2)&0xFFFF))&0xFFFF
        if pit['rd']==0: pit['rd']=1; return v&0xFF
        pit['rd']=0; pit['latched']=None; return v>>8
    return base_in(p)
cpu.out_handler=out_h; cpu.in_handler=in_h
FC=sym['FrameCounter']; AT=sym['animate_tile']; SC=sym['SaveCheckpoint']
delivered=0; lost=0; lost_at=collections.Counter(); next_irq=FRAME; started=False
def run(nframes):
    global delivered,lost,next_irq,started
    end=cyc[0]+nframes*FRAME
    while cyc[0]<end:
        if cpu.halted:
            cyc[0]=next_irq
        else:
            if START and not started and cpu.pc==SC:
                mem[sym['current_levelx']]=START[0]; mem[sym['current_levely']]=START[1]; started=True
            cyc[0]+=CYC[mem[cpu.pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie:
                cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else:
                lost+=1; lost_at[fn(cpu.pc)]+=1
HOLD=None
def rd(a): return mem[a]
ntick=[0]
w=rv.Warmup(sym,keys); patched=False; started=False   # прогрев общий с run_vec (сообщение уровня снимается автоматически)
for fr in range(1500):
    end=cyc[0]+FRAME
    while cyc[0]<end:
        if cpu.halted: cyc[0]=next_irq
        else:
            pc=cpu.pc
            if START and not patched and pc==SC: mem[sym['current_levelx']]=START[0]; mem[sym['current_levely']]=START[1]; patched=True
            if w.step(pc,fr): started=True
            cyc[0]+=CYC[mem[pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1
    if started: break
assert started, 'игра не стартовала'
keys.clear(); run(10)
print(f'{ROM}: старт {"экран "+str(START) if START else "начало уровня"}; прогрев: доставлено {delivered}, потеряно {lost}')
for seg in ROUTE.split(','):
    k,n=seg.split(':'); n=int(n)
    keys.clear()
    for kk in k.split('+'):
        if kk!='none': keys.append(kk)
    d0,l0=delivered,lost
    # тики считаем по входам в RunScripts; тики со сменой экрана (LoadScreen внутри) — отдельно
    hold_ticks=[0]; hold_slow=[0]
    RS=sym['RunScripts']; LS=sym['LoadScreen']; end=cyc[0]+n*FRAME; tick_frames=[]; tstart=cyc[0]; seen_load=False; idle=0
    while cyc[0]<end:
        pc=cpu.pc
        if pc==LS: seen_load=True
        if pc==RS:
            tick_frames.append(((cyc[0]-tstart)/FRAME, seen_load)); tstart=cyc[0]; seen_load=False
            if HOLD: hold_ticks[0]+=1; hold_slow[0]+=1 if mem[HOLD]>=8 else 0   # темп анимации: сколько тиков в замедленном режиме
            if FIXRAND: ntick[0]+=1; mem[sym['FrameCounter']]=ntick[0]&0xFF; mem[sym['FrameCounter']+1]=0
        if cpu.halted: idle+=next_irq-cyc[0]; cyc[0]=next_irq
        else: cyc[0]+=CYC[mem[cpu.pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1; lost_at[fn(cpu.pc)]+=1
    d1,l1=delivered,lost; dd=d1-d0; dl=l1-l0; idle_pct=idle/(n*FRAME)*100
    norm=[f for f,l in tick_frames[1:] if not l]; loads=[f for f,l in tick_frames[1:] if l]
    avg=sum(norm)/max(len(norm),1)
    print(f'  {k:10s} {n:4d} кадров: потеряно прерываний {dl} ({dl/n*100:.1f} %); обычных тиков {len(norm)}: {avg:.2f} кадра/тик ({50/max(avg,0.01):.1f} тик/с), доля тиков >5 кадров {sum(1 for f in norm if f>5.5)/max(len(norm),1)*100:.0f} %, простой (halt) {idle_pct:.0f} %' + (f'; смен экрана {len(loads)}: {", ".join(f"{f:.0f}" for f in loads)} кадров' if loads else '')
          + (f'; анимация замедлена в {hold_slow[0]/max(hold_ticks[0],1)*100:.0f} % тиков' if HOLD else ''))
    if norm:
        import collections as _c
        h=_c.Counter(min(int(f+0.5),12) for f in norm)
        print('    длительность тиков (кадров: сколько): ' + ' '.join(f'{k}:{h[k]}' for k in sorted(h)))
if lost: print('  потери по функциям:', dict(lost_at.most_common(8)))
