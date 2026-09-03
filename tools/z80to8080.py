#!/usr/bin/env python3
"""
z80to8080.py — трансляция исходников Ianna (pasmo, Z80) в подмножество i8080
(в Z80-мнемониках для zasm --8080). Всё, что i8080 умеет сам, проходит как есть;
Z80-only конструкции заменяются последовательностями с теми же эффектами.

Контракт эмуляции IX/IY: индексные регистры живут в ячейках z_ix/z_iy;
хелперы (см. src/vec/z80rt.asm) берегут HL, BC, DE, A и флаги — кроме
случаев, где сама Z80-инструкция их меняет.

Анализ живости: если после инструкции A (или флаги) гарантированно
перезаписываются до чтения в пределах прямолинейного участка, сохранение
A (флагов) опускается. Там, где перевод даёт НЕТОЧНЫЕ флаги (bit -> CY=0,
set/res -> флаги меняются, djnz, sbc hl -> Z по старшему байту, neg -> CY,
rl/rr -> нет Z/S/P), а флаги живы, ставится маркер ";!!FLAGS" и печатается
отчёт — такие места проверяются руками (overrides).

Использование: z80to8080.py in.asm out.asm [--overrides file.py] [--report]
"""
import re, sys, os

# ---------------------------------------------------------------- разбор строк
RE_LABEL = re.compile(r'^([A-Za-z_.][A-Za-z0-9_.]*)\s*:?')
COND = {'nz','z','nc','c','po','pe','p','m'}
REG8 = {'a','b','c','d','e','h','l'}
REG16 = {'bc','de','hl','sp','af'}
IDX = {'ix','iy'}
IDXH = {'ixh':'ix','ixl':'ix','iyh':'iy','iyl':'iy'}

def norm_expr(e):
    """pasmo-выражение -> zasm: #xx -> $xx, 0101B -> %0101, 0FFH -> $FF."""
    e = e.strip()
    e = re.sub(r'#([0-9A-Fa-f]+)', r'$\1', e)
    e = re.sub(r'(?<![A-Za-z0-9_$])([01]+)[Bb]\b', r'%\1', e)
    e = re.sub(r'(?<![A-Za-z0-9_$%])([0-9][0-9A-Fa-f]*)[Hh]\b', r'$\1', e)
    return e

def split_operands(s):
    out=[]; depth=0; cur=''
    instr=False
    for ch in s:
        if ch=="'" : instr = not instr
        if ch=='(' and not instr: depth+=1
        if ch==')' and not instr: depth-=1
        if ch==',' and depth==0 and not instr:
            out.append(cur.strip()); cur=''
        else: cur+=ch
    if cur.strip(): out.append(cur.strip())
    return out

class Line:
    def __init__(self, raw, no):
        self.raw=raw; self.no=no
        s=raw.rstrip('\n')
        # комментарий
        self.comment=''
        q=False; cut=None
        for i,ch in enumerate(s):
            if ch=="'": q=not q
            if ch==';' and not q: cut=i; break
        if cut is not None:
            self.comment=s[cut:]; s=s[:cut]
        self.label=None
        m=RE_LABEL.match(s)
        if m and not s[0].isspace():
            self.label=m.group(1); s=s[m.end():]
        s=s.strip()
        self.op=None; self.args=[]
        if s:
            parts=s.split(None,1)
            self.op=parts[0].lower()
            if len(parts)>1: self.args=split_operands(parts[1])
        # директивы-псевдо
        if self.op in ('defb','defm'): self.op='db'
        if self.op=='defw': self.op='dw'
        if self.op=='defs': self.op='ds'
        if self.op and self.op.upper()=='EQU': self.op='equ'
        # pasmo: "label EQU x" без двоеточия — уже разобрано как label+op

# ---------------------------------------------------------- классификация Z80
def parse_idx(arg):
    """'(ix+5)' -> ('ix','5'); '(iy)' -> ('iy','0'); иначе None"""
    m=re.match(r'^\(\s*(ix|iy)\s*(?:([+-])\s*(.+?))?\s*\)$', arg, re.I)
    if not m: return None
    reg=m.group(1).lower(); sign=m.group(2); d=m.group(3)
    if not sign: return (reg,'0')
    d=norm_expr(d)
    return (reg, d if sign=='+' else '-('+d+')')

def is_mem(arg): return arg.startswith('(') and arg.endswith(')')

# инструкции, читающие/пишущие A и флаги — для анализа живости
def reads_a(op,args):
    a=[x.lower() for x in args]
    if op in ('add','adc','sub','sbc','and','or','xor','cp'):
        if op in ('xor','sub') and a and a[-1]=='a': return False  # xor a / sub a: write-only
        return True
    if op in ('rlca','rrca','rla','rra','cpl','neg','daa','out','push') and (op!='push' or a==['af']): return True
    if op in ('ld','st') and len(a)==2 and a[1]=='a': return True
    if op=='ld' and len(a)==2 and a[1] in IDXH: return False
    if op in ('bit','set','res') and len(a)==2 and a[1]=='a': return True
    if op in ('rl','rr','rlc','rrc','sla','sra','srl') and a==['a']: return True
    if op=='ex' and a and a[0]=='af': return True
    if op in ('ret','call','jp','jr','djnz','rst','halt','exx'): return True   # неизвестно -> считаем живым
    if op=='ldir' or op=='ldi': return False
    return False
def writes_a(op,args):
    a=[x.lower() for x in args]
    if op in ('add','adc','sub','sbc','and','or','xor','neg','cpl','daa','rlca','rrca','rla','rra','in'): return True
    if op=='ld' and a and a[0]=='a': return True
    if op=='pop' and a==['af']: return True
    if op in ('rl','rr','rlc','rrc','sla','sra','srl') and a==['a']: return True
    if op=='ex' and a and a[0]=='af': return True
    return False
FL_ALL={'c','z','s','p'}
def flags_read(op,args):
    """множество флагов, которые инструкция читает ('?' = неизвестно/все)"""
    a=[x.lower() for x in args]
    if op in ('jp','jr','call','ret') and a and a[0] in COND:
        return {{'nz':'z','z':'z','nc':'c','c':'c','po':'p','pe':'p','p':'s','m':'s'}[a[0]]}
    if op in ('adc','sbc','rla','rra','rl','rr','ccf'): return {'c'}
    if op=='daa': return {'c'}
    if op=='push' and a==['af']: return FL_ALL
    if op=='ex' and a and a[0]=='af': return FL_ALL
    if op in ('ret','call','jp','jr','djnz','rst','halt'): return FL_ALL   # неизвестно
    return set()
def flags_written(op,args):
    """множество флагов, которые (после трансляции) инструкция гарантированно пишет"""
    a=[x.lower() for x in args]
    if op in ('add','adc','sub','sbc','and','or','xor','cp','neg','daa','bit','set','res'): return FL_ALL
    if op in ('sla',): return FL_ALL
    if op in ('inc','dec'):
        if a and a[0] in ('bc','de','hl','sp','ix','iy'): return set()
        return {'z','s','p'}
    if op in ('rlca','rrca','rla','rra','rl','rr','rlc','rrc','sra','srl','scf','ccf'): return {'c'}
    if op=='pop' and a==['af']: return FL_ALL
    if op=='ex' and a and a[0]=='af': return FL_ALL
    return set()
_LABELS={}
def _label_map(lines):
    key=id(lines)
    if key not in _LABELS:
        m={}
        for k,L in enumerate(lines):
            if L.label: m[L.label]=k
        _LABELS[key]=m
    return _LABELS[key]
CALL_READS_FLAGS=False   # в коде Ianna нет процедур, зависящих от входящих флагов (проверено grep'ом)
def flags_live_after(lines,i,fl,depth=0,seen=None):
    """живы ли (читаются раньше записи) флаги из множества fl после lines[i];
    идём вдоль потока управления, включая цели переходов (ограниченно)."""
    fl=set(fl)
    if seen is None: seen=set()
    labels=_label_map(lines)
    j=i+1; steps=0
    while j<len(lines) and steps<400:
        L=lines[j]; j+=1
        if L.op is None: continue
        steps+=1
        op=L.op; a=[x.lower() for x in L.args]
        if op in ('db','dw','ds','equ','org','end','include','incbin'): return False
        rd=flags_read(op,L.args)
        if op in ('jp','jr') and a and a[0] in COND:
            if a[0] in ('nz','z'): rd={'z'}
            elif a[0] in ('nc','c'): rd={'c'}
            elif a[0] in ('po','pe'): rd={'p'}
            else: rd={'s'}
            if fl & rd: return True
            tgt=a[1]
            if depth<6 and tgt in labels:
                k=(labels[tgt],frozenset(fl))
                if k not in seen:
                    seen.add(k)
                    if flags_live_after(lines,labels[tgt]-1,fl,depth+1,seen): return True
            elif tgt not in labels:
                return True
            continue
        if op in ('jp','jr') and a:
            tgt=a[0]
            if tgt.startswith('('): return True
            if depth<6 and tgt in labels:
                k=(labels[tgt],frozenset(fl))
                if k in seen: return False
                seen.add(k)
                return flags_live_after(lines,labels[tgt]-1,fl,depth+1,seen)
            return True
        if op=='call':
            if a and a[0] in COND:
                c={'nz':'z','z':'z','nc':'c','c':'c','po':'p','pe':'p','p':'s','m':'s'}[a[0]]
                if c in fl: return True
            if CALL_READS_FLAGS: return True
            fl-=FL_ALL   # после call флаги считаем перезаписанными вызываемой процедурой
            return False
        if op=='djnz':
            if fl & {'z','s','p'}: pass
            fl-=set()
            # djnz читает только B; ветвится: консервативно считаем оба пути
            tgt=a[0]
            if depth<6 and tgt in labels:
                k=(labels[tgt],frozenset(fl))
                if k not in seen:
                    seen.add(k)
                    if flags_live_after(lines,labels[tgt]-1,fl,depth+1,seen): return True
            continue
        if op=='ret':
            if a and a[0] in COND:
                c={'nz':'z','z':'z','nc':'c','c':'c','po':'p','pe':'p','p':'s','m':'s'}[a[0]]
                if c in fl: return True
                continue
            return True   # безусловный ret: вызывающий может проверять флаги
        if op in ('rst','halt'): return True
        if fl & rd: return True
        fl-=flags_written(op,L.args)
        if not fl: return False
    return True
def reads_flags(op,args): return bool(flags_read(op,args))
def writes_flags(op,args): return flags_written(op,args)==FL_ALL

DIRECTIVES=('db','dw','ds','equ','org','end','include','incbin')
def next_instr(lines,i):
    """Индекс следующей команды. None, если по дороге (или на ней самой) стоит метка:
    туда могут прыгнуть, и склеивать пару нельзя."""
    for j in range(i+1,len(lines)):
        L=lines[j]
        if L.label: return None
        if L.op is None: continue
        if L.op in DIRECTIVES: return None
        return j
    return None
def prev_instr(lines,i):
    """Индекс предыдущей команды (метка на самой lines[i] или между ними запрещает пару)."""
    if lines[i].label: return None
    for j in range(i-1,-1,-1):
        L=lines[j]
        if L.op is None:
            if L.label: return None
            continue
        if L.op in DIRECTIVES: return None
        return j
    return None
def idx_word(lines,i,j,noinl,kind):
    """Пара соседних строк, работающих со СЛОВОМ в записи по (ix+d)/(iy+d+1):
      kind='st': 'ld (i?+d),l' + 'ld (i?+d+1),h'   — сохранить HL в поле;
      kind='rd': 'ld e,(i?+d)'  + 'ld d,(i?+d+1)'  — прочитать поле в DE.
    Возвращает (ix|iy, d) либо None. Обе половины обязаны быть рядом, без метки
    на второй (туда могут прыгнуть) и вне окрестности 'jr cc,$+n' (noinl)."""
    if j is None or i in noinl or j in noinl: return None
    A,B=lines[i],lines[j]
    if A.op!='ld' or B.op!='ld' or len(A.args)!=2 or len(B.args)!=2: return None
    if kind=='st':
        p1,p2=parse_idx(A.args[0]),parse_idx(B.args[0])
        if A.args[1].strip().lower()!='l' or B.args[1].strip().lower()!='h': return None
    else:
        p1,p2=parse_idx(A.args[1]),parse_idx(B.args[1])
        if A.args[0].strip().lower()!='e' or B.args[0].strip().lower()!='d': return None
    if not p1 or not p2 or p1[0]!=p2[0]: return None
    d1,d2=const_d(p1[1]),const_d(p2[1])
    if d1 is None or d2 is None or d2!=d1+1 or d1<0: return None
    return p1[0],d1

def idx_pair(lines,i,j,noinl):
    """Пара 'ld i?h,r' + 'ld i?l,r2' одного индексного регистра (в любом порядке),
    источники — из b/c/d/e (h/l нельзя: пара собирается через HL, a дешевле и так).
    Возвращает (ix|iy, регистр-старший, регистр-младший) либо None."""
    if j is None or i in noinl or j in noinl: return None
    A,B=lines[i],lines[j]
    if A.op!='ld' or B.op!='ld' or len(A.args)!=2 or len(B.args)!=2: return None
    d1,s1=A.args[0].lower(),A.args[1].lower(); d2,s2=B.args[0].lower(),B.args[1].lower()
    if d1 not in IDXH or d2 not in IDXH or IDXH[d1]!=IDXH[d2] or d1[-1]==d2[-1]: return None
    if s1 not in ('b','c','d','e') or s2 not in ('b','c','d','e'): return None
    return (IDXH[d1], s1, s2) if d1.endswith('h') else (IDXH[d1], s2, s1)

def a_dead_after(lines,i):
    """A мёртв после lines[i]? (в пределах прямолинейного участка)"""
    for j in range(i+1,len(lines)):
        L=lines[j]
        if L.op is None: continue
        if L.op in ('db','dw','ds','equ','org','end','include','incbin'): return True
        if reads_a(L.op,L.args): return False
        if writes_a(L.op,L.args): return True
    return False
def flags_dead_after(lines,i):
    for j in range(i+1,len(lines)):
        L=lines[j]
        if L.op is None: continue
        if L.op in ('db','dw','ds','equ','org','end','include','incbin'): return True
        if reads_flags(L.op,L.args): return False
        if writes_flags(L.op,L.args): return True
    return False

# ------------------------------------------------- инлайн адреса (ix+d)/(iy+d)
# Хелперы z_ix_* стоят дорого: сам call (24 такта) плюс у «db d»-хелперов ещё
# ~100 тактов возни с адресом возврата (ex (sp),hl / z_ret / ex (sp),hl).
# Если d — константа, адрес считается на месте: ld hl,(z_ix) + inc hl * d.
# Такая последовательность НЕ трогает ни A, ни флаги — точная замена хелперу.
# Цена в байтах: 3 + |d| вместо «call+db» (4 Б) или «ld a,d + call» (5 Б),
# поэтому инлайним только малые d (политика IDX_INLINE, потолок по классам).
IDX_INLINE = {'rda':0, 'rd_hl':1, 'rd_e_ix':6, 'rd_d_ix':5, 'sta':0, 'st_r':4, 'addr':7}

def const_d(d):
    """смещение (ix+d) как число, если это константа; иначе None"""
    s=d.strip(); neg=False
    if s.startswith('-(') and s.endswith(')'): neg=True; s=s[2:-1].strip()
    if re.fullmatch(r'\$[0-9A-Fa-f]+',s): v=int(s[1:],16)
    elif re.fullmatch(r'[0-9]+',s): v=int(s)
    else: return None
    return -v if neg else v

def idx_prep(reg,dv):
    """HL := reg+dv; A и флаги целы"""
    return [f"ld hl,(z_{reg})"]+(["inc hl"]*dv if dv>=0 else ["dec hl"]*(-dv))

# ------------------------------------------------------------------ трансляция
class Translator:
    def __init__(self, fname, overrides=None):
        self.fname=fname; self.overrides=overrides or {}
        self.warns=[]; self.stats={}

    def stat(self,k): self.stats[k]=self.stats.get(k,0)+1

    def tr(self, lines):
        out=[]
        # 'jr cc,$+n' переводится в 'jp cc,$+1+n' — цель верна, только пока
        # пропускаемые инструкции той же длины, что на Z80. Инлайн длину меняет,
        # поэтому рядом с такими переходами он запрещён.
        self.noinl=set()
        for k,L in enumerate(lines):
            if L.op in ('jr','djnz') and L.args and '$' in L.args[-1]:
                n=0; j=k+1
                while j<len(lines) and n<8:
                    if lines[j].op is not None: self.noinl.add(j); n+=1
                    j+=1
        for i,L in enumerate(lines):
            key=(os.path.basename(self.fname), L.no)
            if key in self.overrides:
                out.append(f"; [override {key[0]}:{key[1]}] {L.raw.rstrip()}")
                if L.label: out.append(f"{L.label}:")
                out.extend(('' if o.rstrip().endswith(':') else '\t')+o for o in self.overrides[key]); continue
            out.extend(self.tr_line(lines,i,L))
        return out

    def emit_native(self,L):
        s=''
        if L.label: s+=L.label+':'
        if L.op:
            args=[norm_expr(a) for a in L.args]
            s+='\t'+L.op+(' '+', '.join(args) if args else '')
        if L.comment: s+='\t'+L.comment
        return [s] if s else ['']

    def tr_line(self, lines, i, L):
        op=L.op
        if op is None:
            return self.emit_native(L)
        if op in ('db','dw','ds','equ','org','end','include','incbin','if','endif','else','rept','endm','macro'):
            return self.emit_native(L)
        args=L.args
        a=[x.lower() for x in args]
        pre=[]
        if L.label: pre.append(L.label+':')
        cmt=('\t'+L.comment) if L.comment else ''
        adead=a_dead_after(lines,i); fdead=flags_dead_after(lines,i)
        def native():
            return pre+['\t'+op+(' '+', '.join(norm_expr(x) for x in args) if args else '')+cmt]
        def seq(body, tag):
            self.stat(tag)
            return pre+[f"\t; Z80> {op} {', '.join(args)}{cmt}"]+['\t'+b for b in body]
        def warn(what, fl=FL_ALL):
            if flags_live_after(lines,i,fl):
                self.warns.append((L.no, f"{op} {', '.join(args)}", what))
                return ['; !!FLAGS '+what]
            return []

        # --- индексные регистры ---
        idx=[parse_idx(x) for x in args]
        def inl(kind,d,reg=None):
            """инлайнить (ix+d)? -> смещение-число или None.
            Потолок ищется от частного ключа к общему: 'rd_e_ix' -> 'rd_e' -> 'rd_r'."""
            if i in getattr(self,'noinl',()): return None
            dv=const_d(d)
            if dv is None: return None
            keys=[f'{kind}_{reg}',kind] if reg else [kind]
            if kind.startswith('rd_') and kind!='rd_hl': keys.append('rd_r')
            if kind.startswith('st_') and kind!='st_hl': keys.append('st_r')
            for k in keys:
                lim=IDX_INLINE.get(k)
                if lim is not None:
                    return dv if lim>=0 and abs(dv)<=lim else None
            return None
        def addr(reg,d):
            """HL := ix+d (вызывающий уже сохранил HL): инлайн или хелпер"""
            dv=inl('addr',d,reg)
            if dv is not None:
                self.stat('ix_addr_inl'); return idx_prep(reg,dv)
            return [f"call z_{reg}_hl", f"db {d}"]
        if op=='ld' and len(args)==2:
            dst,src=args
            di,si=idx
            # --- СЛОВО в записи: пара соседних строк вместо двух отдельных обращений ---
            # 'ld (ix+d),l' + 'ld (ix+d+1),h' в оригинале — просто «сохранить HL в поле».
            # Порознь каждая половина стоила ld (z_a),a / ld a,l / call z_ix_sta / db d /
            # ld a,(z_a) — 11 байт и 280 тактов (A прячется, потому что жив). Вместе достаточно
            # одолжить BC: 12 байт и 104 такта на обе, причём A, DE, BC, HL и флаги целы.
            # Симметрично 'ld e,(ix+d)' + 'ld d,(ix+d+1)' — «прочитать поле в DE».
            noinl=getattr(self,'noinl',())
            for kind,tag in (('st','ix_word_st'),('rd','ix_word_rd')):
                w=idx_word(lines,i,next_instr(lines,i),noinl,kind)
                if w:
                    reg,dv=w
                    if kind=='st':
                        body=["push bc","ld c,l","ld b,h"]+idx_prep(reg,dv)+[
                              "ld (hl),c","inc hl","ld (hl),b","ld h,b","ld l,c","pop bc"]
                    else:
                        body=["push hl"]+idx_prep(reg,dv)+["ld e,(hl)","inc hl","ld d,(hl)","pop hl"]
                    return seq(body,tag)
                k=prev_instr(lines,i)
                if k is not None and idx_word(lines,k,i,noinl,kind):
                    self.stat(tag+'_2nd')
                    return pre+[f"\t; Z80> {op} {', '.join(args)}{cmt} — сделано парой выше"]
            # ld r,(ix+d)
            if si:
                reg,d=si; rz='z_'+reg
                if a[0]=='a':
                    dv=inl('rda',d,reg)
                    if dv is not None:
                        return seq(["push hl"]+idx_prep(reg,dv)+["ld a,(hl)","pop hl"],'ix_rd_a_inl')
                    h = f"{rz}_rda" if not fdead else f"{rz}_rda_nf"
                    return seq([f"ld a,{d}", f"call {h}"], 'ix_rd_a')
                if a[0] in ('b','c','d','e'):
                    dv=inl(f'rd_{a[0]}',d,reg)
                    if dv is not None:
                        return seq(["push hl"]+idx_prep(reg,dv)+[f"ld {a[0]},(hl)","pop hl"],'ix_rd_r_inl')
                    return seq([f"call {rz}_rd_{a[0]}", f"db {d}"], 'ix_rd_r')
                if a[0] in ('h','l'):
                    # результат кладём в старый HL — только через A (свободных регистров нет),
                    # поэтому при живом A он прячется в z_a (ISR эту ячейку сохраняет)
                    dv=inl('rd_hl',d,reg)
                    if dv is not None:
                        body=[] if adead else ["ld (z_a),a"]
                        body+=["push hl"]+idx_prep(reg,dv)+["ld a,(hl)","pop hl",f"ld {a[0]},a"]
                        if not adead: body+=["ld a,(z_a)"]
                        return seq(body,'ix_rd_hl_inl')
                    return seq([f"call {rz}_rd_{a[0]}", f"db {d}"], 'ix_rd_r')
                raise ValueError(f"{L.no}: {L.raw}")
            # ld (ix+d),x
            if di:
                reg,d=di; rz='z_'+reg
                if a[1]=='a':
                    dv=inl('sta',d,reg)
                    if dv is not None:
                        return seq(["push hl"]+idx_prep(reg,dv)+["ld (hl),a","pop hl"],'ix_st_a_inl')
                    return seq([f"call {rz}_sta", f"db {d}"], 'ix_st_a')
                if a[1] in ('b','c','d','e'):
                    dv=inl(f'st_{a[1]}',d,reg)
                    if dv is not None:
                        return seq(["push hl"]+idx_prep(reg,dv)+[f"ld (hl),{a[1]}","pop hl"],'ix_st_r_inl')
                    return seq([f"call {rz}_st_{a[1]}", f"db {d}"], 'ix_st_r')
                if a[1] in ('h','l'):
                    dv=inl('st_hl',d,reg)
                    if dv is not None:
                        body=[] if adead else ["ld (z_a),a"]
                        body+=[f"ld a,{a[1]}","push hl"]+idx_prep(reg,dv)+["ld (hl),a","pop hl"]
                        if not adead: body+=["ld a,(z_a)"]
                        return seq(body,'ix_st_hl_inl')
                    body=[] if adead else ["ld (z_a),a"]
                    body+=[f"ld a,{a[1]}", f"call {rz}_sta", f"db {d}"]
                    if not adead: body+=["ld a,(z_a)"]
                    return seq(body,'ix_st_hl')
                # immediate
                dv=inl('stn',d,reg)
                if dv is not None:
                    return seq(["push hl"]+idx_prep(reg,dv)+[f"ld (hl),{norm_expr(src)}","pop hl"],'ix_st_n_inl')
                # метка «A мёртв» — build_vec.per_offset_helpers превращает такие площадки в
                # 'ld a,n / call z_i?_st{d}' (те же 5 байт, 136 тактов против 252)
                return seq([f"call {rz}_stn", f"db {d}", f"db {norm_expr(src)}"+("\t; A мёртв" if adead else '')], 'ix_st_n')
            # ld ix,nn / ld ix,(nn) / ld (nn),ix
            if a[0] in IDX:
                rz='z_'+a[0]
                if is_mem(src):
                    return seq(["push hl", f"ld hl,{norm_expr(src)}", f"ld ({rz}),hl", "pop hl"],'ix_ld_mem')
                return seq(["push hl", f"ld hl,{norm_expr(src)}", f"ld ({rz}),hl", "pop hl"],'ix_ld_nn')
            if a[1] in IDX:
                rz='z_'+a[1]
                return seq(["push hl", f"ld hl,({rz})", f"ld {norm_expr(dst)},hl", "pop hl"],'ix_st_mem')
            # ixh/ixl
            if a[0] in IDXH:
                # Пара 'ld ixh,d' + 'ld ixl,e' (в любом порядке) — это просто IX := DE.
                # Порознь каждая половина стоит push af / ld a,r / ld (nn),a / pop af — 6 байт и
                # 52 такта; вместе — push hl / ld h,r / ld l,r2 / ld (z_ix),hl / pop hl: 7 байт и
                # 60 тактов на обе. A и флаги не трогаются, HL бережётся стеком, поэтому склейка
                # безопасна при любом вызывающем. Метка между половинами (и на второй) запрещена:
                # туда могут прыгнуть. Запись z_ix становится двухбайтовой — прерывание между
                # половинами больше невозможно, а ISR z_ix/z_iy и так сохраняет и восстанавливает.
                noinl=getattr(self,'noinl',())
                p=idx_pair(lines,i,next_instr(lines,i),noinl)
                if p:
                    reg,hi,lo=p
                    return seq(["push hl", f"ld h,{hi}", f"ld l,{lo}", f"ld (z_{reg}),hl", "pop hl"],'ixh_pair')
                k=prev_instr(lines,i)
                if k is not None and idx_pair(lines,k,i,noinl):
                    self.stat('ixh_pair_2nd')
                    return pre+[f"\t; Z80> {op} {', '.join(args)}{cmt} — собрано парой выше"]
                cell='z_'+IDXH[a[0]]+('+1' if a[0].endswith('h') else '')
                if a[1]=='a': return seq([f"ld ({cell}),a"],'ixh_ld_a')
                if a[1] in REG8: return seq(["push af", f"ld a,{a[1]}", f"ld ({cell}),a", "pop af"],'ixh_ld_r')
                if a[1] in IDXH:
                    c2='z_'+IDXH[a[1]]+('+1' if a[1].endswith('h') else '')
                    return seq(["push af", f"ld a,({c2})", f"ld ({cell}),a", "pop af"],'ixh_ld_ixh')
                return seq(["push af", f"ld a,{norm_expr(src)}", f"ld ({cell}),a", "pop af"],'ixh_ld_n')
            if a[1] in IDXH:
                cell='z_'+IDXH[a[1]]+('+1' if a[1].endswith('h') else '')
                if a[0]=='a': return seq([f"ld a,({cell})"],'ld_a_ixh')
                return seq(["push af", f"ld a,({cell})", f"ld {a[0]},a", "pop af"],'ld_r_ixh')
            # ld (nn),de/bc ; ld de,(nn) ; ld bc,(nn) ; ld sp,(nn)
            if a[0]=='de' and is_mem(src): return seq(["push hl", f"ld hl,{norm_expr(src)}", "ex de,hl", "pop hl"],'ld_de_mem')
            if a[0]=='bc' and is_mem(src): return seq(["push hl", f"ld hl,{norm_expr(src)}", "ld b,h", "ld c,l", "pop hl"],'ld_bc_mem')
            if a[0]=='sp' and is_mem(src): return seq(["push hl", f"ld hl,{norm_expr(src)}", "ld sp,hl", "pop hl"],'ld_sp_mem')
            if a[1]=='de' and is_mem(dst): return seq(["push hl", "ex de,hl", f"ld {norm_expr(dst)},hl", "ex de,hl", "pop hl"],'ld_mem_de')
            if a[1]=='bc' and is_mem(dst): return seq(["push hl", "ld h,b", "ld l,c", f"ld {norm_expr(dst)},hl", "pop hl"],'ld_mem_bc')
            if a[1]=='sp' and is_mem(dst): return seq(["push hl", "ld hl,0", "add hl,sp", f"ld {norm_expr(dst)},hl", "pop hl"],'ld_mem_sp')
            return native()

        # push/pop ix
        if op=='push' and a[0] in IDX:
            return seq(["push hl", f"ld hl,(z_{a[0]})", "ex (sp),hl"],'push_ix')
        if op=='pop' and a[0] in IDX:
            return seq(["ex (sp),hl", f"ld (z_{a[0]}),hl", "pop hl"],'pop_ix')
        if op in ('inc','dec') and a[0] in IDX:
            return seq(["push hl", f"ld hl,(z_{a[0]})", f"{op} hl", f"ld (z_{a[0]}),hl", "pop hl"],'incdec_ix')
        if op=='add' and a[0] in IDX:
            rz='z_'+a[0]
            if a[1] in ('bc','de'):
                return seq(["push hl", f"ld hl,({rz})", f"add hl,{a[1]}", f"ld ({rz}),hl", "pop hl"],'add_ix')
            if a[1]==a[0]:
                return seq(["push hl", f"ld hl,({rz})", "add hl,hl", f"ld ({rz}),hl", "pop hl"],'add_ix')
            raise ValueError(L.raw)
        # ALU с ixh/ixl или (ix+d)
        if op in ('add','adc','sub','sbc','and','or','xor','cp') :
            x=a[-1]
            if x in IDXH:
                cell='z_'+IDXH[x]+('+1' if x.endswith('h') else '')
                o=op if len(a)==1 else f"{op} a,"
                body=["push hl", f"ld hl,{cell}", f"{op} {'a,' if op in ('add','adc','sbc') else ''}(hl)", "pop hl"]
                return seq(body,'alu_ixh')
            ii=parse_idx(args[-1])
            if ii:
                reg,d=ii
                body=["push hl"]+addr(reg,d)+[f"{op} {'a,' if op in ('add','adc','sbc') else ''}(hl)", "pop hl"]
                return seq(body,'alu_idx')
        if op in ('inc','dec') and len(a)==1:
            ii=parse_idx(args[0])
            if ii:
                reg,d=ii
                return seq(["push hl"]+addr(reg,d)+[f"{op} (hl)", "pop hl"],'incdec_idx')
            if a[0] in IDXH:
                cell='z_'+IDXH[a[0]]+('+1' if a[0].endswith('h') else '')
                return seq(["push hl", f"ld hl,{cell}", f"{op} (hl)", "pop hl"],'incdec_ixh')
        # --- bit/set/res ---
        if op in ('bit','set','res'):
            n=norm_expr(args[0]); tgt=a[1]
            if re.fullmatch(r'[0-7]', n):
                mask=f"${1<<int(n):02X}"; nmask=f"${(~(1<<int(n)))&0xFF:02X}"
            else:
                mask=f"1<<({n})" ; nmask=f"$FF^(1<<({n}))"
            ii=parse_idx(args[1])
            w=[]
            if op=='bit':
                w=warn('bit: CY=0 (Z80 сохраняет CY)',{'c'})
                if tgt=='a':
                    body=([] if adead else ["ld (z_a),a"])+[f"and {mask}"]+([] if adead else ["ld a,(z_a)"])
                elif tgt in REG8:
                    body=([] if adead else ["ld (z_a),a"])+[f"ld a,{tgt}", f"and {mask}"]+([] if adead else ["ld a,(z_a)"])
                elif tgt=='(hl)':
                    body=([] if adead else ["ld (z_a),a"])+["ld a,(hl)", f"and {mask}"]+([] if adead else ["ld a,(z_a)"])
                elif ii:
                    reg,d=ii
                    body=["push hl"]+addr(reg,d)+([] if adead else ["ld (z_a),a"])+["ld a,(hl)", f"and {mask}"]+([] if adead else ["ld a,(z_a)"])+["pop hl"]
                else: raise ValueError(L.raw)
                return seq(body,'bit')+w
            else:
                w=warn(f'{op}: флаги меняются (Z80 не трогает)',FL_ALL)
                alu=f"or {mask}" if op=='set' else f"and {nmask}"
                if tgt=='a':
                    body=[alu]
                elif tgt in REG8:
                    body=([] if adead else ["ld (z_a),a"])+[f"ld a,{tgt}", alu, f"ld {tgt},a"]+([] if adead else ["ld a,(z_a)"])
                elif tgt=='(hl)':
                    body=([] if adead else ["ld (z_a),a"])+["ld a,(hl)", alu, "ld (hl),a"]+([] if adead else ["ld a,(z_a)"])
                elif ii:
                    reg,d=ii
                    body=["push hl"]+addr(reg,d)+([] if adead else ["ld (z_a),a"])+["ld a,(hl)", alu, "ld (hl),a"]+([] if adead else ["ld a,(z_a)"])+["pop hl"]
                else: raise ValueError(L.raw)
                return seq(body,op)+w
        # --- переходы ---
        if op=='jr':
            a2=[norm_expr(x) for x in args]
            if '$' in a2[-1]:
                # jr на $+n перескакивает через следующие инструкции; jp на байт длиннее jr,
                # поэтому цель = $+n+1 (верно, пока пропускаемые инструкции той же длины на i8080)
                a2[-1]=a2[-1].replace('$','$+1')
            return pre+['\tjp '+', '.join(a2)+cmt]
        if op=='djnz':
            tgt=norm_expr(args[0])
            if '$' in tgt: tgt=tgt.replace('$','$-1')   # '$' относился к самому djnz = адресу 'dec b'
            return seq(["dec b", f"jp nz,{tgt}"],'djnz')+warn('djnz: dec b меняет Z/S/P',{'z','s','p'})
        # --- блочные ---
        if op=='ldir': return seq(["call z_ldir"],'ldir')
        if op=='ldi':  return seq(["call z_ldi"],'ldi')
        if op=='exx':  return seq(["call z_exx"],'exx')
        if op=='ex' and a[0]=='af': return seq(["call z_exaf"],'exaf')
        # --- 16-бит sbc/adc ---
        if op in ('sbc','adc') and a[0]=='hl':
            rr=a[1]; lo={'bc':'c','de':'e','hl':'l'}[rr]; hi={'bc':'b','de':'d','hl':'h'}[rr]
            body=([] if adead else ["ld (z_a),a"])+[f"ld a,l", f"{op} a,{lo}", "ld l,a", "ld a,h", f"{op} a,{hi}", "ld h,a"]+([] if adead else ["ld a,(z_a)"])
            return seq(body,op+'_hl')+warn(f'{op} hl: Z только по старшему байту',{'z','s','p'})
        # --- neg ---
        if op=='neg':
            return seq(["cpl","inc a"],'neg')+warn('neg: CY не выставляется',{'c'})
        # --- сдвиги/вращения через CB ---
        if op in ('rl','rr','rlc','rrc','sla','sra','srl'):
            tgt=a[0]; ii=parse_idx(args[0])
            core={'rl':['rla'],'rr':['rra'],'rlc':['rlca'],'rrc':['rrca'],'sla':['add a,a'],
                  'srl':['or a','rra'],'sra':['ld (z_tmp),a','rla','ld a,(z_tmp)','rra']}[op]
            fw=warn(f'{op}: нет Z/S/P (только CY)',{'z','s','p'}) if op!='sla' else []
            if tgt=='a':
                return seq(core,op)+fw
            if tgt in REG8:
                body=([] if adead else ["ld (z_a),a"])+[f"ld a,{tgt}"]+core+[f"ld {tgt},a"]+([] if adead else ["ld a,(z_a)"])
                return seq(body,op)+fw
            if tgt=='(hl)':
                body=([] if adead else ["ld (z_a),a"])+["ld a,(hl)"]+core+["ld (hl),a"]+([] if adead else ["ld a,(z_a)"])
                return seq(body,op)+fw
            if ii:
                reg,d=ii
                body=["push hl"]+addr(reg,d)+([] if adead else ["ld (z_a),a"])+["ld a,(hl)"]+core+["ld (hl),a"]+([] if adead else ["ld a,(z_a)"])+["pop hl"]
                return seq(body,op)+fw
            raise ValueError(L.raw)
        # --- нормализация 'sub a,x' / 'and a,x' ---
        if op in ('sub','and','or','xor','cp') and len(a)==2 and a[0]=='a':
            return pre+[f"\t{op} {norm_expr(args[1])}{cmt}"]
        if op=='jp' and a and a[0] in ('(ix)','(iy)'):
            raise ValueError(L.raw)
        # Z80-only, которых быть не должно
        if op in ('rld','rrd','otir','outi','cpir','cpi','ldd','lddr','im','reti','retn','in','out') :
            if op in ('in','out') and len(a)==2 and ('(c)' in a): raise ValueError(f"{L.no}: {L.raw}")
            if op not in ('in','out'): raise ValueError(f"{L.no}: {L.raw}")
        return native()

def load_overrides(path):
    ns={}
    exec(open(path,encoding='utf-8').read(), ns)
    return ns.get('OVERRIDES',{})

def main():
    args=sys.argv[1:]
    ov={}; report=False
    if '--overrides' in args:
        k=args.index('--overrides'); ov=load_overrides(args[k+1]); del args[k:k+2]
    if '--report' in args: report=True; args.remove('--report')
    src,dst=args[0],args[1]
    raw=open(src,encoding='utf-8',errors='replace').read().split('\n')
    lines=[Line(r,i+1) for i,r in enumerate(raw)]
    T=Translator(src,ov)
    out=T.tr(lines)
    hdr=[f"; ==== {os.path.basename(src)} -> i8080 (z80to8080.py) ====",'']
    open(dst,'w',encoding='utf-8').write('\n'.join(hdr+out)+'\n')
    if report or T.warns:
        print(f"{os.path.basename(src)}: {len(out)} строк, замены: {T.stats}")
        for no,ins,what in T.warns:
            print(f"  !!FLAGS {os.path.basename(src)}:{no}: {ins}  -- {what}")
    return 0

if __name__=='__main__':
    sys.exit(main())
