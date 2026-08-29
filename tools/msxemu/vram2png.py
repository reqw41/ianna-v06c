#!/usr/bin/env python3
"""Дамп VRAM MSX2 (SCREEN 5) -> PNG. Использование: vram2png.py vram.bin out.png [page=0] [pal.plt]"""
import sys
from PIL import Image
vram=open(sys.argv[1],'rb').read(); out=sys.argv[2]
page=int(sys.argv[3]) if len(sys.argv)>3 else 0
palf=sys.argv[4] if len(sys.argv)>4 else '/Users/boris/projects/ianna-v06c/ref/msx2/src/test.plt'
p=open(palf,'rb').read()[:32]
pal=[]
for i in range(16):
    b0,b1=p[2*i],p[2*i+1]; r=(b0>>4)&7; b=b0&7; g=b1&7
    pal.append((r*255//7,g*255//7,b*255//7))
W,H=256,212; base=page*0x8000
img=Image.new('RGB',(W,H))
px=img.load()
for y in range(H):
    for x in range(0,W,2):
        v=vram[base+y*128+x//2]
        px[x,y]=pal[v>>4]; px[x+1,y]=pal[v&15]
img=img.resize((W*2,H*2),Image.NEAREST); img.save(out); print('ok',out)
