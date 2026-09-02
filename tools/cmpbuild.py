"""Строгая сверка двух сборок: хэш VRAM и ENTITY_DATA после N игровых тиков при детерминированном стенде.
  python3 tools/cmpbuild.py <rom> <lst> <edd> X,Y <тиков>
Одинаковый вывод для двух сборок = эквивалентное поведение (логика + отрисовка). STEP_BUDGET=400000:
обычный кадр не обрывается по числу инструкций (иначе более быстрый код получает прерывание в другой
точке и сборки расходятся без ошибки), а busy-loop сообщения уровня прерывание всё же получает."""
import sys, os, pathlib, hashlib
ROM=sys.argv[1]; LST=sys.argv[2]; EDD=sys.argv[3]; ST=sys.argv[4]; N=int(sys.argv[5]); os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
rv.STEP_BUDGET=400000
sym=rv.load_syms(pathlib.Path(LST))
keys=[]; cpu=rv.make_cpu(keys)
rom=pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100; rv.patch_menu(cpu)
rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
keys.append('right'); RS=sym['RunScripts']; FC=sym['FrameCounter']; ticks=0; step=cpu.step
while ticks<N:
    while not cpu.halted:
        if cpu.pc==RS: ticks+=1; cpu.mem[FC]=ticks&0xFF
        step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
vram=bytes(cpu.mem[0x8000:0x10000]); ent=bytes(cpu.mem[sym['ENTITY_DATA']:sym['ENTITY_DATA']+96])
print(f'  {N} тиков: VRAM {hashlib.md5(vram).hexdigest()[:8]}  ENTITY_DATA {hashlib.md5(ent).hexdigest()[:8]}  {ent[:24].hex()}')
