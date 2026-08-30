#!/usr/bin/env python3
"""Покадровый гейт «частичный спрайт»: на каждом кадре (прерывании) снимается VRAM прямоугольника
героя (по SPDATA[0]) и сравнивается с ДВУМЯ эталонами — картинкой прошлого тика и картинкой текущего
(после полного вывода). Кадр, где прямоугольник не совпадает ни с одной, — переходный (стёрто, но не
дорисовано). Считает такие кадры на маршруте.  python3 tests/render/frame_partial.py rom lst [--route=...] [--start=]
"""
import sys, pathlib, hashlib
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]; OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'right:60,up:10,none:30,fire+right:60,up:8,none:40')
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
rv.START=START; sym=rv.load_syms(pathlib.Path(ARGS[1])); keys=[]; cpu=rv.make_cpu(keys)
r=open(ARGS[0],'rb').read(); cpu.mem[0x100:0x100+len(r)]=r; cpu.pc=0x100
rv.start_game(cpu,keys,sym); mem=cpu.mem; SPD=sym['SPDATA']; RS=sym['RunScripts']
def rect_from(vram,x,y,nx,ny):
    out=bytearray()
    for base in (0x0000,0x2000,0x4000,0x6000):
        for cx in range(max(0,x//8-1), min(32,x//8+nx+1)):
            col=base+cx*256
            for yy in range(max(0,y-8), min(160,y+ny*8+8)): out.append(vram[col+223-yy])
    return bytes(out)
frames=0; partial=0; prev_vram=None; snaps=[]
for seg in ROUTE.split(','):
    k,n=seg.split(':'); keys.clear()
    for kk in k.split('+'):
        if kk!='none': keys.append(kk)
    for _ in range(int(n)):
        c=0
        while cpu.pc!=RS and c<400000:
            if cpu.halted:
                cpu.halted=False
                if cpu.ie:
                    cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
                    x,y,nx,ny=mem[SPD+3],mem[SPD+4],mem[SPD+5],mem[SPD+6]
                    vr=bytes(mem[0x8000:0x10000]); snaps.append(((x,y,nx,ny), rect_from(vr,x,y,nx,ny))); frames+=1
            cpu.step(); c+=1
        final=bytes(mem[0x8000:0x10000])      # начало тика: вывод прошлого тика завершён
        for (rect,snap) in snaps:
            ok = snap==rect_from(final,*rect) or (prev_vram is not None and snap==rect_from(prev_vram,*rect))
            if not ok: partial+=1
        snaps=[]; prev_vram=final; cpu.step()
print(f'{ARGS[0]}: кадров {frames}, переходных (герой стёрт/недорисован) {partial} ({partial/max(frames,1)*100:.1f} %)')
