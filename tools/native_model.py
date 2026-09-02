#!/usr/bin/env python3
"""Модели горячих функций логики на Python — спецификация, снятая с Z80-оригинала (ref/msx2/src),
и гейт: прогон сборки в эмуляторе сверяется с моделью шаг за шагом.

  python3 tools/native_model.py <rom> <lst> <edd> X,Y <тиков> [имя модели ...]

Зачем: нативная i8080-версия пишется не «по мотивам перевода», а по этой модели, и обе сборки —
переведённая и нативная — обязаны ей соответствовать. Сверка сборок между собой (tools/cmpbuild.py)
показывает лишь, что они ведут себя одинаково; модель показывает, что они обе делают то, что
написано в оригинале.

Модели ГСЧ не касаются, поэтому стенд подменяет random так же, как cmpbuild --fixrand.
"""
import sys, os, pathlib

# ---------------------------------------------------------------------------
# DrawSpriteList (ref/msx2/src/drawsprite.asm:314..368)
# Запись SPDATA, 8 байт: +0/+1 адрес кадра, +2 тип (страница ROM в битах 0..6, направление в бите 7),
# +3 X, +4 Y, +5 nchars X, +6 nchars Y, +7 флаг перерисовки.
def model_drawspritelist(spd, max_sprites=16):
    """Что обязан сделать обход списка: список вызовов drawSprite и новое состояние SPDATA."""
    spd = bytearray(spd); calls = []
    for i in range(max_sprites):
        r = spd[i*8:i*8+8]
        if r[7] == 0:                       # ld a,(ix+7) / and a / jp z
            continue
        page = r[2] & 0x7f                  # ld a,(ix+2) / and $7f / call setROM2
        low = (r[6]*8 + r[4]) & 0xFF        # (ix+6)*8 + (ix+4), всё по модулю 256
        ny = 32 if low < 160 else (192 - low) & 0xFF   # cp 160 / sub 160 / neg / add SPRITE_HEIGHT
        spd[i*8+7] = 0                      # ld (ix+7),0 — до вызова drawSprite
        calls.append(dict(page=page, ny=ny, b=r[3], c=r[4],
                          hl=r[0] | (r[1] << 8), a=(r[2] >> 7) & 1))   # rlca / and 1
    return calls, bytes(spd)

MODELS = {'DrawSpriteList': model_drawspritelist}

# ---------------------------------------------------------------------------
def main():
    ROM, LST, EDD, ST = sys.argv[1:5]; N = int(sys.argv[5])
    want = sys.argv[6:] or list(MODELS)
    os.environ['IANNA_EDD'] = EDD
    sys.argv = [sys.argv[0]]; sys.path.insert(0, 'tools')
    import run_vec as rv
    rv.STEP_BUDGET = 400000
    sym = rv.load_syms(pathlib.Path(LST)); keys = []; cpu = rv.make_cpu(keys)
    rom = pathlib.Path(ROM).read_bytes(); cpu.mem[0x100:0x100+len(rom)] = rom; cpu.pc = 0x100
    rv.patch_menu(cpu)
    R = sym['random'] + 5
    assert cpu.mem[R] == 0x3A, 'random: ждём ld a,(FrameCounter)'
    cpu.mem[R:R+3] = b'\xAF\x00\x00'
    rv.START = tuple(int(v) for v in ST.split(',')); rv.start_game(cpu, keys, sym)
    keys.append('right')
    RS = sym['RunScripts']; FC = sym['FrameCounter']; SPD = sym['SPDATA']
    DSL = sym['DrawSpriteList']; DS = sym['drawSprite']; NY = sym['vdpCmdSprite'] + 10
    BANK = sym['vec_sprite_bank']
    ticks = 0; step = cpu.step; mem = cpu.mem
    exp = []; nchecks = [0]; nclip = [0]; bad = []
    while ticks < N:
        while not cpu.halted:
            pc = cpu.pc
            if pc == RS:
                ticks += 1; mem[FC] = ticks & 0xFF
            elif pc == DSL and 'DrawSpriteList' in want:
                exp = model_drawspritelist(bytes(mem[SPD:SPD+128]))[0]
            elif pc == DS and 'DrawSpriteList' in want:
                if not exp:
                    bad.append(f'тик {ticks}: drawSprite вызван, а модель вызовов не ждала')
                else:
                    e = exp.pop(0); nchecks[0] += 1
                    got = dict(page=mem[BANK], ny=mem[NY], b=cpu.b, c=cpu.c,
                               hl=cpu.h << 8 | cpu.l, a=cpu.a)
                    if e['ny'] != 32: nclip[0] += 1
                    if got != e:
                        bad.append(f'тик {ticks}: модель {e} != сборка {got}')
            step()
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
    for b in bad[:10]: print('  РАСХОЖДЕНИЕ', b)
    print(f'  DrawSpriteList: сверено {nchecks[0]} вызовов drawSprite за {N} тиков, '
          f'{"расхождений нет" if not bad else str(len(bad)) + " РАСХОЖДЕНИЙ"}; '
          f'ветка обрезки по Y сработала {nclip[0]} раз')
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
