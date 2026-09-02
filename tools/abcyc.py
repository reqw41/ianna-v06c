#!/usr/bin/env python3
"""A/B-замер тактов на детерминированном стенде cmpbuild: N игровых тиков,
одинаковая траектория у любых сборок (FrameCounter подменяется). Печатает
всего тактов, такты в хелперах z_*, хэши VRAM/ENTITY_DATA.
  python3 tools/abcyc.py <rom> <lst> <edd> X,Y <тиков>"""
import sys, os, re, bisect, pathlib, hashlib, collections
ROM=sys.argv[1]; LST=sys.argv[2]; EDD=sys.argv[3]; ST=sys.argv[4]; N=int(sys.argv[5])
os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
rv.STEP_BUDGET=400000
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step; mem=cpu.mem
tot=0; cnt=collections.Counter()
while ticks<N:
    while not cpu.halted:
        pc=cpu.pc; w=CYC[mem[pc]]; tot+=w; cnt[fn(pc)]+=w
        if pc==RS: ticks+=1; mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
z=sum(v for k,v in cnt.items() if k.startswith('z_'))
vram=bytes(mem[0x8000:0x10000]); ent=bytes(mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
print(f'{N} тиков: всего {tot} тактов, на тик {tot/N:.0f}; z_* {z} ({z/tot*100:.2f}%); VRAM {hashlib.md5(vram).hexdigest()[:8]} ENT {hashlib.md5(ent).hexdigest()[:8]}')
