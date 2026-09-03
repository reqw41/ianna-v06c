#!/usr/bin/env python3
"""A/B-замер тактов на детерминированном стенде (как cmpbuild): N игровых
тиков, траектория обязана совпасть у обеих сборок — тогда сравнение тактов
честное. Печатает всего тактов, такты в хелперах z_*, хэши VRAM/ENTITY_DATA.

ГПСЧ нейтрализуется (как в cmpbuild --norand): оригинальный random читает
байт памяти по блуждающему указателю randData ('ld e,(hl)'), поэтому любая
правка кода сдвигает случайные числа и траектории расходятся законно.
  python3 tools/abcyc.py <rom> <lst> <edd> X,Y <тиков> [--rand]"""
import sys, os, re, bisect, pathlib, hashlib, collections
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST,N=A[0],A[1],A[2],A[3],int(A[4])
NORAND='--rand' not in OPTS
os.environ['IANNA_EDD']=EDD
if 'demo' in pathlib.Path(ROM).name:
    sys.exit('ОТКАЗ: демо-ROM не применяет стартовый экран X,Y и не несёт врагов — все «сцены» на нём одна и та же '
             'пустая сцена (найдено 2026-09-03). Сверять только build/ianna.rom + build/ianna_vec.lst + набор того же коммита.')
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
src=open('tools/profile_vec.py').read(); i=src.index('# Такты ВЕКТОРА'); j=src.index('keys = []'); exec(src[i:j])
rv.STEP_BUDGET=400000
syms={}
for line in open(LST,encoding='utf-8',errors='replace'):
    m=re.match(r'([0-9A-F]{4}):\s.*?\s([A-Za-z_][A-Za-z_0-9.]*):',line)
    if m: syms.setdefault(int(m.group(1),16),m.group(2))
addrs=sorted(syms); names=[syms[a] for a in addrs]
def fn(pc):
    k=bisect.bisect_right(addrs,pc)-1; return names[k] if k>=0 else '?'
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
def norand_patch(cpu, sym):
    """ГПСЧ игры читает БАЙТ ПАМЯТИ по блуждающему указателю randData ('ld e,(hl)'),
    то есть его выход зависит от СОДЕРЖИМОГО кода: любая правка байтов ROM сдвигает
    случайные числа, и сцены с врагами расходятся законно, без ошибки в переводе.
    Здесь тело random в памяти заменяется на 'A := randData += $4D' (период 256, ничего
    кроме своей ячейки не читает) — одинаково у любых сборок. Патч ставится ДО прогрева:
    random зовут уже при загрузке уровня."""
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a+9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
if NORAND: norand_patch(cpu,sym)
rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step; mem=cpu.mem
tot=0; cnt=collections.Counter()
while ticks<N:
    while not cpu.halted:
        pc=cpu.pc; w=CYC[mem[pc]]; tot+=w; cnt[fn(pc)]+=w
        if pc==RS: ticks+=1; mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
z=sum(v for k,v in cnt.items() if k.startswith('z_'))
vram=bytes(mem[0x8000:0x10000]); ent=bytes(mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
print(f'{N} тиков: всего {tot} тактов, на тик {tot/N:.0f}; z_* {z} ({z/tot*100:.2f}%); VRAM {hashlib.md5(vram).hexdigest()[:8]} ENT {hashlib.md5(ent).hexdigest()[:8]}')
