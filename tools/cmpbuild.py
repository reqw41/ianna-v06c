"""Строгая сверка двух сборок: хэш VRAM и ENTITY_DATA после N игровых тиков при детерминированном стенде.
  python3 tools/cmpbuild.py <rom> <lst> <edd> X,Y <тиков> [--norand]
Одинаковый вывод для двух сборок = эквивалентное поведение (логика + отрисовка). STEP_BUDGET=400000:
обычный кадр не обрывается по числу инструкций (иначе более быстрый код получает прерывание в другой
точке и сборки расходятся без ошибки), а busy-loop сообщения уровня прерывание всё же получает.

--norand: нейтрализовать ГПСЧ. Оригинальный random читает БАЙТ ПАМЯТИ по блуждающему указателю
randData ('ld e,(hl)'), то есть его выход зависит от содержимого кода: ЛЮБАЯ правка, меняющая байты
ROM, сдвигает случайные числа, и сцены с врагами расходятся законно, без ошибки в переводе. С этим
ключом тело random в памяти подменяется на 'A := randData += $4D' — одинаково у обеих сборок, ничего
кроме своей ячейки не читает: расхождение после этого означает именно разную СЕМАНТИКУ. Патч ставится
ДО прогрева — random зовут уже при загрузке уровня, иначе расхождение возникает раньше первого тика."""
import sys, os, pathlib, hashlib
OPTS=[a for a in sys.argv[1:] if a.startswith('--')]
A=[a for a in sys.argv[1:] if not a.startswith('--')]
ROM,LST,EDD,ST,N=A[0],A[1],A[2],A[3],int(A[4]); NORAND='--norand' in OPTS
os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
rv.STEP_BUDGET=400000
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
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step
while ticks<N:
    while not cpu.halted:
        if cpu.pc==RS: ticks+=1; cpu.mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
vram=bytes(cpu.mem[0x8000:0x10000]); ent=bytes(cpu.mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
r=' norand' if NORAND else ''
print(f'  {N} тиков{r}: VRAM {hashlib.md5(vram).hexdigest()[:8]}  ENTITY_DATA {hashlib.md5(ent).hexdigest()[:8]}  {ent[:24].hex()}')
