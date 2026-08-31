#!/usr/bin/env python3
"""
build_vec.py [--demo] — сборка ROM для Вектор-06Ц.
  1. трансляция модулей MSX2 (Z80 -> i8080) с overrides
  2. нарезка игрового цикла из ianna.asm
  3. переменные vars.asm (музыка урезана, string_area по $0200)
  4. склейка в build/ianna[_demo]_vec.asm и zasm --8080 (гейт: только i8080-опкоды)
Раскладка образа: $0100 jp; $0200 vars+vec_vars; [DEMO: $1600 данные]; код.
Результат: build/ianna.rom (квазидиск, + build/ianna.edd) или build/ianna_demo.rom.
"""
import subprocess, sys, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'ref/msx2/src'
TR = ROOT / 'build/tr'
VEC = ROOT / 'src/vec'
ZASM = ROOT / 'tools/bin/sjasm'
TRANS = ROOT / 'tools/z80to8080.py'
OVR = ROOT / 'tools/overrides.py'
DEMO = '--demo' in sys.argv
C8 = '--colors8' in sys.argv        # 8 цветов: 3 плоскости; данные готовит build_edd --colors8
VI53 = '--softbudget' not in sys.argv  # бюджет по счётчику 0 ВИ53 (каналы 1-2 свободны под музыку); --softbudget = старый программный
sys.path.insert(0, str(ROOT / 'tools/data'))
from build_edd import STRING_AREA_KVAZ, STRING_AREA_DEMO, STRING_AREA_C8
VARS_ADDR = STRING_AREA_DEMO if DEMO else (STRING_AREA_C8 if C8 else STRING_AREA_KVAZ)

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def translate(src, dst):
    r = run([sys.executable, str(TRANS), str(src), str(dst), '--overrides', str(OVR)])
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
    out += ['; ---- waitforVBlank (247-306) ----'] + rng(247, 306)
    out += ['; ---- IndCall / random / Mul8x8 / Div8 (780-838) ----'] + rng(780, 838)
    out += ['; ---- Div16_8 (840-857): ВЕКТОР — нативное деление сдвигами вместо цикла вычитаний (до 255 итераций по ~60 тактов) ----',
            '; HL = floor(HL / C), DE и BC целы (оригинал портил B). C = 0 в оригинале недостижим (там ret z с push de на стеке).',
            'Div16_8:', '\tpush de', '\tpush bc', '\tld a,c', '\tor a', '\tjp z,div168_z', '\tld e,c', '\tld b,16', '\txor a\t\t; остаток',
            'div168_l:', '\tadd hl,hl', '\trla', '\tjp c,div168_s\t; остаток >= 256 > C', '\tcp e', '\tjp c,div168_n',
            'div168_s:', '\tsub e', '\tinc l\t\t; бит частного (бит 0 после add hl,hl = 0)',
            'div168_n:', '\tdec b', '\tjp nz,div168_l', 'div168_z:', '\tpop bc', '\tpop de', '\tret']
    out += ['; ---- ENCODE / HEX_TO_TEXT (893-970) ----'] + rng(893, 970)
    out += ['; ---- таблицы (1006-1079) ----'] + rng(1006, 1079)
    text = '\n'.join(out) + '\n'
    # ВЕКТОР: порядок тика — раздача слотов пула (EI) -> ждём кадр -> вывод. Вывод стартует сразу после
    # прерывания (известная фаза кадра), программный бюджет DI (vec_budget) считает от цены ISR.
    old = '\tcall RedrawScreen_part1\n\tcall waitforVBlank\n\tcall RedrawScreen_part2\n'
    assert old in text
    text = text.replace(old, ('' if DEMO else '\tcall vec_pool_begin\t; ВЕКТОР: слоты пула (до ожидания, с EI)\n') +
                        '\tcall waitforVBlank\t; ВЕКТОР: ждём кадр ДО отрисовки\n\tcall RedrawScreen_part1\n\tcall RedrawScreen_part2\n')
    # waitforVBlank выходит только сразу после halt (при тике > 5 кадров иначе вышли бы посреди кадра)
    old = '\tld a, (frames_noredraw)\n    ld hl, frames_lock\n\tcp (hl)\t\t\t; wait until we have spent at least 5 (PÂL) or 6 (NTSC) frames without redrawing\n\tjr nc, vblank_done\n'
    assert old in text, 'waitforVBlank_loop'
    text = text.replace(old, '\tld a, (frames_noredraw)\n    ld hl, frames_lock\n\tcp (hl)\n\tld a, (vec_wait_halted)\t; ВЕКТОР: и выход, и куски панели — только после halt (известная фаза кадра)\n\tjr c, waitforVBlank_vec_score\n\tand a\n\tjr nz, vblank_done\n\tjr waitforvblank_halt_go\nwaitforVBlank_vec_score:\n\tand a\n\tjr z, waitforvblank_halt_go\n')
    old = 'waitforvblank_halt_go:\t\n\thalt\n'
    assert old in text, 'halt_go'
    text = text.replace(old, 'waitforvblank_halt_go:\t\n\thalt\n\tld a, 1\t; ВЕКТОР\n\tld (vec_wait_halted), a\n')
    old = 'waitforVBlank:\n\tpush af\n'
    assert old in text, 'waitforVBlank entry'
    text = text.replace(old, 'waitforVBlank:\n\tpush af\n\txor a\t; ВЕКТОР\n\tld (vec_wait_halted), a\n')
    if not DEMO:
        # буферный рендер: part1 собирает в пул, part2 выбрасывает в VRAM; полный RedrawScreen (смена экрана)
        # синхронизируется с кадром сам (halt)
        old = 'RedrawScreen:\n\tcall RedrawInvTiles'
        assert old in text; text = text.replace(old, 'RedrawScreen:\n\tcall vec_pool_begin\t; ВЕКТОР: слоты пула\n\thalt\t\t; ВЕКТОР: к началу кадра — бюджет DI считает от прерывания\n\tcall RedrawInvTiles')
        old = '\tcall TransferDirtyTiles\t; Transfer dirty tiles to main screen'
        assert old in text; text = text.replace(old, '\tcall vec_pool_flush\t; ВЕКТОР: пул -> VRAM сверху вниз')
    assert 'ld      a,r' in text
    text = text.replace('ld      a,r', 'ld a,(FrameCounter)\t; ВЕКТОР: вместо ld a,r')
    text = re.sub(r'^blackpal: db 0.*\n\s+db 0.*\n', 'blackpal:\n', text, flags=re.M)
    text = text.replace('tilespal:  INCBIN "test.plt"', 'tilespal:\t; палитра Вектора — vec_palette')
    if DEMO:
        i = text.index('enemy_info:'); j = text.index('enemy_info_demon:')
        j = text.index('\n', text.index('DB', text.index('DB', text.index('DB', text.index('DB', text.index('DB', j)+1)+1)+1)+1))  # конец 5 строк demon
        text = text[:i] + 'enemy_info:\t; ДЕМО: таблиц врагов нет\n' + text[j+1:]
        old = 'LEVEL_OFFSET: dw $8000, $8000'
        assert old in text
        text = text.replace(old, 'LEVEL_OFFSET: dw DEMO_LEVEL_ADDR, $8000')
    (TR / 'ianna_main_src.asm').write_text(text)

def make_score_font():
    sc = (SRC / 'score.asm').read_text(encoding='utf-8', errors='replace')
    sc = sc.replace('scorearea: INCBIN "marcador.SR5.plet1"', 'scorearea:')
    sc = sc.replace('WEAPON_SPRITES: INCBIN "armas.SR5.plet1"', 'WEAPON_SPRITES:')
    old = 'load_scorearea:\n\tld hl, scorearea\n\tld de, $D000\n\tcall unpackVRAM'
    assert old in sc; sc = sc.replace(old, 'load_scorearea:\n\tcall vec_load_panel\t; ВЕКТОР: картинка панели из квазидиска')
    if DEMO:
        # в демо панели нет: все процедуры score остаются, но рисуют в пустоту (drawChar и пр. — ret)
        pass
    (TR / 'score_src.asm').write_text(sc)
    ft = (SRC / 'font.asm').read_text(encoding='utf-8', errors='replace')
    (TR / 'font_src.asm').write_text(ft)

def make_music():
    mu = (SRC / 'music.asm').read_text(encoding='utf-8', errors='replace')
    mu = mu.replace('INCLUDE "music_sfx.sym"', '; ВЕКТОР: песни лежат в странице 3 квазидиска (окно $A000-$DFFF, адреса как на MSX), эффекты по $D980\nMUSIC_WIN\tequ $C980\nSFX_WIN\tequ $D980\n'
                    + '\n'.join(f'{n}\tequ MUSIC_WIN' for n in ['music0','music1','music3','music4','music5','music6','music7','music8','music_gameover','music_intro','music_menu','music_end','music_credits']))
    old = '''\tex de, hl
\tld de, music_addr\t\t
\tcall depack
\tld hl, SFX_ADDR
\tld de, music_sfx
\tcall depack
\tld de, music_addr
\tcall atInit
\tld de, music_sfx
\tcall atSfxInit'''
    assert old in mu, 'music.asm: не нашёл блок depack'
    mu = mu.replace(old, '''\tex de, hl\t\t; HL = адрес песни (в окне)
\tex de, hl
\tcall atInit\t\t; ВЕКТОР: без распаковки — песня уже в квазидиске
\tld de, SFX_WIN
\tcall atSfxInit''')
    mu = mu.replace('atInit: equ MUSIC_CODE\natPlay: equ MUSIC_CODE + 3\natStop: equ MUSIC_CODE + 6\natSfxInit: equ MUSIC_CODE + 9\natSfxPlay: equ MUSIC_CODE + 12\natSfxStop: equ MUSIC_CODE + 15',
                    '; ВЕКТОР: плеер ассемблируется на месте, точки входа — его метки (atInit/atPlay/atStop/atSfxInit/atSfxPlay/atSfxStopAll)')
    mu = mu.replace('\tcall atSfxStop\n', '\tcall atSfxStopAll\n')
    # ВЕКТОР: данные эффектов лежат в окне квазидиска ($D980, страница 3); atSfxPlay читает оттуда таблицу
    # инструментов — из игровой логики окно закрыто, поэтому открыть на время вызова и вернуть прежнюю страницу
    # (через setROM2, чтобы тень окна для ISR была согласована).
    m = re.search(r'\n(\tld l, a[^\n]*; effect\n)', mu); assert m, 'FX_Play: ld l,a'
    mu = mu[:m.start(1)] + '\tld l, a\t\t\t; ВЕКТОР: окно квазидиска на страницу музыки/эффектов\n\tld a, (ROMBank1)\n\tpush af\n\tld a, MUSIC_ROM_PAGE\n\tcall setROM2\n\tld a, l\n' + mu[m.start(1):]
    old2 = '\tld bc, 0\n\tcall atSfxPlay\n'; assert mu.count(old2) == 1, 'FX_Play: call atSfxPlay'
    mu = mu.replace(old2, '\tld bc, 0\n\tcall atSfxPlay\n\tpop af\t\t\t; ВЕКТОР: вернуть прежнюю страницу окна\n\tcall setROM2\n')
    (TR / 'music_src.asm').write_text(mu)
    pl = (SRC / 'ArkosTrackerPlayer_CPC_MSX.asm').read_text(encoding='utf-8', errors='replace')
    pl = pl.replace('org $DDCC', '; ВЕКТОР: org снят — плеер на месте в коде')
    pl = pl.replace('out (#a0),a', 'out ($15),a\t; AY Вектора: выбор регистра').replace('out (#a1),a', 'out ($14),a\t; AY Вектора: данные')
    assert 'out (#a' not in pl
    # ВЕКТОР: горячая часть плеера (Play Sound по каналам + _atPlaySound) — нативный i8080 (src/vec/arkos_hot.asm)
    hot = (VEC / 'arkos_hot.asm').read_text(encoding='utf-8')
    hot1, hot2 = hot.split(';;;SPLIT;;;\n')
    L = pl.split('\n')
    def find(pred, start=0):
        for i in range(start, len(L)):
            if pred(L[i]): return i
        raise SystemExit('arkos: маркер не найден')
    a = find(lambda l: 'Play Sound on Track 3' in l)
    b = find(lambda l: 'Update AY3 Registers (platform specific)' in l, a)
    c = find(lambda l: l.startswith('_atPlaySound'), b)
    d = find(lambda l: '; Read Track.' in l, c)
    assert 'atCNF_SFX\tequ 1' in pl
    pl = '\n'.join(L[:a] + hot1.split('\n') + L[b:c] + hot2.split('\n') + L[d:])
    (TR / 'arkos_src.asm').write_text(pl)

def make_vars():
    text = (SRC / 'vars.asm').read_text(encoding='utf-8', errors='replace')
    text = text.replace('music_addr: ds 4096', 'music_addr: ds 2')
    text = text.replace('music_sfx:  ds 1100', 'music_sfx:  ds 2')
    text = text.replace('MUSIC_CODE: ds 2000', 'MUSIC_CODE: ds 2')
    # string_area: как в оригинале 2048 (уровень 7 — 1994 Б; с 1536 уровень 2 затирал OBJECT_DATA); OBJECT_DATA на границе страницы
    if DEMO: text = text.replace('string_area: ds 2048', 'string_area: ds 512')
    # неиспользуемые буферы VDP-команд (кроме vdpCmdSprite: там NY для drawSprite) и палитры
    text = re.sub(r'^(tileDat|fgtileDat|dirtyTileDat|cmdDat|charDat|charDat2|charDat3|fillDat|vdpCmdWeapon|lineMoveDat|vdpCopyDat|scoreDat): ds 15', r'\1: ds 0', text, flags=re.M)
    text = text.replace('currentPal: ds 32', 'currentPal: ds 0')
    text = re.sub(r'string_list: dw string_1, string_2, string_3, string_4_1', 'string_list: dw 0,0,0,0', text)
    text = re.sub(r'string_list_es: dw string_1, string_2, string_3_es, string_4_1', 'string_list_es: dw 0,0,0,0', text)
    text = f'\torg ${VARS_ADDR:04X}\t; vars наверху ОЗУ; string_area = ${VARS_ADDR:04X} (указатели скриптов уровня перенесены сюда)\n' + text
    (TR / 'vars_src.asm').write_text(text)

def consts_from(path):
    out = []
    for l in (SRC / path).read_text(encoding='utf-8', errors='replace').split('\n'):
        if re.search(r'\bequ\b', l, re.I) and not l.strip().startswith(';') and 'MUSIC_CODE' not in l:
            l = re.sub(r'#([0-9A-Fa-f]+)', r'$\1', l)
            l = re.sub(r'(?<![A-Za-z0-9_$])([01]+)[Bb]\b', r'%\1', l)
            out.append(l)
    return '\n'.join(out) + '\n'

def main():
    TR.mkdir(parents=True, exist_ok=True)
    slice_ianna(); make_vars(); make_score_font(); make_music()
    (TR / 'vdp_consts.asm').write_text('; константы из vdp.asm/sprites.asm/music.asm/input.asm\n' + f'C8\tequ {1 if C8 else 0}\t; 8 цветов (3 плоскости)\nVI53\tequ {1 if VI53 else 0}\t; бюджет по счётчику 0 ВИ53\n' + consts_from('vdp.asm') + consts_from('sprites.asm') + consts_from('music.asm') + consts_from('input.asm'))
    # ВЕКТОР: цепочка пересечений спрайтов — нативно (src/vec/overlap_hot.asm) вместо перевода
    hot = (VEC / 'overlap_hot.asm').read_text(encoding='utf-8'); hot_t, hot_d = hot.split(';;;SPLIT;;;\n')
    def cut(text, start_pred, end_pred, repl):
        L = text.split('\n'); a = next(i for i, l in enumerate(L) if start_pred(l)); b = next(i for i in range(a + 1, len(L)) if end_pred(L[i]))
        return '\n'.join(L[:a] + repl.split('\n') + L[b:])
    t = (SRC / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    t = cut(t, lambda l: l.startswith('AnimStile_CheckSprites:'), lambda l: 'Get the value for the tile in the hardness map' in l, hot_t)
    t = cut(t, lambda l: l.startswith('AnimateSTiles:'), lambda l: '; Update a supertile on screen' in l, '; ВЕКТОР: AnimateSTiles — нативно (overlap_hot.asm)')
    inner = ('dirtyrectloop','dirty_y_loop','dirty_x_loop','RedrawInvTiles_FG','dirtyrectloop_fg','dirty_y_loop_fg','dirty_x_loop_fg')
    t = cut(t, lambda l: l.startswith('RedrawInvTiles:'), lambda l: re.match(r'^[A-Za-z_]\w*:', l) and not l.split(':')[0] in inner, '; ВЕКТОР: RedrawInvTiles/RedrawInvTiles_FG — нативно (overlap_hot.asm)')
    (TR / 'tiles_src.asm').write_text(t)
    d = (SRC / 'drawsprite.asm').read_text(encoding='utf-8', errors='replace')
    d = cut(d, lambda l: l.startswith('CheckSprOverlap:'), lambda l: l.startswith('; Redraw the sprite list'), hot_d)
    (TR / 'drawsprite_src.asm').write_text(d)
    translate(TR / 'tiles_src.asm', TR / 'tiles.asm')
    translate(TR / 'drawsprite_src.asm', TR / 'drawsprite.asm')
    for m in ['entities', 'scripts', 'objects', 'depack']:
        translate(SRC / f'{m}.asm', TR / f'{m}.asm')
    # ряды панели (>= 10) DrawTile/DrawFGTile никогда не рисуют (cp 11 / ret nc) — не копить
    # пустые прямоугольники: каждый стоил обход 16x2 тайлов с двумя z_exx на тайл
    t = (TR / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    if C8:
        assert t.count('DrawScreen:\n') == 1
        t = t.replace('DrawScreen:\n', 'DrawScreen:\n\tcall vec_scr_palette\t; ВЕКТОР C8: палитра экрана\n')
    old = 'InvalidateSTiles:\n\tpush de'
    assert old in t
    (TR / 'tiles.asm').write_text(t.replace(old, 'InvalidateSTiles:\n\tld a,c\t; ВЕКТОР: ряды панели не рисуются — прямоугольник не нужен\n\tcp 10\n\tret nc\n\tpush de'))
    # накладные обхода грязных тайлов в RedrawInvTiles_FG (z_exx x2 на тайл, EI) — зарядить в бюджет DI
    t = (TR / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    old = 'DrawFGTile:\n'
    assert t.count(old) == 1
    (TR / 'tiles.asm').write_text(t.replace(old, 'DrawFGTile:\n\tpush af\t; ВЕКТОР: накладные обхода — в бюджет DI\n\tld a,3-C8\t; обход FG: 16ц медиана 2.1/p90 2.6; c8 2.1 -> 2\n\tcall vec_budget\n\tpop af\n'))
    translate(TR / 'ianna_main_src.asm', TR / 'ianna_main.asm')
    translate(TR / 'score_src.asm', TR / 'score.asm')
    translate(TR / 'font_src.asm', TR / 'font.asm')
    if not DEMO:
        translate(TR / 'music_src.asm', TR / 'music.asm')
        translate(TR / 'arkos_src.asm', TR / 'arkos.asm')
    translate(TR / 'vars_src.asm', TR / 'vars.asm')
    data = ROOT / ('build/demo_data.asm' if DEMO else 'build/gen_data.asm')
    order = [VEC / 'vec_boot.asm', TR / 'vdp_consts.asm']
    if DEMO:
        order.append(data)              # org $0200
    order += [VEC / 'vec_main.asm', TR / 'ianna_main.asm', TR / 'tiles.asm', TR / 'drawsprite.asm',
              TR / 'entities.asm', TR / 'scripts.asm', TR / 'objects.asm', TR / 'depack.asm',
              TR / 'score.asm', TR / 'font.asm'] + ([TR / 'music.asm', TR / 'arkos.asm'] if not DEMO else []) + [
              VEC / 'vec_vdp.asm', VEC / 'vec_isr.asm'] + ([VEC / 'vec_fdd.asm'] if C8 else []) + [VEC / 'vec_stubs.asm']
    if not DEMO:
        order.append(data)
    # z80rt: только используемые хелперы
    used = set()
    for f in order:
        if f.suffix == '.asm':
            used |= set(re.findall(r'\bcall\s+(z_\w+)', f.read_text(encoding='utf-8', errors='replace')))
    rt = (VEC / 'z80rt.asm').read_text(encoding='utf-8', errors='replace')
    blocks = re.split(r'(?m)^(?=z_\w+:)', rt)
    keep = [blocks[0]]; kept = set()
    for b in blocks[1:]:
        name = re.match(r'z_\w+', b).group(0)
        parent = next((k for k in kept if name.startswith(k + '_')), None)   # подметка (z_ldir_l) идёт с родителем
        if name in used or parent:
            keep.append(b); kept.add(name)
    (TR / 'z80rt_used.asm').write_text(''.join(keep))
    order.append(TR / 'z80rt_used.asm')
    order += [TR / 'vars.asm', VEC / 'vec_vars.asm']   # org VARS_ADDR
    parts = [f'DEMO\tequ {1 if DEMO else 0}\n']
    for f in order:
        parts.append(f'\n; ======== {f.name} ========\n')
        parts.append(f.read_text(encoding='utf-8', errors='replace'))
    name = 'ianna_demo' if DEMO else 'ianna'
    (ROOT / f'build/{name}_vec.asm').write_text(''.join(parts))
    r = run([str(ZASM), '--8080', '-uwy', f'{name}_vec.asm', f'{name}_vec.lst', f'{name}.rom'], cwd=ROOT / 'build')
    errs = [l for l in (r.stdout + r.stderr).split('\n') if l.strip()]
    print('\n'.join(errs[-40:]))
    rom = ROOT / f'build/{name}.rom'
    if rom.exists() and r.returncode == 0:
        size = rom.stat().st_size
        if size + 0x100 > 0x8000:
            print(f'ПЕРЕПОЛНЕНИЕ: конец образа ${0x100+size:04X} > $8000'); return 1
        lst = (ROOT / f'build/{name}_vec.lst').read_text(errors='replace')
        m = re.search(r'^string_area\s+=\s+\$([0-9A-F]{4})', lst, re.M)
        assert m and int(m.group(1), 16) == VARS_ADDR, 'string_area не по VARS_ADDR!'
        # конец кода: максимальный адрес байтовой строки ДО org vars (наезд на vars sjasm молчит!)
        code_end = 0
        for line in lst.split('\n'):
            if 'vars наверху ОЗУ' in line: break
            mm = re.match(r'^([0-9A-F]{4}): [0-9A-F]{2}', line)
            if mm: code_end = max(code_end, int(mm.group(1), 16))
        assert code_end < VARS_ADDR, f'код до ${code_end:04X} НАЕХАЛ на переменные ${VARS_ADDR:04X}'
        print(f'код до ${code_end:04X}, переменные с ${VARS_ADDR:04X} (зазор {VARS_ADDR-code_end-1} Б)')
        m = re.search(r'^OBJECT_DATA\s+=\s+\$([0-9A-F]{4})', lst, re.M)
        assert m and int(m.group(1), 16) & 0xFF == 0, 'OBJECT_DATA не выровнена на страницу!'
        print(f'OK: build/{name}.rom {size} Б, конец = ${0x100+size:04X} (граница VRAM $8000, свободно {0x8000-0x100-size} Б)')
        if not DEMO:
            build_menu_bins(lst)
        return 0
    return 1

def build_menu_bins(lst):
    """Оверлей меню и RAM-блоб: собираются отдельно с импортом символов игры из .lst."""
    need = ['drawChar', 'fillArea', 'MUSIC_Load', 'language', 'joystick_state', 'music_playing',
            'vec_kv_shadow', 'string_area', 'vec_pal_dirty', 'current_level', 'cls']
    syms = {}
    for line in lst.split('\n'):
        m = re.match(r'^([A-Za-z_][\w.]*)\s+=\s+\$([0-9A-F]{4})', line)
        if m and m.group(1) in need:
            syms[m.group(1)] = int(m.group(2), 16)
    missing = [n for n in need if n not in syms]
    assert not missing, f'нет символов для меню: {missing}'
    out = ['; сгенерировано build_vec (символы игры для оверлея меню)']
    for n, v in syms.items():
        out.append(f'{n}\tequ ${v:04X}')
    out += [f'MB_ORG\tequ ${syms["string_area"]:04X}', 'MB_TRK_MENU\tequ 40', 'MB_TRK_SLIDES\tequ 44']
    (ROOT / 'build/menu_syms.asm').write_text('\n'.join(out) + '\n')
    sys.path.insert(0, str(ROOT / 'tools/data'))
    from texts_ru import encode, MENU, INTRO
    def db(label, text): return f"{label}:\tdb " + ','.join(str(b) for b in encode(text)) + ',0'
    ru = ['; сгенерировано build_vec из tools/data/texts_ru.py (кодировка шрифта: кириллица 96..127)',
          db('o_play_es', MENU['play']), db('o_pass_es', MENU['pass']), db('o_esp', MENU['lang']), db('o_mus_es', MENU['music']),
          db('t1s', INTRO[0]), db('t2s', INTRO[1]), db('t3s', INTRO[2])]
    (ROOT / 'build/menu_ru.asm').write_text('\n'.join(ru) + '\n')
    for src, binout, maxlen in ((VEC / 'menu_ram.asm', 'menu_ram.bin', 0x400),
                                (VEC / 'menu_ovl.asm', 'menu_ovl.bin', 0x9C00 - 0x8440)):
        work = ROOT / f'build/{src.name}'
        work.write_text(src.read_text())
        r = subprocess.run([str(ZASM), '--8080', '-uwy', work.name, f'{binout}.lst', binout],
                           capture_output=True, text=True, cwd=str(ROOT / 'build'))
        if r.returncode != 0:
            print(f'МЕНЮ: ошибка сборки {src.name}:'); print((r.stdout + r.stderr)[-1200:]); sys.exit(1)
        blen = (ROOT / f'build/{binout}').stat().st_size
        assert blen <= maxlen, f'{binout}: {blen} > {maxlen}'
        print(f'меню: {binout} {blen} Б (лимит {maxlen})')

if __name__ == '__main__':
    sys.exit(main())
