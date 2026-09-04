"""Профиль по статьям, привязанный к ТИКАМ (а не кадрам).

Зачем отдельно от profile_vec.py: тот гоняет 300 КАДРОВ и жмёт «вправо». Ускоряющая правка меняет
число тиков в этих кадрах, герой уходит дальше, и на сцене голема прогон уезжает в смену экрана —
статьи двух сборок оказываются посчитаны по РАЗНЫМ сценам (2026-09-04: у одной сборки LoadScreen
внутри окна, «логика» +50 %). Здесь прогрев доводится до заданного НОМЕРА ТИКА, маршрут задан в
тиках, и обе сборки проходят одну и ту же последовательность тиков (что доказывает cmpticks.py).
Строка «фон в слот dtb» обязана совпасть у сравниваемых сборок байт в байт — это признак того,
что сцены действительно одинаковы.

  python3 tools/proftick.py <rom> <lst> <edd> X,Y [прогрев=30]
Маршрут (ROUTE ниже) повторяет measure_vec на сцене голема: 20 тиков влево, 5 на месте, 35 удар+бег.
"""
import sys, os, re, bisect, collections, pathlib
ROM,LST,EDD,ST = sys.argv[1:5]
SETTLE = int(sys.argv[5]) if len(sys.argv)>5 else 30
os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
rv.STEP_BUDGET=400000
t=pathlib.Path(LST).read_text(errors='replace')
syms={}
for line in t.split('\n'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
a=sym['random']; rd=sym['randData']
cpu.mem[a:a+9]=bytes((0x3A,rd&0xFF,rd>>8,0xC6,0x4D,0x32,rd&0xFF,rd>>8,0xC9))
rv.START=tuple(int(v) for v in ST.split(',')); rv._start_done[0]=False
RS=sym['RunScripts']; FC=sym['FrameCounter']
w=rv.Warmup(sym,keys); done=False; ticks=0
for fr in range(1500):
    c=0
    while not cpu.halted and c<rv.STEP_BUDGET:
        pc=cpu.pc
        if not rv._start_done[0] and pc==sym['SaveCheckpoint']:
            cpu.mem[sym['current_levelx']]=rv.START[0]; cpu.mem[sym['current_levely']]=rv.START[1]; rv._start_done[0]=True
        if w.step(pc,fr): done=True
        if pc==RS: ticks+=1; cpu.mem[FC]=ticks&0xFF
        cpu.step(); c+=1
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
    if done: break
assert done
keys.clear()
ROUTE=[(20,['left']),(5,[]),(35,['fire','left'])]      # по тикам, как в measure_vec
NT=sum(n for n,_ in ROUTE)
cnt=collections.Counter(); mem=cpu.mem; tot=0; nf=0; started=False
while ticks < SETTLE+NT:
    while not cpu.halted:
        pc=cpu.pc
        if pc==RS:
            ticks+=1; cpu.mem[FC]=ticks&0xFF
            if ticks>=SETTLE:
                started=True
                k=ticks-SETTLE; acc=0
                for n,ks in ROUTE:
                    acc+=n
                    if k<acc: keys[:] = ks; break
        if started:
            c=CYC[mem[pc]]; cnt[fn(pc)]+=c; tot+=c
        cpu.step()
    cpu.halted=False; nf+=1
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
print(f'ИТОГО {tot} тактов на {NT} тиков ({nf} кадров), тактов на тик {tot/NT:.0f}, кадров на тик {nf/NT:.2f}')
GROUPS=[('фон в слот dtb', ('dtb_loop','drawTile_nosave','dt_a0','dt_rit','drawTile','fgc_','dt_norm','dt_black','dt_blk')),
        ('FG в слот dftb', ('dftb_loop','dft_find','dft_found','dft_rit','drawFGTile','dft_exit')),
        ('прямой в VRAM dt/dft_direct', ('dt_direct','dtd_','dt_end','dft_direct','dft_plane','dft_col','dft_end')),
        ('сброс слотов vb_col/vpf', ('vb_col','vec_blit','vbc_','vpf_')),
        ('раздача слотов vpb', ('vpb_','vec_pool_begin','vec_slot_')),
        ('голем b2p', ('b2p_','b2pm_')),
        ('герой dsp', ('dsp_','dspm_','ds_','dsm_','drawSprite','vss_','vec_spr_')),
        ('обход rit', ('rit_','RedrawInvTiles')),
        ('бюджет/фаза', ('vec_budget','vbg_','vec_phase','vph_','vec_hr','vhr')),
        ('ISR/музыка', ('isr','vec_isr','_at','ply','MUSIC','FX','at_','SPR3','PLY','ps_')),
        ('z80 хелперы', ('z_',))]
g=collections.Counter()
for n,c in cnt.items():
    for gn,pref in GROUPS:
        if n.startswith(pref): g[gn]+=c; break
    else: g['ПРОЧЕЕ (логика)']+=c
for gn,c in g.most_common(): print(f'  {c/NT:8.0f}  {c*100/tot:5.1f}%  {gn}')
print('--- метки ---')
for n,c in cnt.most_common(30): print(f'  {c/NT:8.0f}  {c*100/tot:5.2f}%  {n}')
