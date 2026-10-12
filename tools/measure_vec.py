#!/usr/bin/env python3
"""Headless-замер по тактам (Вектор-06Ц, i8080 3 МГц, кадр 59904 тактов): прерывание в начале обратного
хода НЕ защёлкивается — если INTE=0, теряется (как Emu80/MiSTer). ВИ53 счётчик 0 эмулируется (1.5 МГц,
режим 0, latch по out $08=0) — для таймерного бюджета. Печатает: доставлено/потеряно прерываний,
тиков, кадров/тик, где терялись (по функциям).
  python3 tools/measure_vec.py [rom lst] [--route=right:300] [--start=3,1] [--frames=600] [--fixrand]
Маршрут — отрезки «клавиши:кадров» через запятую: none, right, fire+right ...; fight — бой по сценарию
FIGHT (удары во все стороны с шагами, один и тот же для любой сборки); pace — ходьба туда-обратно. Текст скрипта посреди отрезка
снимается сам («огонь» на wait_till_read до следующего тика); такие тики в среднее не входят.
--pos=X,Y — место героя на стартовом экране в пикселях (штатное место уровня на чужом экране бывает в воздухе).
Герой на время замера неуязвим (здоровье возвращается каждый тик); --mortal — как в игре.
  IANNA_EDD=<edd> — образ квазидиска для этой сборки
"""
import sys, re, bisect, collections, pathlib
pc_ring=[]; bh_n=[0]
ARGS=[a for a in sys.argv[1:] if not a.startswith('--')]; OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROM=ARGS[0] if ARGS else 'build/ianna.rom'; LST=ARGS[1] if len(ARGS)>1 else 'build/ianna_vec.lst'
FRAMES=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'600'))
ROUTE=next((o[8:] for o in OPTS if o.startswith('--route=')),'none:300,right:300')
START=next((tuple(int(v) for v in o[8:].split(',')) for o in OPTS if o.startswith('--start=')),None)
FIXRAND='--fixrand' in OPTS
SLOWN=float(next((o[7:] for o in OPTS if o.startswith('--slow=')),'0'))   # --slow=N: отдельный профиль тиков длиннее N кадров
PROF=any(o.startswith('--prof') for o in OPTS); PROFN=int(next((o[7:] for o in OPTS if o.startswith('--prof=')),'40'))
SHOT=next((o[7:] for o in OPTS if o.startswith('--shot=')),None)
POS=next((tuple(int(v) for v in o[6:].split(',')) for o in OPTS if o.startswith('--pos=')),None)   # место героя на стартовом экране, px
BHIST='--budget-hist' in OPTS
NOFG='--nofg' in OPTS   # замер без передних тайлов: слой FG обнуляется в ОЗУ при каждом DrawScreen   # гистограмма отказов бюджета: фаза кадра и цена запроса   # FrameCounter := номер тика перед RunScripts — логика не зависит от скорости сборки (сравнение A/B на сценах с врагами)
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
FRAME=59904
# --turbo: режим «CPU Speed 6MHz» ядра MiSTer. Там турбо — это ДВЕ вещи сразу: фазы процессора идут
# вдвое чаще И cpu_ready держится в единице, то есть ожиданий видеоконтроллера нет вовсе (память в
# FPGA двухпортовая, видео берёт свой порт). Поэтому такт инструкции равен её паспортному значению
# i8080 без округления до шинного слота, а кадр вмещает вдвое больше тактов.
if '--turbo' in OPTS:
    _T8 = {}
    for _op in range(256):
        _hi, _lo, _d = _op >> 6, _op & 7, (_op >> 3) & 7
        if _op == 0x76: _T8[_op] = 7
        elif _hi == 1: _T8[_op] = 7 if (_lo == 6 or _d == 6) else 5
        elif _hi == 2: _T8[_op] = 7 if _lo == 6 else 4
        elif _hi == 0:
            if _lo == 6: _T8[_op] = 10 if _d == 6 else 7
            elif _lo == 1: _T8[_op] = 10
            elif _lo == 2: _T8[_op] = {0x22: 16, 0x2A: 16, 0x32: 13, 0x3A: 13}.get(_op, 7)
            elif _lo == 3: _T8[_op] = 5
            elif _lo in (4, 5): _T8[_op] = 10 if _d == 6 else 5
            else: _T8[_op] = 4
        else:
            if _lo == 0: _T8[_op] = 11
            elif _lo == 1: _T8[_op] = 5 if _op in (0xE9, 0xF9) else 10
            elif _lo == 2: _T8[_op] = 10
            elif _lo == 3: _T8[_op] = {0xE3: 18, 0xEB: 5, 0xF3: 4, 0xFB: 4}.get(_op, 10)
            elif _lo == 4: _T8[_op] = 17
            elif _lo == 5: _T8[_op] = 17 if _op == 0xCD else 11
            elif _lo == 6: _T8[_op] = 7
            else: _T8[_op] = 11
    CYC = [_T8[_op] for _op in range(256)]
    FRAME = 59904 * 2          # 6 МГц: вдвое больше тактов в том же кадре 50 Гц
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100
rv.patch_menu(cpu, LST)          # набор без оверлея меню (уровни 2+): фазу меню глушим
rv.STEP_BUDGET=400000       # прогрев без обрыва обычного кадра по числу инструкций (старт одинаков у любых
                            # сборок), но busy-loop сообщения уровня всё же получает прерывание
mem=cpu.mem
# --- ВИ53 счётчик 0 ---
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
FC=sym['FrameCounter']; AT=sym['animate_tile']; SC=sym['SaveCheckpoint']
DSCR=sym.get('DrawScreen',-1); VBW=sym.get('vbg_wait',-1); DTW=sym.get('dtd_wait',-2);   # ожидания кадра: общий vec_budget и вписанный в dt_direct bh_cost=collections.Counter(); bh_phase=collections.Counter(); bh_lost=[0]
bh_cost=collections.Counter(); bh_phase=collections.Counter(); bh_lost=[0]
# --tail=spr|all — ОЦЕНКА идеи «не терять хвост кадра»: запрос бюджета, не влезший до конца кадра, делает
# сейчас столько, сколько влезает, а остаток — после прерывания. Кода в ROM для этого нет: стенд просто
# возвращает время влезшей части (минус накладные второго входа TAIL_OVH; меньше TAIL_MIN не режем).
# spr — только колонки спрайтов (vec_spr_colbud: цена NY*1,25+8), all — любой запрос (потолок).
TAIL=next((o[7:] for o in OPTS if o.startswith('--tail=')),None); VBL=228; TAIL_OVH=10; TAIL_MIN=5
# --nolatewait — ОЦЕНКА идеи «опоздавший тик не ждёт начала кадра»: waitforVBlank делает halt всегда, даже
# когда frames_noredraw уже >= frames_lock; стенд этот halt пропускает (вывод начинается с любой фазы кадра).
NOLATE=any(o.startswith('--nolatewait') for o in OPTS); LATEWIN=[tuple(int(v) for v in w.split('-')) for w in next((o[13:] for o in OPTS if o.startswith('--nolatewait=')),'0-999').split(',')]   # --nolatewait=A-B[,C-D]: только при фазе кадра в окне
WHG=sym.get('waitforvblank_halt_go',-1); FNR=sym['frames_noredraw']; FLK=sym['frames_lock']
WHF=sym['vec_wait_halted']; nolate_n=[0]
VBA=sym.get('vbg_again',-1); DTB=sym.get('dtd_bud',-1); tail_credit=[0]; tail_sum=[0]
delivered=0; lost=0; lost_at=collections.Counter(); next_irq=FRAME; started=False
def run(nframes):
    global delivered,lost,next_irq,started
    end=cyc[0]+nframes*FRAME
    while cyc[0]<end:
        if cpu.halted:
            cyc[0]=next_irq
        else:
            if START and not started and cpu.pc==SC:
                mem[sym['current_levelx']]=START[0]; mem[sym['current_levely']]=START[1]; started=True
            cyc[0]+=CYC[mem[cpu.pc]]
            try: cpu.step()
            except RuntimeError:
                print('  КРАХ; последние PC:', ' '.join(f'{x:04X}' for x in pc_ring[-24:])); raise
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie:
                cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else:
                lost+=1; lost_at[fn(cpu.pc)]+=1
HOLD=None
# бой: (клавиши, кадров) по кругу — удары вправо/вверх/вниз/влево с паузами и шаг туда-обратно
FIGHT=[(['fire','right'],10),([],6),(['fire','up'],10),([],6),(['fire','down'],10),([],6),
       (['fire','left'],10),([],6),(['right'],12),(['left'],12)]
PACE=[(['right'],30),(['left'],30)]      # ходьба туда-обратно: «right» за 200 кадров уходит с экрана
SCEN={'fight':FIGHT,'pace':PACE}
def scen_keys(name,f):
    sc=SCEN[name]; f%=sum(n for _,n in sc)
    for k,n in sc:
        if f<n: return k
        f-=n
IMMORTAL='--mortal' not in OPTS; EPP=sym['ENTITY_PLAYER_POINTER']; energy0=[None]; hits=[0]
WT=sym.get('wait_till_read',-1); AS=sym.get('action_string',-1)
def rd(a): return mem[a]
ntick=[0]
w=rv.Warmup(sym,keys); patched=False; started=False   # прогрев общий с run_vec (сообщение уровня снимается автоматически)
for fr in range(1500):
    end=cyc[0]+FRAME
    while cyc[0]<end:
        if cpu.halted: cyc[0]=next_irq
        else:
            pc=cpu.pc
            if START and not patched and pc==SC: mem[sym['current_levelx']]=START[0]; mem[sym['current_levely']]=START[1]; patched=True; mem[sym['initial_coordx']]=POS[0] if POS else mem[sym['initial_coordx']]; mem[sym['initial_coordy']]=POS[1] if POS else mem[sym['initial_coordy']]
            if w.step(pc,fr): started=True
            cyc[0]+=CYC[mem[pc]]; cpu.step()
        if cyc[0]>=next_irq:
            next_irq+=FRAME
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1
    if started: break
assert started, 'игра не стартовала'
keys.clear(); run(10)
print(f'{ROM}: старт {"экран "+str(START) if START else "начало уровня"}; прогрев: доставлено {delivered}, потеряно {lost}')
if NOFG:   # NOFG после прогрева: экран уже нарисован, дальше передние тайлы не перерисовываются
    for k in range(160): mem[sym['CURRENT_SCREEN_MAP_FG']+k]=0
for seg in ROUTE.split(','):
    k,n=seg.split(':'); n=int(n)
    keys.clear()
    if k not in SCEN:
        for kk in k.split('+'):
            if kk!='none': keys.append(kk)
    tickprof=collections.Counter(); slowprof=collections.Counter(); nslow=[0]; slowinfo=[]; prof=collections.Counter(); n_ext=0; hits[0]=0; where=collections.Counter();  route_keys=list(keys); seg_fr=0; in_wait=False; seen_msg=False; nmsg=0
    if k in SCEN: keys[:]=scen_keys(k,0)
    d0,l0=delivered,lost
    # тики считаем по входам в RunScripts; тики со сменой экрана (LoadScreen внутри) — отдельно
    hold_ticks=[0]; hold_slow=[0]
    RS=sym['RunScripts']; LS=sym['LoadScreen']; end=cyc[0]+n*FRAME; tick_frames=[]; tstart=cyc[0]; seen_load=False; idle=0
    while cyc[0]<end:
        pc=cpu.pc
        if pc==LS: seen_load=True
        elif pc==AS: seen_msg=True
        elif pc==WT and not in_wait: in_wait=True; seen_msg=True; keys[:]=['fire']
        if pc==RS:
            if IMMORTAL:      # здоровье героя (байт 4 сущности) держим на стартовом: иначе великан убивает его
                ep=EPP                                  # за сотню кадров и дальше меряется экран конца игры
                if energy0[0] is None: energy0[0]=mem[ep+4]
                elif mem[ep+4]<energy0[0]: hits[0]+=1; mem[ep+4]=energy0[0]
            if in_wait: in_wait=False; keys[:]=scen_keys(k,seg_fr) if k in SCEN else route_keys
            nmsg+=seen_msg
            if PROF:
                if SLOWN and (cyc[0]-tstart)/FRAME>=SLOWN and not seen_load and not seen_msg: slowprof.update(tickprof); nslow[0]+=1; slowinfo.append((len(tick_frames),round((cyc[0]-tstart)/FRAME,1),mem[sym['vec_slot_next']] if 'vec_slot_next' in sym else -1,mem[sym['ndirtyrects']]))
                tickprof.clear()
            if seen_msg: end+=cyc[0]-tstart; n_ext+=(cyc[0]-tstart)/FRAME   # печать текста (~200 кадров) в длину отрезка не входит
            tick_frames.append(((cyc[0]-tstart)/FRAME, 'M' if seen_msg else seen_load)); tstart=cyc[0]; seen_load=False; seen_msg=False
            if HOLD: hold_ticks[0]+=1; hold_slow[0]+=1 if mem[HOLD]>=8 else 0   # темп анимации: сколько тиков в замедленном режиме
            if FIXRAND: ntick[0]+=1; mem[sym['FrameCounter']]=ntick[0]&0xFF; mem[sym['FrameCounter']+1]=0
        if cpu.halted: idle+=next_irq-cyc[0]; cyc[0]=next_irq
        else:
            if TAIL and tail_credit[0] and (cpu.pc==VBA or cpu.pc==DTB):
                # модель «блит режется по строкам»: часть, влезавшая в хвост прошлого кадра, уже сделана —
                # возвращаем её время (часы и точка перезарядки ВИ53 сдвигаются вместе: фаза для бюджета та же)
                cyc[0]-=tail_credit[0]; pit['reload_cyc']-=tail_credit[0]; tstart=min(tstart,cyc[0]); tail_sum[0]+=tail_credit[0]; tail_credit[0]=0
            if NOLATE and cpu.pc==WHG and mem[FNR]>=mem[FLK] and not mem[WHF] and any(lo<=(cyc[0]-pit['reload_cyc'])/256<hi for lo,hi in LATEWIN):
                cpu.pc+=1; nolate_n[0]+=1      # тик уже опоздал: halt перед выводом пропускаем
            if cpu.pc==VBW or cpu.pc==DTW:
                bh_n[0]+=1
                if TAIL:
                    sp=cpu.sp; ret=mem[sp+2]|mem[sp+3]<<8
                    who=fn(ret) if cpu.pc==VBW else 'dt_direct'
                    if TAIL=='all' or who=='vec_spr_colbud':
                        ph=(cyc[0]-pit['reload_cyc'])/256
                        cr=VBL-ph-TAIL_OVH
                        if cr>=TAIL_MIN: tail_credit[0]=int(cr*256)
                if BHIST:
                    cost=cpu.l; phase=(cpu.a-cost)&0xFF
                    bh_cost[cost]+=1; bh_phase[phase//16*16]+=1; bh_lost[0]+=max(0,234-phase)
            if PROF: prof[fn(cpu.pc)]+=CYC[mem[cpu.pc]]; tickprof[fn(cpu.pc)]+=CYC[mem[cpu.pc]]
            cyc[0]+=CYC[mem[cpu.pc]]
            try: cpu.step()
            except RuntimeError:
                print('  КРАХ; последние PC:', ' '.join(f'{x:04X}' for x in pc_ring[-24:])); raise
        if cyc[0]>=next_irq:
            next_irq+=FRAME; seg_fr+=1
            where[fn(cpu.pc)]+=1
            if k in SCEN and not in_wait: keys[:]=scen_keys(k,seg_fr)
            if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38; delivered+=1
            else: lost+=1; lost_at[fn(cpu.pc)]+=1
    d1,l1=delivered,lost; dd=d1-d0; dl=l1-l0; idle_pct=idle/((n+n_ext)*FRAME)*100
    norm=[f for f,l in tick_frames[1:] if not l]; loads=[f for f,l in tick_frames[1:] if l and l!='M']
    avg=sum(norm)/max(len(norm),1)
    print(f'  {k:10s} {n:4d} кадров: потеряно прерываний {dl} ({dl/n*100:.1f} %); обычных тиков {len(norm)}: {avg:.2f} кадра/тик ({50/max(avg,0.01):.1f} тик/с), доля тиков >5 кадров {sum(1 for f in norm if f>5.5)/max(len(norm),1)*100:.0f} %, простой (halt) {idle_pct:.0f} %' + (f'; смен экрана {len(loads)}: {", ".join(f"{f:.0f}" for f in loads)} кадров' if loads else '')
          + (f'; тиков с текстом {nmsg}' if nmsg else '')
          + (f'; ударов по герою {hits[0]}' if hits[0] else '')
          + f'; экран {mem[sym["current_levelx"]]},{mem[sym["current_levely"]]}' + (f', герой погиб ({mem[sym["player_dead"]]})' if mem[sym['player_dead']] else '')
          + (f'; анимация замедлена в {hold_slow[0]/max(hold_ticks[0],1)*100:.0f} % тиков' if HOLD else ''))
    if SHOT:      # снимок экрана в конце отрезка: проверить, что герой стоит где надо и враг в кадре
        rv.render(bytes(mem[0x8000:0x10000]), list(mem[sym['vec_palette']:sym['vec_palette']+16]), f'{SHOT}_{k}.png')
    if PROF:
        nt=max(len(tick_frames),1); tot=sum(prof.values())
        print(f'    профиль, тактов на тик (кадр = {FRAME}); всего работы {tot/nt/FRAME:.2f} кадра/тик, простой {idle/nt/FRAME:.2f}:')
        for name,c in prof.most_common(PROFN): print(f'      {name:28s} {c/nt:8.0f}  {c/tot*100:5.1f} %')
    if PROF and SLOWN and nslow[0]:
        tot=sum(slowprof.values())
        print(f'    медленные тики (>= {SLOWN} кадров): {nslow[0]}; работа {tot/nslow[0]/FRAME:.2f} кадра/тик; (номер тика, кадров, слотов, прямоугольников): {slowinfo[:12]}')
        for name,c in slowprof.most_common(PROFN): print(f'      ~{name:27s} {c/nslow[0]:8.0f}  {c/tot*100:5.1f} %')
    if '--where' in OPTS: print('    PC на прерывании:', dict(where.most_common(6)), 'клавиши в конце:', keys, 'ожидание текста:', in_wait)
    if norm:
        import collections as _c
        h=_c.Counter(min(int(f+0.5),12) for f in norm)
        print('    длительность тиков (кадров: сколько): ' + ' '.join(f'{k}:{h[k]}' for k in sorted(h)))
if BHIST and sum(bh_cost.values()):
    n=sum(bh_cost.values())
    print(f'  отказы бюджета: {n}; цена запроса (ед. 256 тактов): {sorted(bh_cost.items())}')
    print(f'  фаза кадра при отказе (ед.): {sorted(bh_phase.items())}')
    print(f'  потеряно хвостов: {bh_lost[0]} ед. = {bh_lost[0]/234:.1f} кадра, в среднем {bh_lost[0]/n:.0f} ед. на отказ')
print(f'  ожиданий кадра бюджетом (vbg_wait) за прогон: {bh_n[0]}' + (f'; пропущено ожиданий опоздавшего тика: {nolate_n[0]}' if NOLATE else '') + (f'; модель хвостов ({TAIL}): возвращено {tail_sum[0]/FRAME:.1f} кадра' if TAIL else ''))
if lost: print('  потери по функциям:', dict(lost_at.most_common(8)))
