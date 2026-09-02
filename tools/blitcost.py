"""Реальная стоимость двухплоскостных блитов (такты Вектора, ед. 256) против цены в бюджете."""
import sys, os, re, pathlib, collections
ST=sys.argv[1]; EDD=sys.argv[2]; os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
B2=sym['vec_blit2']; B2M=sym['vec_slot_tab']; LEAVE=sym['vec_stk_leave']; NY=sym['vec_spr_ny']; COST=sym['vec_spr_colcost']
keys=[]; cpu=rv.make_cpu(keys); rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
mem=cpu.mem; cyc=0; cur=None; stat=collections.defaultdict(list)
keys.append('left')
for _ in range(200):
    if _==100: keys.clear(); keys.append('right')
    while not cpu.halted:
        pc=cpu.pc
        if pc in (B2,B2M) and cur is None: cur=(pc, cyc, mem[NY], mem[COST])
        elif pc==LEAVE and cur is not None:
            kind='прямой' if cur[0]==B2 else 'зеркальный'
            stat[(kind,cur[2])].append(((cyc-cur[1])/256, cur[3])); cur=None
        cyc+=CYC[mem[pc]]; cpu.step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
for (kind,ny),v in sorted(stat.items()):
    real=sorted(x for x,_ in v); price=v[0][1]
    print(f'  {kind:10s} NY={ny:2d}: вызовов {len(v):3d}, реально медиана {real[len(real)//2]:.0f} / p90 {real[int(len(real)*.9)]:.0f} / макс {real[-1]:.0f} ед., в бюджете {price} ед.')
