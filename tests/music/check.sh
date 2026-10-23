#!/bin/sh
# Локстеп-сверка плеера Arkos: оригинал (Z80, pasmo + Z80.js) против перевода (i8080, zasm + emu8080).
# Обе сборки играют music-level1.mus/iannafx.mus по $C980/$D980 600 кадров; сравниваются потоки регистров AY.
set -e
cd "$(dirname "$0")"
../../tools/bin/pasmo z80_drv.asm z80_drv.bin z80_drv.sym 2>&1 | grep -v WARNING | grep -v "^$" || true
node z80_run.js | head -1
../../tools/bin/sjasm --8080 -uwy i8080_drv.asm i8080_drv.lst i8080_drv.bin 2>&1 | grep -i "error" || true
python3 - <<'PY'
import sys,json; sys.path.insert(0,'../../tools/vendor')
from emu8080 import I8080
cpu=I8080(); rom=open('i8080_drv.bin','rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom
sp='../../ref/msx2/src/'
for a,f in ((0xC980,'music-level1.mus'),(0xD980,'iannafx.mus')):
    d=open(sp+f,'rb').read(); cpu.mem[a:a+len(d)]=d
frames=[[]]; reg=[None]
def out_h(p,v):
    if p==0x15: reg[0]=v
    elif p==0x14: frames[-1].append([reg[0],v])
    elif p==0xFF: frames.append([])
cpu.out_handler=out_h; cpu.pc=0x100; cpu.run(50_000_000)
b=frames[:-1]; a=json.load(open('z80_stream.json'))
bad=[i for i in range(min(len(a),len(b))) if a[i]!=b[i]]
print('кадров %d/%d, расхождений %d%s' % (len(a),len(b),len(bad),(' — первое в кадре %d'%bad[0]) if bad else ' — ПОТОКИ AY ИДЕНТИЧНЫ'))
sys.exit(1 if bad or len(a)!=len(b) else 0)
PY
# ---- расширенный гейт: 6200 кадров (полный цикл песни) + эффекты канала 1 по таблице (как FX_Play) ----
../../tools/bin/pasmo z80_drv_sfx.asm z80_drv_sfx.bin z80_drv_sfx.sym 2>&1 | grep -v WARNING | grep -v "^$" || true
node z80_run_sfx.js | head -1
../../tools/bin/sjasm --8080 -uwy i8080_drv_sfx.asm i8080_drv_sfx.lst i8080_drv_sfx.bin 2>&1 | grep -i "error" || true
python3 - <<'PY'
import sys,json; sys.path.insert(0,'../../tools/vendor')
from emu8080 import I8080
cpu=I8080(); rom=open('i8080_drv_sfx.bin','rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom
sp='../../ref/msx2/src/'
for a,f in ((0xC980,'music-level1.mus'),(0xD980,'iannafx.mus')):
    d=open(sp+f,'rb').read(); cpu.mem[a:a+len(d)]=d
frames=[[]]; reg=[None]
def out_h(p,v):
    if p==0x15: reg[0]=v
    elif p==0x14: frames[-1].append([reg[0],v])
    elif p==0xFF: frames.append([])
cpu.out_handler=out_h; cpu.pc=0x100; cpu.run(400_000_000)
b=frames[:-1]; a=json.load(open('z80_stream_sfx.json'))
bad=[i for i in range(min(len(a),len(b))) if a[i]!=b[i]]
print('РАСШИРЕННЫЙ ГЕЙТ (эффекты, полный цикл): кадров %d/%d, расхождений %d%s' % (len(a),len(b),len(bad),(' — первое в кадре %d'%bad[0]) if bad else ' — ПОТОКИ AY ИДЕНТИЧНЫ'))
sys.exit(1 if bad or len(a)!=len(b) else 0)
PY
