# Гейт по всем мелодиям: Z80-оригинал против нативного i8080-плеера, 6200 кадров + эффекты (как FX_Play).
import sys, os, json, subprocess, glob
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../tools/vendor'))
from emu8080 import I8080
sp='../../ref/msx2/src/'
songs=sorted(os.path.basename(f) for f in glob.glob(sp+'music-*.mus'))
total_bad=0
for song in songs:
    subprocess.run(['node','z80_run_sfx.js'],env={**os.environ,'SONG':song},check=True,capture_output=True)
    a=json.load(open('z80_stream_sfx.json'))
    cpu=I8080(); rom=open('i8080_drv_sfx.bin','rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom
    for addr,f in ((0xC980,song),(0xD980,'iannafx.mus')):
        d=open(sp+f,'rb').read(); cpu.mem[addr:addr+len(d)]=d
    frames=[[]]; reg=[None]
    def out_h(p,v):
        if p==0x15: reg[0]=v
        elif p==0x14: frames[-1].append([reg[0],v])
        elif p==0xFF: frames.append([])
    cpu.out_handler=out_h; cpu.pc=0x100; cpu.run(400_000_000)
    b=frames[:-1]
    bad=[i for i in range(min(len(a),len(b))) if a[i]!=b[i]]
    total_bad+=len(bad)+abs(len(a)-len(b))
    print(f'{song:22s} кадров {len(a)}/{len(b)}, расхождений {len(bad)}' + (f' — первое в кадре {bad[0]}' if bad else ' — ИДЕНТИЧНО'), flush=True)
print('ИТОГ:', 'ВСЕ МЕЛОДИИ ИДЕНТИЧНЫ' if total_bad==0 else f'расхождения: {total_bad}')
sys.exit(1 if total_bad else 0)
