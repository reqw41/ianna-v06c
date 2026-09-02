#!/usr/bin/env python3
"""Дискетная сборка headless: пустой квазидиск + образ дискеты (эмуляция ВГ93 в run_vec).
Проверяет, что загрузчик читает набор с дискеты, ставит маркер и игра стартует; с --next
дополнительно проверяет ПЕРЕХОД НА СЛЕДУЮЩИЙ УРОВЕНЬ (player_dead=3, как в скрипте finish_level).
  python3 tools/fdd_boot_test.py [--next]
Без этого теста дискетная ветка проверялась только руками в эмуляторе."""
import sys, pathlib, os
NEXT='--next' in sys.argv
os.environ.setdefault('IANNA_EDD','/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/empty.edd')
os.environ.setdefault('IANNA_FDD','build/ianna.fdd')
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=[]; cpu=rv.make_cpu(keys)
print('маркер до старта:', bytes(cpu.kvaz[3*65536+0xC800:3*65536+0xC802]))
rv.start_game(cpu, keys, sym)
print('игра стартовала; маркер:', bytes(cpu.kvaz[3*65536+0xC800:3*65536+0xC802]),
      '| уровень', cpu.mem[sym['current_level']])
edd1=pathlib.Path('build/ianna.edd').read_bytes()
same=sum(1 for i in range(0x8000) if cpu.kvaz[i]==edd1[i])
print(f'квазидиск против набора уровня 1: {same*100//0x8000} % совпадения на первых 32 КБ')
if NEXT:
    rv.run_frames(cpu, 30, sym=sym)
    cpu.mem[sym['current_level']] = 1        # скрипт finish_level уже увеличил бы номер
    cpu.mem[sym['player_dead']] = 3
    print('запрошен переход на уровень 2...')
    reads=[0]; base=cpu.out_handler
    def out(pt,v):
        if pt==0x1B and v==0x80: reads[0]+=1
        return base(pt,v)
    cpu.out_handler=out
    rv.run_frames(cpu, 2500, sym=sym)
    print('секторов прочитано при переходе:', reads[0])
    print('после перехода: уровень', cpu.mem[sym['current_level']],
          '| player_dead', cpu.mem[sym['player_dead']], f'| pc=${cpu.pc:04X}')
    pal=bytes(cpu.mem[sym['vec_palette']:sym['vec_palette']+16])
    print('палитра в ОЗУ:', pal.hex())
    print('палитра в наборе (квазидиск):', bytes(cpu.kvaz[2*65536+0xBC40:2*65536+0xBC40+16]).hex())
    rv.render(bytes(cpu.mem[0x8000:0x10000]), list(pal),
              '/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/level2.png')
    print('снимок: scratchpad/level2.png')
    pathlib.Path('/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/kvaz_after.bin').write_bytes(bytes(cpu.kvaz[:262144]))
    print('дамп квазидиска сохранён')
