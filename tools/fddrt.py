#!/usr/bin/env python3
"""Загрузка с дискеты «как на железе»: пустой (или замусоренный) квазидиск, прерывания ПО ТАКТАМ, а не на halt.
Обычный fdd_boot_test подаёт прерывание только на halt, а в загрузчике набора halt нет — обработчик
прерывания во время загрузки там не исполняется вовсе.
  python3 tools/fddrt.py [--junk] [--frames=3000] [--drq=N] [--strict]   (--strict: окна квазидиска как на железе; --junk: квазидиск заполнен мусором, как на MiSTer
  после другой игры; --drq=N: байт сектора появляется через N тактов после чтения предыдущего)"""
import sys, os, pathlib, re, bisect, collections, random
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
ROOT=pathlib.Path(__file__).resolve().parents[1]
FR=int(next((o[9:] for o in OPTS if o.startswith('--frames=')),'3000')); DRQ=int(next((o[6:] for o in OPTS if o.startswith('--drq=')),'0'))
edd=ROOT/'build/_fddrt.edd'
rnd=random.Random(7)
edd.write_bytes(bytes(rnd.randrange(256) for _ in range(262144)) if '--junk' in OPTS else bytes(262144))
os.environ['IANNA_EDD']=str(edd); os.environ['IANNA_FDD']=str(ROOT/'build/ianna.fdd')
sys.argv=[sys.argv[0]]; sys.path.insert(0,str(ROOT/'tools')); import run_vec as rv
src=open(ROOT/'tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
LST=ROOT/'build/ianna_vec.lst'; sym=rv.load_syms(LST)
_s={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: _s.setdefault(int(m.group(1),16),m.group(2))
_a=sorted(_s); _n=[_s[a] for a in _a]
def fn(pc):
    if pc>=0x8000: return '$%04X'%(pc&0xFF00)
    k=bisect.bisect_right(_a,pc)-1; return _n[k] if k>=0 else '?'
keys=[]; cpu=rv.make_cpu(keys); mem=cpu.mem
if '--strict' in OPTS:
    # Квазидиск как в ядре MiSTer и на железе (Vector-06C.sv: ed_ram = ed_reg[5] & ed_win): биты 6 и 7 порта
    # только РАСШИРЯЮТ окно $A000-$DFFF до $8000 и до $FFFF, а включает его бит 5. Стендовый эмулятор и Emu80
    # считают три окна независимыми — там $43 открывает одно окно $8000-$9FFF, на железе не открывает ничего.
    def _kv_strict(a, stackrq=False):
        if cpu.kv_stack_mode and stackrq: return True, cpu.kv_page_stack + a
        m = cpu.kv_map_mode
        if m & 0x20:
            if 0xA000 <= a <= 0xDFFF or ((m & 0x40) and 0x8000 <= a <= 0x9FFF) or ((m & 0x80) and 0xE000 <= a <= 0xFFFF):
                return True, cpu.kv_page_map + a
        return False, a
    cpu._kv_addr = _kv_strict
# make_cpu глушит вызов меню (в пустом квазидиске оверлея нет) — возвращаем ROM из образа как есть:
# на железе фаза меню исполняется, и проверять надо именно её
_img=open(os.environ['IANNA_FDD'],'rb').read(); mem[0x100:0x100+32512]=_img[0x80:0x80+32512]
SHOTDIR=next((o[7:] for o in OPTS if o.startswith('--shot=')),None); SHOTS=(set(range(2000,FR,150))|{2300,2700,3100,3500}) if SHOTDIR else set(); vr={}
if SHOTDIR: os.makedirs(SHOTDIR,exist_ok=True)
INTRO='--intro' in OPTS; dark=[]; CHEAT='--cheat' in OPTS or INTRO; st=[]
FRAME=59904; cyc=0; nxt=FRAME; fr=0; ev=[]; lost=0; hist=collections.Counter()
names={sym[k]:k for k in ('vec_to_menu','vec_start','vfl_done','vec_menu_phase','MUSIC_Load','MUSIC_Stop','vec_reload_set','RunScripts','vec_begin_level','vfl_go') if k in sym}
seen=collections.Counter()
while fr<FR:
    pc=cpu.pc
    if pc in names:
        seen[names[pc]]+=1
        if seen[names[pc]]<=3: ev.append((fr,names[pc]))
    if cpu.halted: cyc=nxt
    else:
        if fr>FR-200: hist[fn(pc)]+=1
        cyc+=CYC[mem[pc]]
        try: cpu.step()
        except RuntimeError as e: ev.append((fr,'КРАХ pc=%04X %s'%(pc,str(e)[:60]))); break
    if cyc>=nxt:
        nxt+=FRAME; fr+=1
        if CHEAT:
            # сценарий проверки читов: F1+F3 в меню, старт, затем I, G, L
            plan={2300:['f1','f3'],2320:[],2400:['fire'],2420:[],2600:['fire'],2620:[],2800:['fire'],2820:[],3000:['fire'],3020:[],3250:['fire'],3270:[],3400:['fire'],3420:[],
                  3600:['i'],3610:[],3700:['g'],3710:[],3800:['right'],4500:['l'],4510:[],4520:['fire'],4540:[]}
            if fr>4600 and fr%200==0: keys[:]=['fire']
            if fr>4600 and fr%200==20: keys[:]=[]
            if fr in plan and not INTRO: keys[:]=plan[fr]
            if INTRO:
                ip={2350:['fire'],2370:[],2750:['fire'],2770:[],3150:['fire'],3170:[]}
                if fr in ip: keys[:]=ip[fr]
                if fr>=2340: dark.append(not any(mem[sym['vec_palette']:sym['vec_palette']+16]))
            if fr in (2330,3590,3620,3695,3720,4490,4560,FR-1):
                st.append((fr,'чит=%d бог=%d уровень=%d экран=%d,%d здоровье=%d тиков=%d'%(mem[sym['vec_cheat']],mem[sym['vec_god']],mem[sym['current_level']]+1,mem[sym['current_levelx']],mem[sym['current_levely']],mem[sym['ENTITY_PLAYER_POINTER']+4],seen['RunScripts']), bytes(mem[0x8000:0x10000])))
        else:
            if fr in range(2000,FR,200): keys[:]=['fire']
            if fr in range(2020,FR,200): keys[:]=[]
        if fr in SHOTS: rv.render(bytes(mem[0x8000:0x10000]), list(mem[sym['vec_palette']:sym['vec_palette']+16]), f'{SHOTDIR}/fdd_{fr}.png'); vr[fr]=bytes(mem[0x8000:0x10000])
        if cpu.ie: cpu.ie=False; cpu.halted=False; cpu.push(cpu.pc); cpu.pc=0x38
        else: lost+=1
print('события (кадр, точка):',ev[:24]); print('потеряно прерываний',lost,'; RunScripts',seen['RunScripts'],'; в конце PC=%04X SP=%04X'%(cpu.pc,cpu.sp))
print('где сидит в последние 200 кадров:',hist.most_common(6)); print('маркер набора:',bytes(cpu.kvaz[3*65536+0xC800:3*65536+0xC802]))

if SHOTDIR:
    import hashlib, json
    json.dump({str(k):hashlib.md5(v).hexdigest() for k,v in vr.items()}, open(f'{SHOTDIR}/vram.json','w'))

if INTRO:
    runs=[]; n=0
    for i,d in enumerate(dark+[False]):
        if d: n+=1
        elif n: runs.append((2340+i-n,n)); n=0
    print('  экран погашен: (с кадра, кадров):',runs)
elif CHEAT:
    for f,s,_ in st: print('  кадр',f,s)
    a=next(v for f,_,v in st if f==3590); b=next(v for f,_,v in st if f==3620)
    d=[i for i in range(32768) if a[i]!=b[i]]
    print('  после I изменилось байт экрана:',len(d), 'колонки', sorted({(i>>8)&31 for i in d})[:10], 'строки L', sorted({i&255 for i in d})[:4], '..', sorted({i&255 for i in d})[-2:] if d else '')
    rv.render(b, list(mem[sym['vec_palette']:sym['vec_palette']+16]), str(ROOT/'build/cmp/cheat_i.png'))
