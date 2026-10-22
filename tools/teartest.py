#!/usr/bin/env python3
"""Разрыв перерисовки по кадрам: что ВИДНО на экране. Прогон с прерываниями по тактам (как rtcheck), луч
снимает строки поля из VRAM в момент своего прохода (кадр 59904 такта, строка поля y — на такте
13824 + 192*y от прерывания, как дедлайны героя в pool_hr.asm). Между двумя тиками (RunScripts) меняется
множество байтов поля; показанный кадр «рваный», если в нём часть этих байтов уже новая, а часть ещё
старая, и «промежуточный», если байт ни старый, ни новый (видна недорисовка: фон без спрайта и т.п.).
По спрайтам (--sprites): то же, но только в прямоугольнике каждого спрайта (старое место + новое), спрайт
узнаётся по банку (vec_sprite_bank на входе drawSprite). Для него же — окно, пока он выведен наполовину:
от первого до конца последнего его слота в сбросе (vpf_slot, L = индекс стайла), и окно «если бы его
слоты шли подряд» (число слотов * средняя цена слота). Разрыв возможен, если луч проходит прямоугольник
за это окно: P ~ (окно + 0.75*высота)/234 — оценка выигрыша от вывода слотов спрайта группой.
  python3 tools/teartest.py <rom> <lst> <edd> X,Y [--ticks=120] [--route=fight|pace] [--pos=x,y] [--sprites [--join=14,15]]
  --join — банки одного существа (голем — два спрайта) считаются одним прямоугольником."""
import sys, os, pathlib, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]; A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST=A[:4]; os.environ['IANNA_EDD']=EDD
NT=int(next((o[8:] for o in OPTS if o.startswith('--ticks=')),'120')); ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'fight')
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904; Y_TOP_L=223; L0=64; NL=160            # строки поля: L 223 (верх, y=0) .. 64 (низ, y=159)
SC={'fight':[['fire','right'],[],['fire','up'],[],['fire','down'],[],['fire','left'],[],['right'],['right'],['left'],['left'],['up'],['down']],
    'pace':[['right']]*6+[['left']]*6}[ROUTE]
def field(mem):
    return bytes(b for y in range(NL) for b in line(mem, Y_TOP_L-y))
def line(mem, L):
    return bytes(mem[p+c*256+L] for p in (0x8000,0xA000,0xC000,0xE000) for c in range(32))
sym=rv.load_syms(pathlib.Path(LST)); keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu, LST)
mem=cpu.mem; a=sym['random']; rd=sym['randData']; mem[a:a+9]=bytes((0x3A,rd&0xFF,rd>>8,0xC6,0x4D,0x32,rd&0xFF,rd>>8,0xC9))
pit={'reload':0,'latched':None,'wr':0,'rd':0}; cyc=[0]; bo=cpu.out_handler; bi=cpu.in_handler
def oh(p,v):
    if p==0x08:
        if v==0: pit['latched']=(0xFFFF-(((cyc[0]-pit['reload'])//2)&0xFFFF))&0xFFFF; pit['rd']=0
        return
    if p==0x0B:
        if pit['wr']==0: pit['wr']=1
        else: pit['wr']=0; pit['reload']=cyc[0]
        return
    bo(p,v)
def ih(p):
    if p==0x0B:
        v=pit['latched'] if pit['latched'] is not None else (0xFFFF-(((cyc[0]-pit['reload'])//2)&0xFFFF))&0xFFFF
        if pit['rd']==0: pit['rd']=1; return v&0xFF
        pit['rd']=0; pit['latched']=None; return v>>8
    return bi(p)
cpu.out_handler=oh; cpu.in_handler=ih
RS=sym['RunScripts']; SCP=sym['SaveCheckpoint']; WT=sym.get('wait_till_read',-1); FC=sym['FrameCounter']; EPP=sym['ENTITY_PLAYER_POINTER']
st=tuple(int(v) for v in ST.split(',')); pos=next((tuple(int(v) for v in o[6:].split(',')) for o in OPTS if o.startswith('--pos=')),None)
patched=False; ticks=0; e0=None; wait=False; nxt=FRAME; saved=[]
# луч: frame_t0 — такт прерывания текущего кадра, ln — следующая строка поля к снятию
frame_t0=0; ln=0; shown=[None]*NL; frames=[]              # frames: (тик, кадр поля как список строк)
def beam_to(t):
    global ln, frame_t0
    while True:
        if ln>=NL:
            frames.append((ticks, b''.join(shown))); ln=0; frame_t0+=FRAME
        tl=frame_t0+13824+192*ln
        if tl>t: return
        shown[ln]=line(mem, Y_TOP_L-ln); ln+=1
snaps={}
SPR='--sprites' in OPTS; JOIN={int(b):'+'.join(g.split(',')) for g in [next((o[7:] for o in OPTS if o.startswith('--join=')),'')] if g for b in g.split(',')}; DS=sym['drawSprite']; VS=sym['vpf_slot']; SB=sym['vec_sprite_bank']
sprs=collections.defaultdict(list); slots=collections.defaultdict(list)   # тик -> [(банк,x,y)], [(такт, индекс стайла)]
while ticks<NT+40:
    pc=cpu.pc
    if pc==SCP and not patched:
        mem[sym['current_levelx']]=st[0]; mem[sym['current_levely']]=st[1]; patched=True
        if pos: mem[sym['initial_coordx']]=pos[0]; mem[sym['initial_coordy']]=pos[1]
    elif pc==WT and not wait: wait=True; saved=list(keys); keys[:]=['fire']
    elif pc==RS:
        if wait: wait=False; keys[:]=saved
        ticks+=1; mem[FC]=ticks&0xFF; mem[FC+1]=0
        if e0 is None: e0=mem[EPP+4]
        elif mem[EPP+4]<e0: mem[EPP+4]=e0
        if ticks>40:
            keys[:]=SC[(ticks-40)%len(SC)]; snaps[ticks]=field(mem)
    if SPR and ticks>40:
        if pc==DS: sprs[ticks].append((mem[SB], cpu.b, cpu.c))
        elif pc==VS: slots[ticks].append((cyc[0], cpu.l))
    irq=False
    if cpu.halted:
        beam_to(nxt); cyc[0]=nxt; irq=True
    else:
        cyc[0]+=CYC[mem[pc]]; cpu.step()
        if cyc[0]>=frame_t0+13824+192*ln or ln>=NL: beam_to(cyc[0])
        irq = cyc[0]>=nxt
    if irq:
        nxt+=FRAME
        if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38
# разбор: кадры, показанные между тиками k и k+1, против снимков S_k (старое) и S_{k+1} (новое)
torn=0; mid=0; total=0; tt=collections.Counter(); rows_t=[]
for k in sorted(snaps):
    if k+1 not in snaps: continue
    old=snaps[k]; new=snaps[k+1]; ch=[i for i in range(len(old)) if old[i]!=new[i]]
    if not ch: continue
    for t,img in frames:
        if t!=k: continue
        total+=1
        n_new=sum(1 for i in ch if img[i]==new[i]); n_old=sum(1 for i in ch if img[i]==old[i] and img[i]!=new[i])
        n_mid=sum(1 for i in ch if img[i]!=new[i] and img[i]!=old[i])
        if n_new and n_old:
            torn+=1; tt[k]+=1
            ys=sorted({i//128 for i in ch if img[i]==old[i] and img[i]!=new[i]}); rows_t.append(len(ys))
        if n_mid: mid+=1
ticked=len([k for k in snaps if k+1 in snaps])
print(f'{ROM} {ST} {ROUTE}: тиков {ticked}, кадров {total}; рваных кадров {torn} (тиков с разрывом {len(tt)}, '
      f'{100*len(tt)/max(ticked,1):.0f} %), в среднем старых строк в рваном кадре {sum(rows_t)/max(len(rows_t),1):.0f}; '
      f'кадров с недорисовкой {mid}')

if SPR:
    # сброс тика k (по нашим снимкам) выводит спрайты, нарисованные в тике k: ищем кадры между RS_k и RS_k+1
    per=collections.defaultdict(lambda: [0,0,0,0.,0.,0])   # банк -> [тиков, рваных тиков, рваных кадров, окно, окно подряд, слотов]
    prev={}
    dur=[]
    for k in sorted(slots):
        sl=slots[k]; dur+= [b[0]-a[0] for a,b in zip(sl,sl[1:]) if b[0]-a[0]<6000]
    sd=sum(dur)/max(len(dur),1)
    for k in sorted(snaps):
        if k+1 not in snaps: continue
        old=snaps[k]; new=snaps[k+1]
        cur=collections.defaultdict(list)
        for bank,x,y in sprs.get(k,[]):
            cur[JOIN.get(bank,bank)].append((x,y))
        for bank,pts in cur.items():
            rect=pts+prev.get(bank,[])
            prev[bank]=pts
            idx=set()
            for (rx,ry) in rect:
                for yy in range(max(ry,0),min(ry+32,NL)):
                    for c in range(rx//8, min(rx//8+3,32)):
                        for pl in range(4): idx.add(yy*128+pl*32+c)
            ch=[i for i in idx if old[i]!=new[i]]
            if not ch: continue
            st={((i//128)//16)*16 + (i%32)//2 for i in ch}           # стайлы, где спрайт что-то поменял
            ts=[t for t,l in slots.get(k,[]) if l in st]
            r=per[bank]; r[0]+=1
            nt=0
            for t,img,*_ in frames:
                if t!=k: continue
                if any(img[i]==new[i] for i in ch) and any(img[i]==old[i] and img[i]!=new[i] for i in ch): nt+=1
            r[2]+=nt; r[1]+=nt>0
            if ts: r[3]+=(max(ts)-min(ts)+sd)/256; r[4]+=len(ts)*sd/256; r[5]+=len(ts)
    print(f'  слот сброса в среднем {sd/256:.1f} ед.')
    for bank,(n,tt_,tf,w,wg,ns) in sorted(per.items(), key=lambda kv: str(kv[0])):
        print(f'  банк {str(bank):>5}: тиков {n}, рваных {tt_} ({100*tt_/max(n,1):.0f} %, кадров {tf}); слотов на тик {ns/max(n,1):.1f}, '
              f'окно наполовину {w/max(n,1):.0f} ед., подряд было бы {wg/max(n,1):.0f} ед.')
