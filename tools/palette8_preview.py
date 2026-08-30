#!/usr/bin/env python3
"""Превью 8-цветных палитр по экранам уровня: palette8_preview.py <уровень> [выход.png]
Правила (согласованы 2026-08-30): чёрный + 6 цветов героя фиксированы на всех экранах
(герой перед квантованием переназначается HREMAP — стабилен в деталях, меч голубой);
врагу экрана фиксируется один опознавательный цвет (EFIX); остальные 1-2 подбираются
k-средними (вес G x2) по тайлам и врагам экрана среди всех 256 цветов Вектора.
Пишет лист-карту экранов и <выход>.txt с палитрами (RGB 0..7) и таблицами 16->8.
"""
import sys,collections,zlib,struct,random,statistics,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).parent/'data'))
from build_edd import SRC, screens_of, tile_pixels, parse_sprite_asm
from level_tools import parse_level
from pletter import depack as pletter_depack
LVL=int(sys.argv[1]) if len(sys.argv)>1 else 1
OUT=sys.argv[2] if len(sys.argv)>2 else f'build/l{LVL}_map8.png'
plt=(SRC/'test.plt').read_bytes(); msx=[]
for i in range(16):
    b0,b1=plt[2*i],plt[2*i+1]; msx.append(((b0>>4)&7,b1&7,b0&7))
msx[0]=(0,0,0)
page={20:'sprite_esqueleto',21:'sprite_orc',22:'sprite_mummy',23:'sprite_troll',24:'sprite_rollingstone',25:'sprite_caballerorenegado',26:'sprite_dalgurak',27:'sprite_golem',28:'sprite_ogro',29:'sprite_minotauro',30:'sprite_demonio'}
EFIX={20:(7,7,7),21:(0,5,0),22:(7,7,7),23:(5,5,5),24:(5,5,5),25:(5,5,5),26:(0,5,0),27:(4,6,7),28:(5,5,5),29:(3,2,1),30:(5,0,1)}
HREMAP={7:9, 11:4, 6:4, 8:4, 5:10, 2:9}   # герой: серый->корич, белый/св.серый/св.синий->голубой, жёлтый->оранж, синий->корич
HFIX=[(0,0,0),(3,2,1),(7,4,1),(7,5,5),(4,6,7),(5,0,1)]
W=(1.0,2.0,0.6)
def d2(a,b): return sum(w*(x-y)**2 for w,x,y in zip(W,a,b))
def snap(c): return tuple(max(0,min(7,round(v))) for v in c)
def to255(c): return tuple(v*255//7 for v in c)
sr5=pletter_depack((SRC/f'tiles_nivel{LVL:02d}.SR5.plet1').read_bytes()); lv=(SRC/f'level{LVL}.map').read_bytes(); info=parse_level(lv); scr=screens_of(lv); w,h=info['w'],info['h']
def kmeans(hist,FIX,k):
    pts=[(msx[c],wt) for c,wt in hist.items() if c!=0]
    cand=[c for c in hist if c not in (0,1)] or [2]
    best=None
    for seed in range(25):
        random.seed(seed); cent=[msx[c] for c in random.sample(cand,min(k,len(cand)))]
        while len(cent)<k: cent.append((7,7,7))
        for it in range(25):
            grp=collections.defaultdict(list)
            for p,wt in pts:
                allc=FIX+cent; j=min(range(len(allc)),key=lambda i:d2(p,allc[i]))
                if j>=len(FIX): grp[j-len(FIX)].append((p,wt))
            cent2=[]
            for i in range(k):
                g=grp.get(i)
                if not g: cent2.append(cent[i]); continue
                sw=sum(wt for _,wt in g); cent2.append(tuple(sum(p[j]*wt for p,wt in g)/sw for j in range(3)))
            cent=cent2
        cent=[snap(c) for c in cent]; allc=FIX+cent
        err=sum(wt*min(d2(p,c) for c in allc) for p,wt in pts)
        if best is None or err<best[0]: best=(err,cent)
    return FIX+best[1]
sheet=[[(0,0,0)]*(w*256+(w-1)*4) for _ in range(h*160+(h-1)*4)]
lines=[]; hero0=parse_sprite_asm(SRC/'sprite_barbaro_1.asm')[0]
for i,s in enumerate(scr):
    sx,sy=i%w,i//w
    img=[[0]*256 for _ in range(160)]
    for k in range(160):
        tx,ty=(k%16)*16,(k//16)*16
        for t,fgm in ((s[k],False),(s[160+k],True)):
            if t==0 and fgm: continue
            px=tile_pixels(sr5,t)
            for y in range(16):
                for x in range(16):
                    v=px[y][x]
                    if v or not fgm: img[ty+y][tx+x]=v
    hist=collections.Counter()
    for row in img:
        for v in row: hist[v]+=1
    FIX=list(HFIX); ens=[]
    for off in (361,367):
        if len(s)>off+3 and s[off+1] and s[off+1] in page:
            t=s[off+1]; ens.append((t,s[off+2]*16,s[off+3]*16))
            c=EFIX.get(t)
            if c and c not in FIX: FIX.append(c)
    for t,x0,y0 in ens:
        f=parse_sprite_asm(SRC/f'{page[t]}{"_inf" if t>=27 else ""}.asm')[0]
        for y in range(32):
            for x in range(24):
                if 0<=y0+y<160 and f[y][x]: img[y0+y][x0+x]=f[y][x]; hist[f[y][x]]+=8
        if t>=27:
            f=parse_sprite_asm(SRC/f'{page[t]}_sup.asm')[0]
            for y in range(32):
                for x in range(24):
                    if 0<=y0-32+y<160 and f[y][x]: img[y0-32+y][x0+x]=f[y][x]; hist[f[y][x]]+=8
    for y in range(32):
        for x in range(24):
            v=hero0[y][x]
            if v: img[112+y][16+x]=HREMAP.get(v,v)
    kfree=8-len(FIX)
    pal=kmeans(hist,FIX,kfree) if kfree>0 else FIX[:8]
    mp=[min(range(8),key=lambda j:d2(msx[c],pal[j])) for c in range(16)]; mp[0]=0
    for c in range(1,16):
        if msx[c] in pal: mp[c]=pal.index(msx[c])
    changed=sum(hist[c] for c in range(16) if pal[mp[c]]!=msx[c])/max(sum(hist.values()),1)*100
    lines.append(f'({sx},{sy}) своб.{kfree} палитра {" ".join(f"{r}{g}{b}" for r,g,b in pal)}  16->8: {" ".join(map(str,mp))}  изм. {changed:4.1f} %')
    ox,oy=sx*260,sy*164
    for y in range(160):
        for x in range(256):
            sheet[oy+y][ox+x]=to255(pal[mp[img[y][x]]])
pathlib.Path(OUT).with_suffix('.txt').write_text('\n'.join(lines)+'\n')
raw=bytearray()
for r in sheet:
    raw.append(0)
    for p in r: raw+=bytes(p)
def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
pathlib.Path(OUT).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',len(sheet[0]),len(sheet),8,2,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw),6))+chunk(b'IEND',b''))
ch=[float(l.split('изм.')[1].split('%')[0]) for l in lines]
print(f'{OUT}: уровень {LVL}, медиана изменённых {statistics.median(ch):.1f} %, макс {max(ch):.1f} %')
