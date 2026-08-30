#!/usr/bin/env python3
"""Дифференциальный тест цепочки пересечений спрайтов: две сборки (ROM+LST) получают одинаковое
случайное состояние (SPDATA, simulatedsprite, пустой список грязных прямоугольников) и вызов
AnimStile_CheckSprites(B,C,D,E); сравниваются SPDATA (флаги перерисовки), tiles_dirty, ndirtyrects,
simulatedsprite. Плюс check_sprite_overlap(IX,IY) на случайных парах — сравнение CY.
  python3 tests/render/overlap_fuzz.py romA lstA romB lstB [N=400]
"""
import sys, pathlib, random
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]
N=int(ARGS[4]) if len(ARGS)>4 else 400
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
def boot(rom,lst):
    sym=rv.load_syms(pathlib.Path(lst)); keys=[]; cpu=rv.make_cpu(keys)
    r=open(rom,'rb').read(); cpu.mem[0x100:0x100+len(r)]=r; cpu.pc=0x100
    rv.start_game(cpu, keys, sym)     # игра инициализирована (карта, таблицы)
    return cpu, sym
def call(cpu, sym, addr, regs, maxsteps=2_000_000):
    cpu.ie=False; cpu.halted=False
    for k,v in regs.items(): setattr(cpu,k,v)
    cpu.sp=0x7B00; cpu.push(0x0000); cpu.pc=addr; n=0
    while cpu.pc!=0 and n<maxsteps: cpu.step(); n+=1
    assert cpu.pc==0, 'не вернулась'
A=boot(ARGS[0],ARGS[1]); B=boot(ARGS[2],ARGS[3])
rnd=random.Random(1); bad=0
def rand_state():
    spd=bytearray(128)
    for i in range(16):
        if rnd.random()<0.6:
            spd[i*8]=0x80; spd[i*8+1]=rnd.randrange(1,256)
            spd[i*8+2]=rnd.randrange(0,16); spd[i*8+3]=rnd.randrange(0,32)*8; spd[i*8+4]=rnd.randrange(0,160)
            spd[i*8+5]=rnd.randrange(1,5); spd[i*8+6]=rnd.randrange(1,5); spd[i*8+7]=1 if rnd.random()<0.3 else 0
    sim=bytes(rnd.randrange(256) for _ in range(8))
    return spd, sim
for case in range(N):
    spd,sim=rand_state(); b,c,d,e=rnd.randrange(0,16),rnd.randrange(0,10),rnd.randrange(1,5),rnd.randrange(1,5)
    outs=[]
    for cpu,sym in (A,B):
        m=cpu.mem; m[sym['SPDATA']:sym['SPDATA']+128]=spd; m[sym['simulatedsprite']:sym['simulatedsprite']+8]=sim; m[sym['ndirtyrects']]=0
        m[sym['tiles_dirty']:sym['tiles_dirty']+192]=bytes(192)
        call(cpu, sym, sym['AnimStile_CheckSprites'], {'b':b,'c':c,'d':d,'e':e})
        nd=m[sym['ndirtyrects']]
        outs.append((bytes(m[sym['SPDATA']:sym['SPDATA']+128]), nd, bytes(m[sym['tiles_dirty']:sym['tiles_dirty']+4*nd]), bytes(m[sym['simulatedsprite']:sym['simulatedsprite']+8])))
    if outs[0]!=outs[1]:
        bad+=1
        if bad<=3: print('РАСХОЖДЕНИЕ AnimStile_CheckSprites, случай',case,'B,C,D,E=',(b,c,d,e), 'ndirty',outs[0][1],outs[1][1], 'флаги A',[outs[0][0][i*8+7] for i in range(16)],'B',[outs[1][0][i*8+7] for i in range(16)])
# check_sprite_overlap на парах
bad2=0
for case in range(N):
    s1=bytes([0,0,0,rnd.randrange(0,256),rnd.randrange(0,256),rnd.randrange(0,5),rnd.randrange(0,5),0]); s2=bytes([0,0,0,rnd.randrange(0,256),rnd.randrange(0,256),rnd.randrange(0,5),rnd.randrange(0,5),0])
    res=[]
    for cpu,sym in (A,B):
        m=cpu.mem; m[0x7000:0x7008]=s1; m[0x7010:0x7018]=s2
        m[sym['z_ix']]=0x00; m[sym['z_ix']+1]=0x70; m[sym['z_iy']]=0x10; m[sym['z_iy']+1]=0x70
        call(cpu, sym, sym['check_sprite_overlap'], {}); res.append(cpu.fc)
    if res[0]!=res[1]:
        bad2+=1
        if bad2<=3: print('РАСХОЖДЕНИЕ check_sprite_overlap:', s1[3:7], s2[3:7], res)
print(f'AnimStile_CheckSprites: {N} случаев, расхождений {bad}; check_sprite_overlap: {N} пар, расхождений {bad2}', '— ИДЕНТИЧНО' if not (bad or bad2) else '')
sys.exit(1 if bad or bad2 else 0)
