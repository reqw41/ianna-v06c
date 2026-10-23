#!/usr/bin/env python3
"""Минимальный, но корректный эмулятор Intel 8080 для отладки ROM Вектор-06Ц.
Выполняет ROM (загружается по $100), пишет видеопамять $8000..$FFFF.
OUT-порты логируются; IN порт $02 (клавиатура)=$ff (нет нажатий), иначе 0; in_handler переопределяет.
Останов: по HALT, или по budget инструкций, или по PC вне диапазона.
"""
import sys

class I8080:
    def __init__(self):
        self.mem = bytearray(0x10000)
        self.a=0; self.b=0; self.c=0; self.d=0; self.e=0; self.h=0; self.l=0
        self.sp=0; self.pc=0
        self.fz=0; self.fs=0; self.fp=0; self.fc=0; self.fac=0
        self.halted=False
        self.ie=False     # разрешение прерываний (DI/EI) — для доставки RST7 на HALT
        self.out_log=[]   # (port, value)
        self.icount=0

    # --- helpers ---
    def _hl(self): return (self.h<<8)|self.l
    def _bc(self): return (self.b<<8)|self.c
    def _de(self): return (self.d<<8)|self.e
    def _set_hl(self,v): self.h=(v>>8)&0xff; self.l=v&0xff
    def _set_bc(self,v): self.b=(v>>8)&0xff; self.c=v&0xff
    def _set_de(self,v): self.d=(v>>8)&0xff; self.e=v&0xff
    def rb(self,a): return self.mem[a&0xffff]
    def wb(self,a,v): self.mem[a&0xffff]=v&0xff
    def r16(self,a): return self.rb(a)|(self.rb(a+1)<<8)
    def fetch(self):
        op=self.mem[self.pc]; self.pc=(self.pc+1)&0xffff; return op
    def fetch16(self):
        lo=self.fetch(); hi=self.fetch(); return lo|(hi<<8)

    def parity(self,v):
        v&=0xff; p=1
        while v: p^=1; v&=v-1
        return p
    def set_szp(self,v):
        v&=0xff
        self.fz=1 if v==0 else 0
        self.fs=1 if v&0x80 else 0
        self.fp=self.parity(v)
    def add(self,v,carry=0):
        r=self.a+v+carry
        self.fc=1 if r>0xff else 0
        self.fac=1 if ((self.a&0xf)+(v&0xf)+carry)>0xf else 0
        self.a=r&0xff; self.set_szp(self.a)
    def sub(self,v,borrow=0):
        r=self.a-v-borrow
        self.fc=1 if r<0 else 0
        self.fac=1 if ((self.a&0xf)-(v&0xf)-borrow)<0 else 0
        self.a=r&0xff; self.set_szp(self.a)
    def cmp(self,v):
        r=self.a-v
        self.fc=1 if r<0 else 0
        self.fac=1 if ((self.a&0xf)-(v&0xf))<0 else 0
        self.set_szp(r&0xff)
    def ana(self,v):
        self.fac=1 if ((self.a|v)&0x08) else 0
        self.a&=v; self.fc=0; self.set_szp(self.a)
    def ora(self,v):
        self.a|=v; self.fc=0; self.fac=0; self.set_szp(self.a)
    def xra(self,v):
        self.a^=v; self.fc=0; self.fac=0; self.set_szp(self.a)
    def push(self,v):
        self.sp=(self.sp-1)&0xffff; self.wb(self.sp,(v>>8)&0xff)
        self.sp=(self.sp-1)&0xffff; self.wb(self.sp,v&0xff)
    def pop(self):
        lo=self.rb(self.sp); self.sp=(self.sp+1)&0xffff
        hi=self.rb(self.sp); self.sp=(self.sp+1)&0xffff
        return lo|(hi<<8)
    def get_psw(self):
        f=0x02
        if self.fc: f|=0x01
        if self.fp: f|=0x04
        if self.fac: f|=0x10
        if self.fz: f|=0x40
        if self.fs: f|=0x80
        return (self.a<<8)|f
    def set_psw(self,v):
        self.a=(v>>8)&0xff; f=v&0xff
        self.fc=f&1; self.fp=(f>>2)&1; self.fac=(f>>4)&1; self.fz=(f>>6)&1; self.fs=(f>>7)&1

    def reg(self,i):  # 0..7 = B C D E H L M A
        return [self.b,self.c,self.d,self.e,self.h,self.l,self.rb(self._hl()),self.a][i]
    def setreg(self,i,v):
        v&=0xff
        if i==0:self.b=v
        elif i==1:self.c=v
        elif i==2:self.d=v
        elif i==3:self.e=v
        elif i==4:self.h=v
        elif i==5:self.l=v
        elif i==6:self.wb(self._hl(),v)
        elif i==7:self.a=v

    def step(self):
        op=self.fetch(); self.icount+=1
        # MOV r,r (0x40-0x7F except 0x76 HALT)
        if 0x40<=op<=0x7f:
            if op==0x76: self.halted=True; return
            dst=(op>>3)&7; src=op&7; self.setreg(dst,self.reg(src)); return
        # MVI r,d8 (0x06,0x0E,...0x3E)
        if op&0xc7==0x06:
            dst=(op>>3)&7; self.setreg(dst,self.fetch()); return
        # arithmetic A with reg (0x80-0xBF)
        if 0x80<=op<=0xbf:
            grp=(op>>3)&7; v=self.reg(op&7)
            [self.add,lambda x:self.add(x,self.fc),self.sub,lambda x:self.sub(x,self.fc),
             self.ana,self.xra,self.ora,self.cmp][grp](v); return
        # INR r (0x04,0x0C,..0x3C)
        if op&0xc7==0x04:
            i=(op>>3)&7; v=(self.reg(i)+1)&0xff
            self.fac=1 if (v&0xf)==0 else 0; self.setreg(i,v); self.set_szp(v); return
        # DCR r (0x05,0x0D,..0x3D)
        if op&0xc7==0x05:
            i=(op>>3)&7; old=self.reg(i); v=(old-1)&0xff
            self.fac=0 if (old&0xf)==0 else 1; self.setreg(i,v); self.set_szp(v); return
        # INX/DCX/DAD/LXI by pair
        if op==0x00: return                      # NOP
        if op==0x01: self._set_bc(self.fetch16()); return
        if op==0x11: self._set_de(self.fetch16()); return
        if op==0x21: self._set_hl(self.fetch16()); return
        if op==0x31: self.sp=self.fetch16(); return
        if op==0x03: self._set_bc((self._bc()+1)&0xffff); return
        if op==0x13: self._set_de((self._de()+1)&0xffff); return
        if op==0x23: self._set_hl((self._hl()+1)&0xffff); return
        if op==0x33: self.sp=(self.sp+1)&0xffff; return
        if op==0x0b: self._set_bc((self._bc()-1)&0xffff); return
        if op==0x1b: self._set_de((self._de()-1)&0xffff); return
        if op==0x2b: self._set_hl((self._hl()-1)&0xffff); return
        if op==0x3b: self.sp=(self.sp-1)&0xffff; return
        if op in (0x09,0x19,0x29,0x39):
            src={0x09:self._bc(),0x19:self._de(),0x29:self._hl(),0x39:self.sp}[op]
            r=self._hl()+src; self.fc=1 if r>0xffff else 0; self._set_hl(r&0xffff); return
        # STAX/LDAX
        if op==0x02: self.wb(self._bc(),self.a); return
        if op==0x12: self.wb(self._de(),self.a); return
        if op==0x0a: self.a=self.rb(self._bc()); return
        if op==0x1a: self.a=self.rb(self._de()); return
        # STA/LDA/SHLD/LHLD
        if op==0x32: self.wb(self.fetch16(),self.a); return
        if op==0x3a: self.a=self.rb(self.fetch16()); return
        if op==0x22: a=self.fetch16(); self.wb(a,self.l); self.wb(a+1,self.h); return
        if op==0x2a: a=self.fetch16(); self.l=self.rb(a); self.h=self.rb(a+1); return
        # rotates
        if op==0x07: self.fc=(self.a>>7)&1; self.a=((self.a<<1)|self.fc)&0xff; return  # RLC
        if op==0x0f: self.fc=self.a&1; self.a=((self.a>>1)|(self.fc<<7))&0xff; return  # RRC
        if op==0x17: nc=(self.a>>7)&1; self.a=((self.a<<1)|self.fc)&0xff; self.fc=nc; return  # RAL
        if op==0x1f: nc=self.a&1; self.a=((self.a>>1)|(self.fc<<7))&0xff; self.fc=nc; return    # RAR
        if op==0x27:                              # DAA (BCD-коррекция: очки и т.п.)
            a=self.a; add=0; c=self.fc
            if (a&0x0f)>9 or self.fac: add|=0x06
            if (a>>4)>9 or c or ((a>>4)>=9 and (a&0x0f)>9): add|=0x60; c=1
            self.fac=1 if (a&0x0f)+ (add&0x0f)>0x0f else 0
            self.a=(a+add)&0xff; self.fc=c; self.set_szp(self.a); return
        if op==0x2f: self.a^=0xff; return        # CMA
        if op==0x37: self.fc=1; return           # STC
        if op==0x3f: self.fc^=1; return          # CMC
        # immediate ALU
        if op==0xc6: self.add(self.fetch()); return
        if op==0xce: self.add(self.fetch(),self.fc); return
        if op==0xd6: self.sub(self.fetch()); return
        if op==0xde: self.sub(self.fetch(),self.fc); return
        if op==0xe6: self.ana(self.fetch()); return
        if op==0xee: self.xra(self.fetch()); return
        if op==0xf6: self.ora(self.fetch()); return
        if op==0xfe: self.cmp(self.fetch()); return
        # jumps
        if op==0xc3: self.pc=self.fetch16(); return
        cond={0xc2:not self.fz,0xca:self.fz,0xd2:not self.fc,0xda:self.fc,
              0xe2:not self.fp,0xea:self.fp,0xf2:not self.fs,0xfa:self.fs}
        if op in cond:
            t=self.fetch16()
            if cond[op]: self.pc=t
            return
        # calls
        if op==0xcd: t=self.fetch16(); self.push(self.pc); self.pc=t; return
        ccond={0xc4:not self.fz,0xcc:self.fz,0xd4:not self.fc,0xdc:self.fc,
               0xe4:not self.fp,0xec:self.fp,0xf4:not self.fs,0xfc:self.fs}
        if op in ccond:
            t=self.fetch16()
            if ccond[op]: self.push(self.pc); self.pc=t
            return
        # returns
        if op==0xc9: self.pc=self.pop(); return
        rcond={0xc0:not self.fz,0xc8:self.fz,0xd0:not self.fc,0xd8:self.fc,
               0xe0:not self.fp,0xe8:self.fp,0xf0:not self.fs,0xf8:self.fs}
        if op in rcond:
            if rcond[op]: self.pc=self.pop()
            return
        # push/pop
        if op==0xc5: self.push(self._bc()); return
        if op==0xd5: self.push(self._de()); return
        if op==0xe5: self.push(self._hl()); return
        if op==0xf5: self.push(self.get_psw()); return
        if op==0xc1: self._set_bc(self.pop()); return
        if op==0xd1: self._set_de(self.pop()); return
        if op==0xe1: self._set_hl(self.pop()); return
        if op==0xf1: self.set_psw(self.pop()); return
        # exchange/stack ops
        if op==0xeb: self.h,self.d=self.d,self.h; self.l,self.e=self.e,self.l; return  # XCHG
        if op==0xe3: # XTHL
            t=self.r16(self.sp); self.wb(self.sp,self.l); self.wb(self.sp+1,self.h); self._set_hl(t); return
        if op==0xf9: self.sp=self._hl(); return   # SPHL
        if op==0xe9: self.pc=self._hl(); return   # PCHL
        # I/O & control
        if op==0xd3:                                                     # OUT
            p=self.fetch(); self.out_log.append((p,self.a))
            if getattr(self,'out_handler',None): self.out_handler(p,self.a)
            return
        if op==0xdb:                                                     # IN
            p=self.fetch()
            if getattr(self,'in_handler',None):
                self.a=self.in_handler(p)
            elif p==0x02:
                self.a=0xff   # порт клавиатуры: $ff = НЕТ нажатий (после cpl -> $00); иначе фантомные клавиши
            else:
                self.a=0
            return
        if op==0xf3: self.ie=False; return  # DI
        if op==0xfb: self.ie=True;  return  # EI
        if op==0x76: self.halted=True; return  # HALT (already handled above)
        if op in (0xc7,0xcf,0xd7,0xdf,0xe7,0xef,0xf7,0xff): # RST
            n=((op>>3)&7)*8; self.push(self.pc); self.pc=n; return
        raise RuntimeError(f"неизвестный опкод {op:#04x} на pc={self.pc-1:#06x}")

    def run(self,max_i=5_000_000):
        while not self.halted and self.icount<max_i:
            self.step()

    def run_frames(self,frames,max_per=3_000_000):
        # один «кадр» = выполнить до HALT, затем доставить прерывание RST7 (если IE),
        # ISR (EI;RET) вернётся в mloop и тело кадра отработает до следующего HALT.
        for _ in range(frames):
            c=0
            while not self.halted and c<max_per:
                self.step(); c+=1
            if not self.halted: break
            self.halted=False
            if self.ie:
                self.ie=False
                self.push(self.pc)
                self.pc=0x38

def main():
    rom=sys.argv[1]
    data=open(rom,'rb').read()
    cpu=I8080()
    cpu.mem[0x100:0x100+len(data)]=data
    cpu.pc=0x100
    frames=int(sys.argv[2]) if len(sys.argv)>2 else 0
    if frames>0:
        cpu.run_frames(frames); print(f"прогнано кадров: {frames}")
    else:
        cpu.run()
    # отчёт
    print(f"инструкций выполнено: {cpu.icount}, halted={cpu.halted}, pc={cpu.pc:#06x}")
    # test_result ($7000) — конвенция логических автотестов (TEST_PASS=$a5/TEST_FAIL=$5a)
    print(f"test_result($7000): {cpu.mem[0x7000]:#04x}")
    # ненулевые байты видеопамяти по плоскостям
    for pi,base in enumerate((0x8000,0xA000,0xC000,0xE000)):
        nz=sum(1 for b in cpu.mem[base:base+0x2000] if b)
        print(f"плоскость {pi} ({base:#06x}): ненулевых байт = {nz}")
    # OUT-лог (палитра/звук)
    print("OUT-обращения (порт:значение), первые 60:")
    print(" ".join(f"{p:02x}:{v:02x}" for p,v in cpu.out_log[:60]))
    # сохранить дамп видеопамяти
    open(rom+'.vram','wb').write(cpu.mem[0x8000:0x10000])
    print(f"видеопамять сохранена в {rom}.vram")

if __name__=='__main__': main()
