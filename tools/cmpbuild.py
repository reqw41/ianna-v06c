"""Строгая сверка двух сборок: хэш VRAM и ENTITY_DATA после N игровых тиков при детерминированном стенде.
  python3 tools/cmpbuild.py <rom> <lst> <edd> X,Y <тиков> [--fixrand]
Одинаковый вывод для двух сборок = эквивалентное поведение (логика + отрисовка). STEP_BUDGET=400000:
обычный кадр не обрывается по числу инструкций (иначе более быстрый код получает прерывание в другой
точке и сборки расходятся без ошибки), а busy-loop сообщения уровня прерывание всё же получает.

--fixrand отвязывает ГСЧ от скорости кода. Оригинал берёт энтропию из `ld a,r`, перевод — из
`ld a,(FrameCounter)`, а FrameCounter растёт по прерываниям ВНУТРИ тика: сколько их успеет прийти
до вызова random, зависит от того, насколько быстр код. Поэтому на экранах с бойцами (уровни 2 и 3)
сверка без --fixrand ловит не логику, а тайминг: четыре безобидных nop в холостом обходе списка
спрайтов уже дают другие хэши, хотя ни одна ветка логики не тронута. С флагом три байта
`ld a,(FrameCounter)` в random заменены на `xor a` + два nop: последовательность остаётся
псевдослучайной (её ведёт randData) и одинаковой для обеих сборок при любой их скорости.
Сверять ускоряющую правку следует ОБОИМИ способами: без флага — что не изменился темп (сцены без
бойцов), с флагом — что не изменилась логика."""
import sys, os, pathlib, hashlib
A=[a for a in sys.argv[1:] if not a.startswith('--')]; FIXRAND='--fixrand' in sys.argv
ROM=A[0]; LST=A[1]; EDD=A[2]; ST=A[3]; N=int(A[4]); os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
rv.STEP_BUDGET=400000
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
if FIXRAND:
    R=sym['random']+5   # push hl / push de / ld hl,(randData) / ld a,(FrameCounter)
    assert cpu.mem[R]==0x3A and cpu.mem[R+1]|(cpu.mem[R+2]<<8)==sym['FrameCounter'], 'random: ждём ld a,(FrameCounter)'
    cpu.mem[R:R+3]=b'\xAF\x00\x00'
rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step
while ticks<N:
    while not cpu.halted:
        if cpu.pc==RS: ticks+=1; cpu.mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
vram=bytes(cpu.mem[0x8000:0x10000]); ent=bytes(cpu.mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
print(f'  {N} тиков{" (ГСЧ фикс.)" if FIXRAND else ""}: VRAM {hashlib.md5(vram).hexdigest()[:8]}  '
      f'ENTITY_DATA {hashlib.md5(ent).hexdigest()[:8]}  {ent[:24].hex()}')
