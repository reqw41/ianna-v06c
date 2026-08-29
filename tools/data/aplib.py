"""Декодер aPLib (совместим с depack.asm игры и с apultra)."""
def depack(src, pos=0):
    out=bytearray(); tag=0; bits=0
    def getbit():
        nonlocal tag,bits,pos
        if bits==0:
            tag=src[pos]; pos+=1; bits=8
        bits-=1; b=(tag>>7)&1; tag=(tag<<1)&0xff; return b
    def getgamma():
        v=1
        while True:
            v=(v<<1)|getbit()
            if not getbit(): return v
    out.append(src[pos]); pos+=1
    lwm=0; r0=0
    while pos<len(src):
        if not getbit():
            out.append(src[pos]); pos+=1; lwm=0; continue
        if not getbit():
            g=getgamma()-2
            if lwm==0 and g==0:
                ln=getgamma()
                for _ in range(ln): out.append(out[-r0])
            else:
                if lwm==0: g-=1
                r0=(g<<8)+src[pos]; pos+=1
                ln=getgamma()
                if r0>=32000: ln+=1
                if r0>=1280: ln+=1
                if r0<128: ln+=2
                for _ in range(ln): out.append(out[-r0])
            lwm=1; continue
        if not getbit():
            b=src[pos]; pos+=1
            if b==0: return bytes(out), pos
            r0=b>>1; ln=2+(b&1)
            for _ in range(ln): out.append(out[-r0])
            lwm=1; continue
        r=(getbit()<<3)|(getbit()<<2)|(getbit()<<1)|getbit()
        out.append(0 if r==0 else out[-r]); lwm=0
    return bytes(out), pos
