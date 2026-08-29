#!/usr/bin/env python3
"""
build_vec.py — сборка ianna.rom для Вектор-06Ц.
  1. трансляция модулей MSX2 (Z80 -> i8080) с overrides
  2. нарезка игрового цикла из ianna.asm
  3. переменные vars.asm (музыка урезана)
  4. склейка в build/ianna_vec.asm и zasm --8080 (гейт: только i8080-опкоды)
  5. образ квазидиска (build_edd.py) уже собран отдельно
"""
import subprocess, sys, pathlib, re, os

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'ref/msx2/src'
TR = ROOT / 'build/tr'
VEC = ROOT / 'src/vec'
ZASM = ROOT / 'tools/bin/sjasm'
TRANS = ROOT / 'tools/z80to8080.py'
OVR = ROOT / 'tools/overrides.py'

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r

def translate(src, dst, report=False):
    cmd = [sys.executable, str(TRANS), str(src), str(dst), '--overrides', str(OVR)]
    if report: cmd.append('--report')
    r = run(cmd)
    if r.returncode != 0:
        print(r.stdout, r.stderr); sys.exit(f'трансляция {src} упала')
    if r.stdout.strip():
        print(r.stdout.rstrip())

def slice_ianna():
    src = (SRC / 'ianna.asm').read_text(encoding='utf-8', errors='replace').split('\n')
    def rng(a, b): return src[a-1:b]
    out = []
    out += ['; ---- ianna.asm: game / mainloop (144-239) ----'] + rng(144, 239)
    out += ['; ---- InitVariables..LoadScreen (308-606) ----'] + rng(308, 606)
    out += ['; ---- RedrawScreen / RunScripts / CheckGravities (608-716) ----'] + rng(608, 716)
    out += ['; ---- IndCall / random / Mul8x8 (780-822) ----'] + rng(780, 822)
    out += ['; ---- Div16_8 (840-857) ----'] + rng(840, 857)
    out += ['; ---- таблицы (1006-1079) ----'] + rng(1006, 1079)
    text = '\n'.join(out) + '\n'
    # Вектор: сначала ждём кадр, потом рисуем прямо в экран (нет теневой страницы)
    old = '\tcall RedrawScreen_part1\n\tcall waitforVBlank\n\tcall RedrawScreen_part2\n'
    assert old in text, 'mainloop: не нашёл последовательность part1/wait/part2'
    text = text.replace(old, '\tcall waitforVBlank\t; ВЕКТОР: ждём кадр ДО отрисовки\n\tcall RedrawScreen_part1\n\tcall RedrawScreen_part2\n')
    # random: ld a,r (Z80-only) -> счётчик кадров
    assert 'ld      a,r' in text
    text = text.replace('ld      a,r', 'ld a,(FrameCounter)\t; ВЕКТОР: вместо ld a,r')
    # tilespal: INCBIN "test.plt" -> путь относительно build/
    text = text.replace('INCBIN "test.plt"', 'incbin "../ref/msx2/src/test.plt"')
    (TR / 'ianna_main_src.asm').write_text(text)

def make_vars():
    text = (SRC / 'vars.asm').read_text(encoding='utf-8', errors='replace')
    text = text.replace('music_addr: ds 4096', 'music_addr: ds 2')
    text = text.replace('music_sfx:  ds 1100', 'music_sfx:  ds 2')
    text = text.replace('MUSIC_CODE: ds 2000', 'MUSIC_CODE: ds 2')
    # string_list ссылается на строки меню, которых нет
    text = re.sub(r'string_list: dw string_1, string_2, string_3, string_4_1', 'string_list: dw 0,0,0,0', text)
    text = re.sub(r'string_list_es: dw string_1, string_2, string_3_es, string_4_1', 'string_list_es: dw 0,0,0,0', text)
    (TR / 'vars_src.asm').write_text(text)

def consts_from(path):
    """выдернуть все строки с EQU (константы vdp.asm/sprites.asm)"""
    out = []
    for l in (SRC / path).read_text(encoding='utf-8', errors='replace').split('\n'):
        if re.search(r'\bequ\b', l, re.I) and not l.strip().startswith(';'):
            l = re.sub(r'#([0-9A-Fa-f]+)', r'$\1', l)                      # #f800 -> $f800
            l = re.sub(r'(?<![A-Za-z0-9_$])([01]+)[Bb]\b', r'%\1', l)      # 0101B -> %0101
            out.append(l)
    return '\n'.join(out) + '\n'

def main():
    TR.mkdir(parents=True, exist_ok=True)
    slice_ianna(); make_vars()
    (TR / 'vdp_consts.asm').write_text('; константы из vdp.asm/sprites.asm/music.asm/input.asm\n' + consts_from('vdp.asm') + consts_from('sprites.asm') + consts_from('music.asm') + consts_from('input.asm'))
    for m in ['tiles', 'drawsprite', 'entities', 'scripts', 'objects', 'depack']:
        translate(SRC / f'{m}.asm', TR / f'{m}.asm')
    translate(TR / 'ianna_main_src.asm', TR / 'ianna_main.asm')
    translate(TR / 'vars_src.asm', TR / 'vars.asm')
    order = [VEC / 'vec_boot.asm', TR / 'vdp_consts.asm', TR / 'ianna_main.asm', TR / 'tiles.asm', TR / 'drawsprite.asm',
             TR / 'entities.asm', TR / 'scripts.asm', TR / 'objects.asm', TR / 'depack.asm',
             VEC / 'vec_vdp.asm', VEC / 'vec_isr.asm', VEC / 'vec_stubs.asm', VEC / 'z80rt.asm',
             ROOT / 'build/gen_data.asm', TR / 'vars.asm', VEC / 'vec_vars.asm']
    parts = []
    for f in order:
        parts.append(f'\n; ======== {f.name} ========\n')
        parts.append(f.read_text(encoding='utf-8', errors='replace'))
    (ROOT / 'build/ianna_vec.asm').write_text(''.join(parts))
    r = run([str(ZASM), '--8080', '-uwy', 'ianna_vec.asm', 'ianna_vec.lst', 'ianna.rom'], cwd=ROOT / 'build')
    errs = [l for l in (r.stdout + r.stderr).split('\n') if l.strip()]
    print('\n'.join(errs[-40:]))
    rom = ROOT / 'build/ianna.rom'
    if rom.exists() and r.returncode == 0:
        size = rom.stat().st_size
        print(f'OK: build/ianna.rom {size} Б, конец = ${0x100+size:04X} (граница VRAM $8000)')
        return 0
    return 1

if __name__ == '__main__':
    sys.exit(main())
