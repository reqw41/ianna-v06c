#!/usr/bin/env python3
"""Гейт рендера «по тикам»: две сборки (ROM+LST) гонятся по одному маршруту (клавиши меняются по
номеру ТИКА, не кадра), в начале каждого тика (вход в RunScripts) сверяется VRAM игрового поля
(строки 0..159, 4 плоскости). Логика игры одинакова, значит различие = разный вывод.
  python3 tests/render/tick_oracle.py romA lstA romB lstB [--start=3,1] [--route=...] [--fixrand]
"""
import sys, pathlib, hashlib
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]; OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'none:20,right:40,fire+right:40,left:30,none:10')
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FIXRAND='--fixrand' in OPTS
EDDS=[next((o[7:] for o in OPTS if o.startswith('--eddA=')),None), next((o[7:] for o in OPTS if o.startswith('--eddB=')),None)]   # свой EDD для каждой сборки (формат данных мог измениться)   # FrameCounter := номер тика перед RunScripts: генератор случайных чисел (ld a,r -> FrameCounter) не зависит от скорости сборки
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
def field(mem):
    h=hashlib.md5()
    for base in (0x8000,0xA000,0xC000,0xE000):
        for x in range(32): h.update(bytes(mem[base+x*256+64:base+x*256+224]))   # L 64..223 = y 159..0
    return h.hexdigest()
def run(rom,lst,edd=None):
    rv.START=START; rv._start_done[0]=False
    sym=rv.load_syms(pathlib.Path(lst)); keys=[]; cpu=rv.make_cpu(keys)
    if edd: cpu.load_edd(pathlib.Path(edd))
    r=open(rom,'rb').read(); cpu.mem[0x100:0x100+len(r)]=r; cpu.pc=0x100
    rv.start_game(cpu, keys, sym)
    RS=sym['RunScripts']; out=[]
    for seg in ROUTE.split(','):
        k,n=seg.split(':'); keys.clear()
        for kk in k.split('+'):
            if kk!='none': keys.append(kk)
        for _ in range(int(n)):
            c=0
            while cpu.pc!=RS and c<400000:
                if cpu.halted:
                    cpu.halted=False
                    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
                cpu.step(); c+=1
            if FIXRAND: cpu.mem[sym['FrameCounter']]=len(out)&0xFF; cpu.mem[sym['FrameCounter']+1]=0
            st=bytes(cpu.mem[sym['SPDATA']:sym['SPDATA']+128])+bytes(cpu.mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])+bytes([cpu.mem[sym['ndirtyrects']]])+bytes(cpu.mem[sym['tiles_dirty']:sym['tiles_dirty']+4*cpu.mem[sym['ndirtyrects']]])
            out.append((field(cpu.mem), bytes(cpu.mem[0x8000:0x10000]), list(cpu.mem[sym['vec_palette']:sym['vec_palette']+16], ), hashlib.md5(st).hexdigest())); cpu.step()
    return out
a=run(ARGS[0],ARGS[1],EDDS[0]); b=run(ARGS[2],ARGS[3],EDDS[1])
bad=[i for i,(x,y) in enumerate(zip(a,b)) if x[0]!=y[0]]
badst=[i for i,(x,y) in enumerate(zip(a,b)) if x[3]!=y[3]]
print(f'состояние (спрайты/сущности/грязные): различий {len(badst)}' + (f' — первый в тике {badst[0]}' if badst else ' — ИДЕНТИЧНО'))
print(f'тиков {len(a)}/{len(b)}, различий {len(bad)}' + (f' — первый в тике {bad[0]}' if bad else ' — ВЫВОД ИДЕНТИЧЕН ПО ТИКАМ'))
if bad:
    i=bad[0]; rv.render(a[i][1],a[i][2],'build/tick_oracle_A.png'); rv.render(b[i][1],b[i][2],'build/tick_oracle_B.png')
    from PIL import Image
    ia=Image.open('build/tick_oracle_A.png').convert('RGB'); ib=Image.open('build/tick_oracle_B.png').convert('RGB')
    pa=ia.load(); pb=ib.load(); xs=[];ys=[]
    for y in range(ia.height):
        for x in range(ia.width):
            if pa[x,y]!=pb[x,y]: xs.append(x); ys.append(y)
    print(f'   тик {i}: отличающихся пикселей {len(xs)}' + (f', область x {min(xs)//2}..{max(xs)//2}, y {min(ys)//2}..{max(ys)//2} (в координатах экрана)' if xs else ' (цвета совпадают — различия в невидимых битах плоскостей)'))
    va=a[i][1]; vb=b[i][1]; dif=[]
    for pl,base in enumerate((0,0x2000,0x4000,0x6000)):
        for x in range(32):
            for L in range(64,224):
                if va[base+x*256+L]!=vb[base+x*256+L]: dif.append((pl,x,223-L,va[base+x*256+L],vb[base+x*256+L]))
    print(f'   байтов поля отличается: {len(dif)}; первые: {dif[:12]}')
    out=Image.new('RGB',(ia.width*2+8,ia.height)); out.paste(ia,(0,0)); out.paste(ib,(ia.width+8,0)); out.save('build/tick_oracle_AB.png')
sys.exit(1 if bad else 0)
