#!/usr/bin/env python3
"""Модель луча (Вектор-06Ц, i8080 3 МГц, кадр 59904 тактов, 312 строк × 192): что РЕАЛЬНО видит луч.
Строка экрана y (0..255 сверху) проходится на такте T(y) = 7636 + 192·y от кадрового прерывания
(скролл $FF, верх = линия VRAM 255; база из модели KV: скролл $1F → строка поля 0 на 13780).
В этот такт снимаем строку из всех четырёх плоскостей (mem[$8000+line::256]) и сравниваем с тем,
что в VRAM в конце кадра (итог) и было в конце предыдущего кадра (старое):
  «старое»  — луч показал прошлый кадр (запись пришла позже луча),
  «дыра»    — ни старое, ни итог: строка жила разобранной (фон стёрт, спрайт не дорисован).
Сценарий: вход на экран 4,6 уровня 2 справа и удары мечом вплотную к голему (как golem_close2).
  IANNA_EDD=<edd> python3 tools/beam_vec.py [rom lst] [--start=5,6] [--ticks=90] [--png=DIR]
Печатает по кадрам с расхождениями в рамке героя (+меча): такт начала/конца сброса пула, строки.
"""
import sys, re, bisect, collections, pathlib, os
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]; OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROM=ARGS[0] if ARGS else 'build/ianna.rom'; LST=ARGS[1] if len(ARGS)>1 else 'build/ianna_vec.lst'
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),(5,6))
NT=int(next((o[8:] for o in OPTS if o.startswith('--ticks=')),'90'))
PNG=next((o[6:] for o in OPTS if o.startswith('--png=')),None)
MAXPNG=int(next((o[9:] for o in OPTS if o.startswith('--maxpng=')),'16'))
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904; T0=7636; TL=192
sym=rv.load_syms(pathlib.Path(LST))
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100
rv.patch_menu(cpu, LST); rv.STEP_BUDGET=400000
mem=cpu.mem
# ВИ53 счётчик 0 (как в measure_vec)
pit={'reload_cyc':0,'latched':None,'wr':0,'rd':0,'lo':0}
base_out=cpu.out_handler; base_in=cpu.in_handler
cyc=[0]
def out_h(p,v):
    if p==0x08:
        if v==0: pit['latched']=(0xFFFF-(((cyc[0]-pit['reload_cyc'])//2)&0xFFFF))&0xFFFF; pit['rd']=0
        return
    if p==0x0B:
        if pit['wr']==0: pit['lo']=v; pit['wr']=1
        else: pit['wr']=0; pit['reload_cyc']=cyc[0]
        return
    base_out(p,v)
def in_h(p):
    if p==0x0B:
        v=pit['latched'] if pit['latched'] is not None else (0xFFFF-(((cyc[0]-pit['reload_cyc'])//2)&0xFFFF))&0xFFFF
        if pit['rd']==0: pit['rd']=1; return v&0xFF
        pit['rd']=0; pit['latched']=None; return v>>8
    return base_in(p)
cpu.out_handler=out_h; cpu.in_handler=in_h
SC=sym['SaveCheckpoint']; RS=sym['RunScripts']; SPD=sym['SPDATA']; LX=sym['current_levelx']
PF=sym['vec_pool_flush']; PFD=sym.get('vpf_done',-1); DSL=sym['DrawSpriteList']; RIT=sym['RedrawInvTiles']
next_irq=FRAME; delivered=0; lost=0
# --latewin=A-B[,C-D] — модель правки ожидания (на сборке БЕЗ неё): опоздавший тик пропускает halt, если фаза кадра
# (ед. 256 тактов от прерывания) в одном из окон. 0-234 = не ждать никогда. Поле на экране: фазы ~30..150.
LATEWIN=[tuple(int(v) for v in w.split('-')) for w in next((o[10:] for o in OPTS if o.startswith('--latewin=')),'').split(',') if w]
WHG=sym.get('waitforvblank_halt_go',-1); FNR=sym['frames_noredraw']; FLK=sym['frames_lock']; WHF=sym['vec_wait_halted']
# --- прогрев (как measure_vec) ---
w=rv.Warmup(sym,keys); patched=False; started=False
for fr in range(1500):
    end=cyc[0]+FRAME
    while cyc[0]<end:
        if cpu.halted: cyc[0]=next_irq
        else:
            pc=cpu.pc
            if START and not patched and pc==SC: mem[LX]=START[0]; mem[sym['current_levely']]=START[1]; patched=True
            if w.step(pc,fr): started=True
            cyc[0]+=CYC[mem[pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1
    if started: break
assert started,'игра не стартовала'
keys.clear()
# детерминированный random (как golem_close): сцена одинакова у сборок A/B — сверка по тикам
a_=sym['random']; rd_=sym['randData']; mem[a_:a_+9]=bytes((0x3A,rd_&0xFF,rd_>>8,0xC6,0x4D,0x32,rd_&0xFF,rd_>>8,0xC9))
def spr(i):
    r=mem[SPD+i*8:SPD+i*8+8]
    return (r[2]&0x7f, ((r[0]|r[1]<<8)-0x8000)//384, r[3], r[4]) if (r[0]|r[1]) else None
def sx(i): return mem[SPD+i*8+3]
# --- сценарий по тикам (вход в RunScripts) ---
phase=['enter']; t_close=[0]; tick=[0]
def on_tick():
    """Клавиши на следующий тик. Возвращает False, когда сценарий закончен."""
    tick[0]+=1
    if phase[0]=='enter':
        keys[:]=['left']
        if mem[LX]==4: phase[0]='action'; t_close[0]=0
    elif phase[0]=='action':
        t_close[0]+=1; keys[:]=['action'] if t_close[0]<=6 else []
        if t_close[0]>=9: phase[0]='walk'; t_close[0]=0
    elif phase[0]=='walk':
        keys[:]=['left']; t_close[0]+=1
        if abs(sx(1)-sx(0))<=30 or t_close[0]>60: phase[0]='pause'
    elif phase[0]=='pause':
        keys[:]=[]; phase[0]='hit'; t_close[0]=-1
    elif phase[0]=='hit':
        t_close[0]+=1
        if t_close[0]>=NT: return False
        keys[:]=['fire','left'] if t_close[0]%6 in (0,1,2) else []
    return True
# --- кадр с моделью луча ---
seen=[None]*256; prev_final=None
frame_no=[0]; fstart=[0]; nrow=[0]
def capture_upto(c):
    """Снять все строки, которые луч прошёл к такту c (внутри кадра)."""
    while nrow[0]<256 and c>=fstart[0]+T0+TL*nrow[0]:
        y=nrow[0]; line=255-y; seen[y]=bytes(mem[0x8000+line:0x10000:256]); nrow[0]+=1
def finish_frame():
    capture_upto(fstart[0]+FRAME)
    return bytes(mem[0x8000:0x10000])
def row_of(final,y):
    line=255-y; return final[line:0x8000:256]
report=[]; npng=[0]; hist=collections.Counter(); frames_total=0; frames_bad=0; g_rows=0; g_frames=0; g_hole=0; hero_old=0; hero_hole=0; hero_new=0; all_old=0
flush=[None,None]; dsl=[None]; rit=[None]; hero_at_tick=[None]
running=True; hit_frames=[]
EPP=sym['ENTITY_PLAYER_POINTER']; e0=[None]
VSL=sym['vpf_slot']; VGD=sym.get('vpf_guard',-1); VGO=sym.get('vpf_guard_ok',-1); VDN=sym['vpf_done']
slot_dt=[]; last_slot=[None]; fl_len=[]; fl_slots=[]; fl_start=[None]; fl_n=[0]; guard_spin=[0]; g_in=[None]
fstart[0]=next_irq-FRAME
while running:
    pc=cpu.pc
    if pc==RS:
        if e0[0] is None: e0[0]=mem[EPP+4]      # герой неуязвим: иначе голем убивает его и в прогон попадает экран гибели
        elif mem[EPP+4]<e0[0]: mem[EPP+4]=e0[0]
        hero_at_tick[0]=(tick[0],spr(0),spr(3),spr(1))
        running=on_tick()
    if pc==PF: flush[0]=cyc[0]-fstart[0]; fl_start[0]=cyc[0]; fl_n[0]=0; last_slot[0]=None
    if pc==VSL:
        if last_slot[0] is not None: slot_dt.append(cyc[0]-last_slot[0])
        last_slot[0]=cyc[0]; fl_n[0]+=1
    if pc==VGD and g_in[0] is None: g_in[0]=cyc[0]
    if pc==VGO and g_in[0] is not None: guard_spin[0]+=cyc[0]-g_in[0]; g_in[0]=None
    if pc==VDN and fl_start[0] is not None: fl_len.append(cyc[0]-fl_start[0]); fl_slots.append(fl_n[0]); fl_start[0]=None
    if pc==DSL: dsl[0]=cyc[0]-fstart[0]
    if pc==RIT: rit[0]=cyc[0]-fstart[0]
    if LATEWIN and pc==WHG and mem[FNR]>=mem[FLK] and not mem[WHF]:
        ph=(cyc[0]-fstart[0])/256
        if any(lo<=ph<hi for lo,hi in LATEWIN): cpu.pc+=1; pc=cpu.pc   # модель: опоздавший тик не ждёт кадра, если луч в окне
    if cpu.halted:
        capture_upto(next_irq-1); cyc[0]=next_irq
    else:
        cyc[0]+=CYC[mem[pc]]; cpu.step(); capture_upto(cyc[0])
    if cyc[0]>=next_irq:
        # конец кадра: итог и разбор
        final=finish_frame(); frames_total+=1
        if prev_final is not None and phase[0]=='hit' and hero_at_tick[0]:
            tk,h,sw,g=hero_at_tick[0]
            # по всему полю (игровые строки 0..159 = экранные 32..191): рваные строки и дыры
            gr=0; gh=0
            for y in range(32,192):
                s=seen[y]; f=row_of(final,y)
                if s!=f:
                    gr+=1
                    if s!=row_of(prev_final,y): gh+=1
            g_rows+=gr; g_hole+=gh; g_frames+=1 if gr else 0
            if h:
                x0=min(h[2],(sw[2] if sw else h[2]))-8; x1=max(h[2],(sw[2] if sw else h[2]))+32
                c0=max(0,x0//8); c1=min(32,(x1+7)//8); ys=range(h[3]+32,h[3]+64)
                old=[];hole=[];new=[]
                for y in ys:
                    s=seen[y]; f=row_of(final,y); p=row_of(prev_final,y)
                    sel=lambda r: b''.join(r[k*32+c0:k*32+c1] for k in range(4))
                    S_,F_,P_=sel(s),sel(f),sel(p)
                    if F_==P_: continue                      # строка не менялась — нечего рвать
                    if S_==F_: new.append(y)
                    elif S_==P_: old.append(y)
                    else: hole.append(y)
                # рваный кадр = в рамке героя есть И новые, И старые строки, либо дыры;
                # «всё старое» — не дефект (поза опоздала на кадр целиком)
                if old and not new and not hole: all_old+=1
                if (old and new) or hole:
                    frames_bad+=1; hist[tk]+=1; hero_old+=len(old); hero_hole+=len(hole); hero_new+=len(new)
                    report.append(f'кадр {frames_total} тик {tk} герой {h} меч {sw} голем {g}: фон@{rit[0]} спрайты@{dsl[0]} сброс@{flush[0]} '
                                  f'(строки луча {((flush[0] or 0)-T0)//TL}); новых {len(new)} {new[:4]}, старых {len(old)} {old[:4]}, дыр {len(hole)} {hole[:6]}')
                    if PNG and npng[0]<MAXPNG:
                        vr=bytearray(0x8000)
                        for y in range(256):
                            line=255-y; vr[line:0x8000:256]=seen[y]
                        pal=list(mem[sym['vec_palette']:sym['vec_palette']+16])
                        os.makedirs(PNG,exist_ok=True)
                        rv.render(bytes(vr),pal,f'{PNG}/beam_f{frames_total:03d}_t{tk}.png')
                        rv.render(final,pal,f'{PNG}/final_f{frames_total:03d}_t{tk}.png')
                        npng[0]+=1
                if phase[0]=='hit' and sw: hit_frames.append(frames_total)
        prev_final=final
        next_irq+=FRAME; fstart[0]=next_irq-FRAME; nrow[0]=0; flush[0]=None; dsl[0]=None; rit[0]=None
        if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
        else: lost+=1
print(f'{ROM}: старт {START}; кадров в сцене ударов {frames_total}, РВАНЫХ в рамке героя {frames_bad} (строк новых {hero_new}, старых {hero_old}, дыр {hero_hole}); кадров с целиком старой позой {all_old}; потеряно прерываний {lost}')
if slot_dt:
    sd=sorted(slot_dt); n=len(sd)
    print(f'  слот сброса (такты между входами vpf_slot): медиана {sd[n//2]}, p10 {sd[n//10]}, p90 {sd[n*9//10]}, n={n}')
if fl_len:
    fl=sorted(fl_len); n=len(fl)
    print(f'  длина сброса: медиана {fl[n//2]/FRAME:.2f} кадра, p90 {fl[n*9//10]/FRAME:.2f}, макс {fl[-1]/FRAME:.2f}; слотов за сброс: медиана {sorted(fl_slots)[n//2]}, макс {max(fl_slots)}; сбросов {n}; спин стража всего {guard_spin[0]/FRAME:.2f} кадра')
print(f'  всё поле: кадров с рваными строками {g_frames}, рваных строк {g_rows}, из них дыр {g_hole}; тиков с рваным героем {len(hist)}')
print('\n'.join(report[:60]))
if len(report)>60: print(f'… ещё {len(report)-60}')
