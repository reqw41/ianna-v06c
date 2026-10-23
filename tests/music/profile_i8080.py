import os
# Профиль переведённого плеера Arkos на i8080 (emu8080 + таблица тактов): такты/кадр по функциям.
import sys, re, bisect, collections, json
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../tools/vendor'))
from emu8080 import I8080
src=open('../../tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
syms={}
for line in open('i8080_drv.lst',encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
cpu=I8080(); rom=open('i8080_drv.bin','rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom
sp='../../ref/msx2/src/'
for a,f in ((0xC980,'music-level1.mus'),(0xD980,'iannafx.mus')):
    d=open(sp+f,'rb').read(); cpu.mem[a:a+len(d)]=d
frames=[0]; cnt=collections.Counter(); calls=collections.Counter()
def out_h(p,v):
    if p==0xFF: frames.append(0)
cpu.out_handler=out_h; cpu.pc=0x100; mem=cpu.mem
n=0
while not cpu.halted and n<20_000_000:
    pc=cpu.pc; w=CYC[mem[pc]]; f=fn(pc); cnt[f]+=w; frames[-1]+=w
    if mem[pc]==0xCD: calls[fn(mem[pc+1]|(mem[pc+2]<<8))]+=1
    cpu.step(); n+=1
fr=frames[1:-1] if len(frames)>2 else frames
tot=sum(cnt.values()); nf=len(fr)
print(f'кадров {nf}, тактов/кадр: среднее {sum(fr)/nf:.0f}, мин {min(fr)}, макс {max(fr)}')
h=sum(v for k,v in cnt.items() if k.startswith('z_'))
print(f'хелперы z_*: {h/tot*100:.1f}%')
print('топ по функциям (такты/кадр, вызовов/кадр):')
for k,v in cnt.most_common(28): print(f'  {v/nf:7.0f}  {k:32s} {calls[k]/nf:6.1f}')
