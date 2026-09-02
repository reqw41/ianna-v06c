"""Профиль по семействам функций (префикс метки) + что за код ниже первой метки ($0000-$0103)."""
import sys, re, bisect, collections, pathlib, os
ST=sys.argv[1]; EDD=sys.argv[2]; os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
t=pathlib.Path('build/ianna_vec.lst').read_text(errors='replace')
syms={}
for line in t.split('\n'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m and int(m.group(1),16)>=0x100: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '<$0100>'
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=[]; cpu=rv.make_cpu(keys); rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right')
cnt=collections.Counter(); low=collections.Counter(); mem=cpu.mem; tot=0
for _ in range(300):
    while not cpu.halted:
        pc=cpu.pc; c=CYC[mem[pc]]; cnt[fn(pc)]+=c; tot+=c
        if pc<0x100: low[pc]+=c
        cpu.step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
def fam(n):
    if n.startswith(('vec_','vb_','vbg','vpf','vpb','dsp','ds_','dspm','dt_','dtb','dft','b2_','FG','rit_','vm_','drawTile','DrawTile','drawSprite','drawFG','fillArea','drawChar')): return 'вывод (блиттер/пул)'
    if n.startswith('z_'): return 'эмуляция Z80 (z_*)'
    if n.startswith(('isr','vec_isr')): return 'ISR'
    if n.startswith(('_at','ply','MUSIC','FX')): return 'музыка'
    if n.startswith(('vfl','vfr')): return 'таблицы rev256/слоты (ложные метки загрузчика)'
    if n.startswith(('GetHardness','gh_','check_stile','CheckSpr','mos_','Div','Mul')): return 'логика: коллизии/физика'
    if n.startswith(('action_','RunScripts','run_script','script')): return 'логика: скрипты'
    if n.startswith(('entity','Entity','enemy','player','Player','ai_','update_')): return 'логика: сущности'
    if n.startswith(('object','Object','Invalidate','Animate','Redraw','Load','Move','TransferDirty')): return 'логика: объекты/экран'
    return 'логика: прочее'
g=collections.Counter()
for n,c in cnt.items(): g[fam(n)]+=c
print(f'экран {ST}: тактов на тик ~{tot//60:,}')
for k,v in g.most_common(): print(f'  {v*100/tot:5.1f} %  {k}')
print('  горячие метки «логика: прочее»:', [(n,f'{c*100/tot:.1f}%') for n,c in cnt.most_common(60) if fam(n)=='логика: прочее'][:8])
print('  код ниже $0100 (адрес: %):', [(hex(a),f'{c*100/tot:.1f}%') for a,c in low.most_common(5)])
