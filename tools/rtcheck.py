#!/usr/bin/env python3
"""Артефакты реального времени: одна и та же сборка играет один и тот же маршрут дважды — с прерываниями
только на halt (как cmpticks) и с прерываниями по тактам (как на железе) — и поле экрана сравнивается
на КАЖДОМ тике. Логика от момента прерывания не зависит (клавиши и FrameCounter заданы по тикам), поэтому
любое расхождение поля — след того, что прерывание попало в неудачное место (стек в данных пула и т.п.).
Спрайт в пул идёт под EI (isr_spr чинит пару под SP): печатается, сколько раз прерывание попало в блит и по
какому режиму чинилось, а в конце сравнивается весь квазидиск двух прогонов — порча данных кадров видна там,
даже если испорченная строка ещё не рисовалась. --nofix — контроль: починка выключена, расхождения обязаны быть.
  python3 tools/rtcheck.py <rom> <lst> <edd> X,Y [--ticks=120] [--route=fight|pace] [--pos=x,y] [--nofix]"""
import sys, os, pathlib, re, hashlib
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]; A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST=A[:4]; os.environ['IANNA_EDD']=EDD
NOFIX='--nofix' in OPTS; import collections
NT=int(next((o[8:] for o in OPTS if o.startswith('--ticks=')),'120')); ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'fight')
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904
SC={'fight':[['fire','right'],[],['fire','up'],[],['fire','down'],[],['fire','left'],[],['right'],['right'],['left'],['left'],['up'],['down']],
    'pace':[['right']]*6+[['left']]*6}[ROUTE]
def play(rt):
    sys.modules.pop('run_vec',None); import run_vec as rv
    sym=rv.load_syms(pathlib.Path(LST)); keys=[]; cpu=rv.make_cpu(keys)
    rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu, LST)
    mem=cpu.mem; a=sym['random']; rd=sym['randData']; mem[a:a+9]=bytes((0x3A,rd&0xFF,rd>>8,0xC6,0x4D,0x32,rd&0xFF,rd>>8,0xC9))
    pit={'reload':0,'latched':None,'wr':0,'rd':0}; cyc=[0]; bo=cpu.out_handler; bi=cpu.in_handler
    def oh(p,v):
        if p==0x08:
            if v==0: pit['latched']=(0xFFFF-(((cyc[0]-pit['reload'])//2)&0xFFFF))&0xFFFF; pit['rd']=0
            return
        if p==0x0B:
            if pit['wr']==0: pit['wr']=1
            else: pit['wr']=0; pit['reload']=cyc[0]
            return
        bo(p,v)
    def ih(p):
        if p==0x0B:
            v=pit['latched'] if pit['latched'] is not None else (0xFFFF-(((cyc[0]-pit['reload'])//2)&0xFFFF))&0xFFFF
            if pit['rd']==0: pit['rd']=1; return v&0xFF
            pit['rd']=0; pit['latched']=None; return v>>8
        return bi(p)
    cpu.out_handler=oh; cpu.in_handler=ih
    RS=sym['RunScripts']; SCP=sym['SaveCheckpoint']; WT=sym.get('wait_till_read',-1); FC=sym['FrameCounter']; EPP=sym['ENTITY_PLAYER_POINTER']
    st=tuple(int(v) for v in ST.split(',')); pos=next((tuple(int(v) for v in o[6:].split(',')) for o in OPTS if o.startswith('--pos=')),None)
    patched=False; ticks=0; out=[]; e0=None; wait=False; nxt=FRAME; steps=0; saved=[]
    SW=sym.get('isrb_sw',-1); FIX=sym.get('isrb_fix',-1); GO=sym.get('isrb_go',-1); RET=sym.get('isr_ret',-1)
    lab=sorted((v,k) for k,v in sym.items()); import bisect
    def fn(a): i=bisect.bisect_right(lab,(a,'~'))-1; return lab[i][1] if i>=0 else '?'
    fixes=collections.Counter()
    while ticks<NT+40:
        pc=cpu.pc
        if pc==SCP and not patched:
            mem[sym['current_levelx']]=st[0]; mem[sym['current_levely']]=st[1]; patched=True
            if pos: mem[sym['initial_coordx']]=pos[0]; mem[sym['initial_coordy']]=pos[1]
        elif pc==WT and not wait: wait=True; saved=list(keys); keys[:]=['fire']
        elif pc==RS:
            if wait: wait=False; keys[:]=saved
            ticks+=1; mem[FC]=ticks&0xFF; mem[FC+1]=0
            if e0 is None: e0=mem[EPP+4]
            elif mem[EPP+4]<e0: mem[EPP+4]=e0
            if ticks>40:
                keys[:]=SC[(ticks-40)%len(SC)]
                fld=b''.join(bytes(mem[b+c*256+64:b+c*256+224]) for b in (0x8000,0xA000,0xC000,0xE000) for c in range(32))
                out.append(fld)
        if pc==SW:
            tgt=mem[SW+1]|mem[SW+2]<<8; r=mem[RET+1]|mem[RET+2]<<8
            fixes[(fn(r), 'чинится' if tgt==FIX else 'без починки')]+=1
            if NOFIX: mem[SW+1]=GO&0xFF; mem[SW+2]=GO>>8
        irq=False
        if cpu.halted:
            cyc[0]=nxt if rt else cyc[0]; irq=True
        else:
            cyc[0]+=CYC[mem[pc]]; cpu.step(); steps+=1
            if rt: irq = cyc[0]>=nxt
            elif steps>400000: irq=True
        if irq:
            steps=0
            if rt: nxt+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38
            elif cpu.halted and not rt: cpu.halted=False
    if rt: print('  прерывания в спрайте (адрес возврата у метки):', sorted(fixes.items(), key=lambda kv:-kv[1]))
    return out, bytes(cpu.kvaz)
(a,ka)=play(False); (b,kb)=play(True); bad=[]
kd=[i for i in range(len(ka)) if ka[i]!=kb[i]]
runs=[]
for i in kd:
    if runs and i-runs[-1][1]<=8: runs[-1][1]=i
    else: runs.append([i,i])
print(f'  квазидиск: различий {len(kd)} Б' + (': ' + ', '.join(f'стр.{x>>16} ${x&0xFFFF:04X}-${y&0xFFFF:04X}' for x,y in runs[:12]) if kd else ''))
for t,(x,y) in enumerate(zip(a,b)):
    if x!=y:
        d=[i for i in range(len(x)) if x[i]!=y[i]]
        cells=sorted({((i//160)%32, 159-(i%160)) for i in d})   # (колонка 8px, строка экрана)
        bad.append((t+41,len(d),cells[0],cells[-1]))
print(f'{ROM} {ST} {ROUTE}: тиков {len(a)}; поле расходится на {len(bad)} тиках' + (': '+'; '.join(f'тик {t}: {n} Б, колонки/строки {c0}..{c1}' for t,n,c0,c1 in bad[:8]) if bad else ''))
