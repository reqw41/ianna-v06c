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
import subprocess, sys, pathlib, re, os

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import disk_layout as DL   # раскладка дискеты (дорожки меню и слайдов)
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'ref/msx2/src'
TR = ROOT / 'build/tr'
VEC = ROOT / 'src/vec'
ZASM = ROOT / 'tools/bin/sjasm'
TRANS = ROOT / 'tools/z80to8080.py'
OVR = ROOT / 'tools/overrides.py'
DEMO = '--demo' in sys.argv
C8 = '--colors8' in sys.argv        # 8 цветов: 3 плоскости; данные готовит build_edd --colors8
SPR3 = os.environ.get('IANNA_SPR3') == '1'
SPR3CLR = os.environ.get('IANNA_SPR3CLR') == '1'
NOMIRROR = os.environ.get('IANNA_NOMIRROR') == '1'  # замер: зеркальные спрайты рисуются прямым путём  # плоскость 3 у спрайтов только чистится (законный вариант для 3-плоскостного спрайта)   # верхняя оценка выигрыша от отказа от 4-й плоскости у спрайтов
# Плеер Arkos в стр.3 квазидиска. Код — $C000-$C7FF (хвост прежнего пула), таблицы периодов и состояние —
# $DE00-$DFFF (за эффектами). В $A000-$BFFF плееру нельзя: фаза меню читает туда сжатую картинку с дискеты
# (menu_ram MB_PICBUF, 8 КБ) — первая раскладка ($BD00) затиралась, и MUSIC_Stop из меню уходил в пустоту.
# Код начинается с $C010, а не с $C000: читатель сектора в меню (mb_read, «трюк ПЗУ» без счётчика байтов)
# кладёт один лишний байт сразу за буфером — ровно в $C000.
ARK_ADDR, ARK_END = 0xC010, 0xC800
ARK_DAT, ARK_DAT_END = 0xDE00, 0xE000
VI53 = '--softbudget' not in sys.argv  # бюджет по счётчику 0 ВИ53 (каналы 1-2 свободны под музыку); --softbudget = старый программный
sys.path.insert(0, str(ROOT / 'tools/data'))
from build_edd import STRING_AREA_KVAZ, STRING_AREA_DEMO, STRING_AREA_C8
VARS_ADDR = STRING_AREA_DEMO if DEMO else (STRING_AREA_C8 if C8 else STRING_AREA_KVAZ)
from build_edd import CREDITS_ADDR       # блоб титров в странице 3 квазидиска (см. build_edd)
from build_edd import PAUSE_ADDR, PAUSE_END, FDD_BANKCODE, FDD_BANKCODE_END, WPN_SRC, WPN_SRC_END

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
    # РУССКОЕ ИЗДАНИЕ: язык один, второй ветки в LoadLevel нет. Число строк сохраняем —
    # ключи overrides для ianna_main_src.asm заданы номерами строк, а правки лежат выше них.
    old = ('\tld a, (ix+8)\n\tld l, a\n\tld a, (ix+9)\n\tld h, a\t\n\tld (level_string_en_addr), hl\n')
    assert old in text, 'LoadLevel: чтение ix+8/ix+9'
    text = text.replace(old, '; РУССКОЕ ИЗДАНИЕ: hdr[8..9] (адрес английского блока) не читается —\n'
                             '; build_edd кладёт в набор один блок строк, и hdr[10..11] ведут на него.\n;\n;\n;\n')
    old = ('\tld a, (language)\n\tand a\n\tjr nz, load_strings_en\n\tld hl, (level_string_addr)\n'
           '\tjr load_strings_common\nload_strings_en:\n\tld hl, (level_string_en_addr)\nload_strings_common:\n')
    assert old in text, 'LoadLevel: ветка по language'
    text = text.replace(old, '\tld hl, (level_string_addr)\t; РУССКОЕ ИЗДАНИЕ: язык один\n;\n;\n;\n;\n;\n;\nload_strings_common:\n')
    # ВЕКТОР: порядок тика — раздача слотов пула (EI) -> ждём кадр -> вывод. Вывод стартует сразу после
    # прерывания (известная фаза кадра), программный бюджет DI (vec_budget) считает от цены ISR.
    old = '\tcall RedrawScreen_part1\n\tcall waitforVBlank\n\tcall RedrawScreen_part2\n'
    assert old in text
    text = text.replace(old, ('' if DEMO else '\tcall vec_pool_begin\t; ВЕКТОР: слоты пула (до ожидания, с EI)\n') +
                        '\tcall waitforVBlank\t; ВЕКТОР: ждём кадр ДО отрисовки\n\tcall RedrawScreen_part1\n\tcall RedrawScreen_part2\n')
    # waitforVBlank выходит только сразу после halt (при тике > 5 кадров иначе вышли бы посреди кадра)
    old = '\tld a, (frames_noredraw)\n    ld hl, frames_lock\n\tcp (hl)\t\t\t; wait until we have spent at least 5 (PÂL) or 6 (NTSC) frames without redrawing\n\tjr nc, vblank_done\n'
    assert old in text, 'waitforVBlank_loop'
    if VI53:
        # Бюджет по ВИ53 знает РЕАЛЬНУЮ фазу кадра, поэтому опоздавшему тику (уже >= frames_lock кадров без
        # вывода) ждать начала кадра незачем: обязательный halt здесь был нужен программному бюджету и стоил
        # в тяжёлых сценах 0,4-0,7 кадра на тик (tools/bench_scenes.py, 2026-10-12). Куски панели, как и
        # раньше, рисуются только после halt — когда до срока ещё есть целые кадры.
        text = text.replace(old, '\tld a, (frames_noredraw)\n    ld hl, frames_lock\n\tcp (hl)\n\tjr nc, vblank_done\t; ВЕКТОР: тик опоздал — вывод сразу, с любой фазы кадра\n\tld a, (vec_wait_halted)\t; куски панели — только после halt\n\tand a\n\tjr z, waitforvblank_halt_go\n')
    else:
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
    # ВЕКТОР: плеер выводит все 14 регистров AY из теневых ячеек, а песня уровня шум и огибающую
    # не задаёт — после меню/интро их значения тянулись бы в игру (шипение). Гасим сразу после MUSIC_Load.
    # (с 2026-10-12 это делает сам вход плеера ark_init: плеер и его ячейки живут в квазидиске, из игры
    # при закрытом окне до них не достать)
    old = '\tld a, (current_level)\n\tcall MUSIC_Load\n'
    assert old in text, 'MUSIC_Load в game'
    text = text.replace(old, old + ';\n;\n;\n;\n')     # четыре строки прежней вставки: tools/overrides.py привязан к номерам строк
    # РЕЖИМ ЧИТОВ (vec_main.vec_cheat_tick): вызов раз в тик. Ставим ВМЕСТО строки-комментария перед проверкой
    # паузы — число строк не меняется (tools/overrides.py привязан к номерам строк).
    old = '\t; Press H for pause menu\n'
    assert text.count(old) == 1, 'mainloop: комментарий перед проверкой паузы'
    text = text.replace(old, '\tcall vec_cheat_tick\t; ВЕКТОР: читы для проверки (F1+F3 в меню)\n')
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
    # РУССКОЕ ИЗДАНИЕ: английской строки «PRESS FIRE» и ветки по language нет; строка-исходник
    # пароля мертва (её читает ianna.asm:81, а этот кусок в срез не попал). Число строк сохраняем:
    # ключ overrides ('score_src.asm', 391) — это строка score_gameover_string сразу под ними.
    old = ('score_password_string_rom: db "PASSWORD:1234567890",0\n'
           'score_gameover_string_en: db "    PRESS FIRE",0\n')
    assert old in sc, 'score.asm: строки пароля/gameover'
    sc = sc.replace(old, '; ВЕКТОР: score_password_string_rom не используется (ianna.asm:81 вне среза)\n'
                         '; РУССКОЕ ИЗДАНИЕ: английской строки «PRESS FIRE» нет\n')
    old = ('draw_gameover_string:\n        ld a, (language)\n        and a\n'
           '        jr z, draw_gameover_spanish\n    \tld iy, score_gameover_string_en\n'
           '        jr draw_password_common\ndraw_gameover_spanish:\n')
    assert old in sc, 'score.asm: ветка draw_gameover_string'
    sc = sc.replace(old, 'draw_gameover_string:\n; РУССКОЕ ИЗДАНИЕ: ветки по language нет\n;\n;\n;\n;\n;\n')
    (TR / 'score_src.asm').write_text(sc)
    ft = (SRC / 'font.asm').read_text(encoding='utf-8', errors='replace')
    # МЁРТВЫЙ КОД (tools/deadcode.py, 2026-10-22): меню и прозрачный шрифт живут в оверлее, из ROM эти
    # процедуры никто не зовёт — 226 Б. Тела вырезаются, метки остаются (заглушки в vec_stubs не трогаем).
    for name, nxt in (('LoadFONT_menu', 'print_string'), ('print_string_menu', 'print_string2'),
                      ('print_string3', 'next_word'), ('print_word_menu', None)):
        i = ft.index('\n' + name + ':') + 1
        j = ft.index('\n' + nxt + ':') + 1 if nxt else len(ft)
        # комментарий-шапку следующей процедуры оставляем: откатываемся от j к её последней строке кода
        k = ft.rfind('\n', 0, j - 1)
        while nxt and k > i and ft[k + 1:j].lstrip().startswith(';') or (nxt and k > i and not ft[k + 1:j].strip()):
            j = k + 1; k = ft.rfind('\n', 0, j - 1)
        ft = ft[:i] + name + ':\t; ВЕКТОР: мёртвый код вырезан (deadcode.py)\n' + ft[j:]
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
    old = 'MUSIC_Load_nomusic:\n\tpush af\n'; assert mu.count(old) == 1, 'MUSIC_Load_nomusic'
    mu = mu.replace(old, 'MUSIC_Load_nomusic:\n\tld b, a\t\t; ВЕКТОР: номер песни — входу плеера ark_init (B доживает до call atInit)\n\tpush af\n')
    mu = mu.replace('atInit: equ MUSIC_CODE\natPlay: equ MUSIC_CODE + 3\natStop: equ MUSIC_CODE + 6\natSfxInit: equ MUSIC_CODE + 9\natSfxPlay: equ MUSIC_CODE + 12\natSfxStop: equ MUSIC_CODE + 15',
                    '; ВЕКТОР: плеер ассемблируется на месте, точки входа — его метки (atInit/atPlay/atStop/atSfxInit/atSfxPlay/atSfxStopAll)')
    # ВЕКТОР: плеер живёт в квазидиске (оверлей arkos.bin, стр.3 ARK_ADDR, окно $A000-$DFFF — то же, что у
    # песни). MUSIC_Load, FX_Play и прерывание окно уже открывают; MUSIC_Stop — нет, поэтому здесь оно
    # открывается и возвращается так же, как в MUSIC_Load.
    old = 'MUSIC_Stop:\n\tcall atStop\n\tcall atSfxStop\n'
    assert mu.count(old) == 1, 'MUSIC_Stop'
    mu = mu.replace(old, 'MUSIC_Stop:\n\tcall MUSIC_setbank\n\tcall ark_stop\n\tcall MUSIC_restorebank\n')
    # ВЕКТОР: данные эффектов лежат в окне квазидиска ($D980, страница 3); atSfxPlay читает оттуда таблицу
    # инструментов — из игровой логики окно закрыто, поэтому открыть на время вызова и вернуть прежнюю страницу
    # (через setROM2, чтобы тень окна для ISR была согласована).
    m = re.search(r'\n(\tld l, a[^\n]*; effect\n)', mu); assert m, 'FX_Play: ld l,a'
    mu = mu[:m.start(1)] + '\tld l, a\t\t\t; ВЕКТОР: окно квазидиска на страницу музыки/эффектов\n\tld a, (ROMBank1)\n\tpush af\n\tld a, MUSIC_ROM_PAGE\n\tcall setROM2\n\tld a, l\n' + mu[m.start(1):]
    old2 = '\tld bc, 0\n\tcall atSfxPlay\n'; assert mu.count(old2) == 1, 'FX_Play: call atSfxPlay'
    mu = mu.replace(old2, '\tld bc, 0\n\tcall atSfxPlay\n\tpop af\t\t\t; ВЕКТОР: вернуть прежнюю страницу окна\n\tcall setROM2\n')
    (TR / 'music_src.asm').write_text(mu)
    # ВЕКТОР: плеер Arkos — НЕ перевод Z80-исходника, а нативный i8080 (src/vec/arkos_hot.asm),
    # написанный по спецификации tools/arkos_model.py. Оригинал ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm
    # остался только эталоном: по нему сверяются гейты tests/music/check_all.py и сама модель.
    (TR / 'arkos.asm').write_text((VEC / 'arkos_hot.asm').read_text(encoding='utf-8'))   # для гейтов tests/music
    # В ROM от плеера остались только адреса входов (таблица переходов в начале оверлея) и процедуры
    # сброса пула, которые раньше лежали в его зазоре.
    (TR / 'arkos_rom.asm').write_text(
        '; сгенерировано build_vec: плеер Arkos — оверлей arkos.bin в странице 3 квазидиска\n'
        f'ARK_ADDR\tequ ${ARK_ADDR:04X}\n'
        'atInit\t\tequ ARK_ADDR\t; ark_init: гасит шум/огибающую и зовёт atInit (DE = песня)\n'
        'atPlay\t\tequ ARK_ADDR+3\n'
        'ark_stop\tequ ARK_ADDR+6\t; atStop + atSfxStopAll\n'
        'atSfxInit\tequ ARK_ADDR+9\n'
        'atSfxPlay\tequ ARK_ADDR+12\n'
        + (VEC / 'pool_hr.asm').read_text(encoding='utf-8'))
    # Оверлей из двух кусков: код (таблица переходов + плеер) и данные (таблицы периодов, состояние).
    # Данные собираются первыми — их метки уходят коду списком equ. Символов ROM плеер не берёт.
    (ROOT / 'build').mkdir(exist_ok=True)
    src = (VEC / 'arkos_hot.asm').read_text(encoding='utf-8')
    cut = src.index(';;; ============================== данные')
    code, dat = src[:cut], src[cut:]
    (ROOT / 'build/arkos_dat.asm').write_text(
        '; сгенерировано build_vec из src/vec/arkos_hot.asm: таблицы и состояние плеера Arkos (стр.3 квазидиска)\n'
        f'\torg ${ARK_DAT:04X}\n' + dat)
    (ROOT / 'build/arkos_ovl.asm').write_text(
        '; сгенерировано build_vec из src/vec/arkos_hot.asm: код плеера Arkos в странице 3 квазидиска.\n'
        '; Окно $A000-$DFFF на страницу 3 открывают вызывающие: прерывание (vec_isr), MUSIC_Load, MUSIC_Stop, FX_Play.\n'
        '\tinclude "arkos_dat_syms.asm"\n'
        f'\torg ${ARK_ADDR:04X}\n'
        '\tjp ark_init\n\tjp atPlay\n\tjp ark_stop\n\tjp atSfxInit\n\tjp atSfxPlay\n'
        'ark_init:\n\tpush bc\t\t; B = номер песни, DE = песня\n\tcall ay_detect\t; есть ли AY (иначе эффекты на ВИ53)\n\tpop bc\n\t; плеер выводит все 14 регистров AY из теневых ячеек, а песня уровня шум и огибающую не\n'
        '\tld a,b\t\t; задаёт — после меню/интро их значения тянулись бы в игру (шипение). B = номер песни\n'
        '\tcp 9\t\t; (MUSIC_Load): гасим только для песен уровней 0..8, как раньше делала игра после загрузки\n'
        '\tjp nc,atInit\n\txor a\n'
        '\tld (_atVAR_Reg6),a\n\tld (_atVAR_Reg11),a\n\tld (_atVAR_Reg12),a\n\tjp atInit\n'
        'ark_stop:\n\tcall atStop\n\tjp atSfxStopAll\n'
        + code)

def cover_asm():
    """Заставка стартовой загрузки — загрузочный экран ZX Spectrum-версии (MAC) в раскраске «Лунное серебро»
    (вариант 12 от Codex, 24.10; строки и столбцы — чётные из его 512x512): tools/data/art/cover_vector.png — 256x256, индексированный, номер точки =
    слот палитры Вектора, палитра — в метаданных VectorPalette. Набор грузится мимо экрана (vec_bootload.asm).
    Слоты с ролью: 0 — чёрный; 7 — пустая полоса (кремовый $B7); 15 — заливка полосы (красный $0E): хук ставит
    бит плоскости $8000, 7 | 8 = 15. Надпись «НАЖМИ ПРОБЕЛ» печатает оверлей меню шрифтом меню (MB_MCHR): его
    обводка — слот 0, тело — слоты 7 и 8 (PERM уровня 1), поэтому в 8 — оранжевый $27. Полоса — в центре,
    строка надписи — строка 11 шрифта (y 120..127). Пишет build/cover.bin (aPLib экрана $8000-$FFFF) — его кладёт
    на дорожки DL.COVER_TRACK.. build_fdd.py — и build/cover_preview.png; возвращает код и данные."""
    from PIL import Image
    import numpy as np
    LS_COL, LS_Y = 10, 114                                # полоса: колонки 10..21 (x 80..175), строки y 114..133
    img = Image.open(ROOT / 'tools/data/art/cover_vector.png')
    assert img.mode == 'P' and img.size == (256, 256), (img.mode, img.size)
    pal = [int(c, 16) for c in img.info['VectorPalette'].split()]
    assert len(pal) == 16 and pal[0] == 0 and pal[7] == 0xB7 and pal[8] == 0x27 and pal[15] == 0x0E, pal
    q = np.array(img)
    # логотип RetroWorks — плашка с экрана меню (menu_screen оригинала, x 202..255, y 151..177) вместо логотипа MAC
    # (x 0..63, y 224..254): серый — свободный слот 6, тёмно-красный — свободный 13; правее и выше плашки
    # остатки старого логотипа (слоты 0, 4, 8, 15) зарисованы фоном: правее — копией столбцов на 8 точек правее,
    # выше — точкой над ней
    from build_edd import sr5_rows as _sr5
    from pletter import depack as _pd
    assert pal[6] == 0 and pal[13] == 0 and not ((q == 6) | (q == 13)).any(), 'слоты 6/13 заняты'
    pal[6], pal[13] = 0x52, 0x05
    MSX2V = {1: 0, 7: 6, 11: 5, 10: 8, 3: 13, 5: 7, 6: 10, 12: 6, 13: 6}   # цвет MSX -> слот заставки
    menu = _sr5(_pd((SRC / 'menu_screen.SR5.plet1').read_bytes()), 192)
    PX, PY, PW, PH = 3, 227, 55, 28                       # плашка 54x27 + чёрная тень справа и снизу
    for y in range(PH):
        for x in range(PW):
            q[PY + y, PX + x] = 0 if x == PW - 1 or y == PH - 1 else MSX2V[menu[151 + y][202 + x]]
    for y in range(224, 255):
        for x in range(64):
            if PX <= x < PX + PW and y >= PY or q[y, x] not in (0, 4, 8, 15): continue
            if x >= PX + PW:
                q[y, x] = q[y, x + 8]                     # правее — дали без логотипа: сдвиг сохраняет фактуру
            else:
                q[y, x] = q[y - 1, x]
    def rgb(b): return ((b & 7) * 255 / 7, ((b >> 3) & 7) * 255 / 7, ((b >> 6) & 3) * 255 / 3)
    vram = bytearray(32768)
    def put(x, L, k):
        off = (x >> 3) * 256 + L; bit = 0x80 >> (x & 7)
        for p in range(4):
            if k & (8 >> p): vram[p * 8192 + off] |= bit
            else: vram[p * 8192 + off] &= ~bit & 0xFF
    for y in range(256):
        for x in range(256):
            put(x, 255 - y, int(q[y, x]))
    # рамка полосы: x LS_COL*8..+95, строки y LS_Y-1..LS_Y+20 — рамка цвета 0, внутри цвет 7; хук ставит бит
    # $8000 — красный
    x0, L0 = LS_COL * 8, 255 - LS_Y
    ytop = int(re.search(r'^MB_YTOP\s+equ (\d+)', (VEC / 'menu_ram.asm').read_text(encoding='utf-8'), re.M).group(1))
    assert 255 - (ytop - 11 * 8) == LS_Y + 6, 'строка 11 шрифта меню (ovl_press) — не по центру полосы'
    for x in range(x0, x0 + 96):
        for L in range(L0 - 20, L0 + 2):
            put(x, L, 0 if x in (x0, x0 + 95) or L in (L0 - 20, L0 + 1) else 7)
    prev = Image.new('RGB', (256, 256))                   # предпросмотр: build/cover_preview.png (512x512, как в Emu80)
    for y in range(256):
        for x in range(256):
            k = sum(((vram[p * 8192 + (x >> 3) * 256 + 255 - y] >> (7 - (x & 7))) & 1) << (3 - p) for p in range(4))
            prev.putpixel((x, y), tuple(int(t) for t in rgb(pal[k])))
    prev.resize((512, 512), Image.NEAREST).save(ROOT / 'build/cover_preview.png')
    tmp = ROOT / 'build/_cover'
    tmp.write_bytes(bytes(vram))
    r = subprocess.run([str(ROOT / 'tools/bin/apultra'), str(tmp), str(tmp.with_suffix('.ap'))], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    blob = tmp.with_suffix('.ap').read_bytes()
    assert len(blob) <= 2 * 10240, f'обложка {len(blob)} Б: не влезает в две дорожки'
    (ROOT / 'build/cover.bin').write_bytes(blob)
    fdd = (VEC / 'vec_fdd.asm').read_text(encoding='utf-8')
    assert re.search(r'^vfl_fill:\n\tld a,\(vec_fdd_sec\)', fdd, re.M), 'vfl_fill начинается не с ld a,(nn) (LS_OP0)'
    m = re.search(r'^vec_fdd_load:(.*?)^vfl_fill:', fdd, re.M | re.S)
    out = ['\n; --- стартовая загрузка с заставкой (сгенерировано build_vec.cover_asm) ---',
           f'COVER_TRACK\tequ {DL.COVER_TRACK}', f'LS_COL\t\tequ {LS_COL}', f'LS_L0\t\tequ ${L0:02X}', f'LS_L1\t\tequ ${L0 - 20:02X}', 'LS_OP0\t\tequ $3A\t; ld a,(nn) — первый байт vfl_fill',
           '\tds string_area+1024-$\t\t; за буфером сектора (1К)',
           (VEC / 'vec_bootload.asm').read_text(encoding='utf-8'),
           (VEC / 'vec_lscreen.asm').read_text(encoding='utf-8'),
           'ls_pal:\tdb ' + ','.join(f'${v:02X}' for v in pal),
           'bl_end:']
    print(f'заставка: обложка {len(blob)} Б (дорожки {DL.COVER_TRACK}..{DL.COVER_TRACK + (len(blob) - 1) // 10240}), палитра '
          + ' '.join(f'{v:02X}' for v in pal))
    return '\n'.join(out) + '\n'

def make_vars():
    text = (SRC / 'vars.asm').read_text(encoding='utf-8', errors='replace')
    text = text.replace('music_addr: ds 4096', 'music_addr: ds 2')
    text = text.replace('music_sfx:  ds 1100', 'music_sfx:  ds 2')
    text = text.replace('MUSIC_CODE: ds 2000', 'MUSIC_CODE: ds 2')
    # string_area: как в оригинале 2048 (уровень 7 — 1994 Б; с 1536 уровень 2 затирал OBJECT_DATA); OBJECT_DATA на границе страницы
    if DEMO: text = text.replace('string_area: ds 2048', 'string_area: ds 512')
    else:
        # одноразовый код старта для Турбо+ живёт в string_area: образ грузится целиком, а string_area до
        # меню не используется (vec_start зовёт turbo_init первым делом); в резиденте до $6A00 места нет
        boot = (VEC / 'vec_turbo_boot.asm').read_text(encoding='utf-8', errors='replace') + cover_asm()
        assert 'string_area: ds 2048' in text
        text = text.replace('string_area: ds 2048', 'string_area:\n' + boot + '\n\tds 2048 - ($ - string_area)\t; bl_end <= string_area+2048 (иначе ds отрицательный)')
    # неиспользуемые буферы VDP-команд (кроме vdpCmdSprite: там NY для drawSprite) и палитры
    text = re.sub(r'^(tileDat|fgtileDat|dirtyTileDat|cmdDat|charDat|charDat2|charDat3|fillDat|vdpCmdWeapon|lineMoveDat|vdpCopyDat|scoreDat): ds 15', r'\1: ds 0', text, flags=re.M)
    text = text.replace('currentPal: ds 32', 'currentPal: ds 0')
    # РУССКОЕ ИЗДАНИЕ: приглашение пароля на панели. draw_password пишет 10 знаков по
    # score_password_string+9, поэтому приставка ровно 9 знаков: два пробела + «ПАРОЛЬ:».
    # Коды шрифта: 96..127 = А..Я (font_ru.py), 32 = пробел, 58 = двоеточие.
    old = 'score_password_string: db "PASSWORD:1234567890",0'
    assert old in text, 'vars.asm: score_password_string'
    text = text.replace(old, 'score_password_string: db 32,32,111,96,112,110,107,124,58,"1234567890",0\t; «  ПАРОЛЬ:»\n')
    text = text.replace('level_string_en_addr: dw 0\n', '; РУССКОЕ ИЗДАНИЕ: level_string_en_addr не нужен\n')
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

def check_overlays_in_edd():
    """Оверлеи меню и паузы живут в квазидиске и зовут функции движка по адресам ТОЙ сборки ROM, при
    которой собраны. Порядок сборки замкнут в кольцо: build_edd кладёт в образ .bin от предыдущего
    build_vec, а build_vec берёт из образа адреса. Если не сделать второй проход, в образе останется
    старый оверлей: он пишет по чужим адресам, и это ловится не сразу (у нас — одним испорченным
    байтом палитры, экран позеленел только после того, как в этот слот переехал заметный цвет)."""
    edd = ROOT / 'build/ianna.edd'
    if not edd.exists():
        return
    data = edd.read_bytes()
    stale = []
    for name, addr in (('menu_ovl.bin', 0x8440), ('pause_ovl.bin', 0x9000), ('menu_ram.bin', 0x9800), ('arkos.bin', ARK_ADDR)):   # (arkos_dat.bin от адресов ROM не зависит)
        f = ROOT / 'build' / name
        if not f.exists():
            continue
        b = f.read_bytes()
        off = 3 * 65536 + addr
        if data[off:off + len(b)] != b:
            stale.append(name)
    if stale:
        print(f'ВНИМАНИЕ: в build/ianna.edd оверлеи от прежней сборки ({", ".join(stale)}) — '
              f'пересоберите: python3 tools/data/build_edd.py && python3 tools/build_vec.py')

def strip_dead(path, names):
    """Вырезать блок (метка + тело до следующей метки). НЕ ИСПОЛЬЗУЕТСЯ: проверка показала, что
    мёртвого кода в образе фактически нет — см. docs/ANALYSIS.md, «резерв мёртвого кода оказался мифом».
    Оставлено как инструмент: если когда-нибудь появится честный кандидат, резать им, обязательно
    сверяя кадр с эталоном (tools/shot_tick.py --fixrand) — косвенная адресация ловится только так."""
    t = path.read_text()
    for n in names:
        m = re.search(r'(?m)^' + re.escape(n) + r':.*?(?=^[A-Za-z_][\w.]*:)', t, re.S)
        if not m:
            print(f'ВНИМАНИЕ: мёртвый блок {n} не найден — пропускаю'); continue
        assert len(re.findall(r'\b' + re.escape(n) + r'\b', t)) == 1, f'{n}: на блок есть ссылки'
        t = t[:m.start()] + t[m.end():]
    path.write_text(t)

def per_offset_helpers(order):
    """Хелперы (ix+d)/(iy+d) со ВШИТЫМ смещением — вместо общих z_i?_rda/_sta.

    Общий хелпер получает d либо через A (тогда на площадке лишние 2 байта 'ld a,d'),
    либо байтом за call (тогда внутри пляска ex (sp),hl / z_ret — 216 тактов). Со вшитым
    смещением площадка — один call (3 байта), а тело сводится к
        push hl / ld hl,(z_ix) / inc hl * d / ld a,(hl) | ld (hl),a / pop hl / ret,
    то есть 92+8d тактов. Ни одна его команда не трогает A (кроме результата), BC, DE
    и флаги, поэтому вшитый хелпер годится и там, где перевод звал вариант с флагами
    (z_i?_rda), и там, где без них (_nf).

    Смещение вшивается только если это окупается по БАЙТАМ: тело стоит 8+d байт, каждая
    площадка чтения экономит 2 байта, записи — 1. Чтения с d>6 не трогаем: там inc-цепочка
    уже дороже общего хелпера по тактам (92+8d против 124), а байты почти не выигрывают.
    """
    RD = re.compile(r'(?m)^\tld a,(\d+)\n\tcall z_(ix|iy)_rda(?:_nf)?\n')
    ST = re.compile(r'(?m)^\tcall z_(ix|iy)_sta\n\tdb (\d+)\n')
    files = [f for f in order if f.suffix == '.asm' and f.parent == TR]
    texts = {f: f.read_text(encoding='utf-8', errors='replace') for f in files}
    cnt = {}
    for t in texts.values():
        for d, reg in RD.findall(t):
            if int(d) <= 6: cnt[(reg, 'rd', int(d))] = cnt.get((reg, 'rd', int(d)), 0) + 1
        for reg, d in ST.findall(t):
            cnt[(reg, 'st', int(d))] = cnt.get((reg, 'st', int(d)), 0) + 1
    take = {k for k, n in cnt.items() if (2 * n if k[1] == 'rd' else n) > 8 + k[2]}
    if not take: return ''
    def rd_sub(m):
        d, reg = int(m.group(1)), m.group(2)
        return f'\tcall z_{reg}_rd{d}\n' if (reg, 'rd', d) in take else m.group(0)
    def st_sub(m):
        reg, d = m.group(1), int(m.group(2))
        return f'\tcall z_{reg}_st{d}\n' if (reg, 'st', d) in take else m.group(0)
    # 'ld (i?+d),n' там, где A мёртв (метку ставит транслятор): те же 5 байт, но 136 тактов
    # вместо 252 — вшитый хелпер уже есть, новых байт не появляется
    SN = re.compile(r'(?m)^\tcall z_(ix|iy)_stn\n\tdb (\d+)\n\tdb (.*?)\t; A мёртв\n')
    def sn_sub(m):
        reg, d, n = m.group(1), int(m.group(2)), m.group(3)
        return f'\tld a,{n}\n\tcall z_{reg}_st{d}\n' if (reg, 'st', d) in take else m.group(0)
    for f, t in texts.items():
        t2 = SN.sub(sn_sub, ST.sub(st_sub, RD.sub(rd_sub, t)))
        t2 = t2.replace('\t; A мёртв\n', '\n')
        if t2 != t: f.write_text(t2)
    out = ['\n; --- хелперы (i?+d) со вшитым смещением (сгенерированы build_vec.py) ---\n']
    for reg, kind, d in sorted(take):
        n = cnt[(reg, kind, d)]
        out.append(f'z_{reg}_{kind}{d}:\t; {"a := " if kind == "rd" else ""}({reg}+{d})'
                   f'{"" if kind == "rd" else " := a"} — {n} площадок\n\tpush hl\n\tld hl,(z_{reg})\n')
        out.append('\tinc hl\n' * d)
        out.append(('\tld a,(hl)\n' if kind == 'rd' else '\tld (hl),a\n') + '\tpop hl\n\tret\n')
    return ''.join(out)

def main():
    TR.mkdir(parents=True, exist_ok=True)
    slice_ianna(); make_vars(); make_score_font(); make_music()
    (TR / 'vdp_consts.asm').write_text('; константы из vdp.asm/sprites.asm/music.asm/input.asm\n' + f'C8\tequ {1 if C8 else 0}\t; 8 цветов (3 плоскости)\n'
                                     f'NOMIRROR\tequ {1 if NOMIRROR else 0}\t; ЗАМЕРНЫЙ режим: зеркальный блит заменён прямым (картинка неверна)\n'
                                     f'SPR3CLR\tequ {1 if SPR3CLR else 0}\t; спрайт трёхплоскостной: плоскость 3 чистим маской, данных нет\n'
                                     f'SPR3\tequ {1 if SPR3 else 0}\t; ЗАМЕРНЫЙ режим: спрайты не пишут плоскость 3 (картинка неверна — под спрайтом остаются старшие биты фона)\n'
                                     f'VI53\tequ {1 if VI53 else 0}\t; бюджет по счётчику 0 ВИ53\n' + consts_from('vdp.asm') + consts_from('sprites.asm') + consts_from('music.asm') + consts_from('input.asm'))
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
    # ВЕКТОР: обход списка спрайтов — нативно (src/vec/drawlist_hot.asm) вместо перевода через IX/IYH
    d = cut(d, lambda l: l.startswith('DrawSpriteList:'), lambda l: l.startswith('CleanSprite:'),
            (VEC / 'drawlist_hot.asm').read_text(encoding='utf-8'))
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
    # Высоту тоже режем до ряда 9: LoadScreen инвалидирует 16x12, а карты RedrawInvTiles (overlap_hot.asm,
    # 16x10 бит) на рядах 10-11 переполняют младший байт адреса — карта фона писала в карту переднего слоя
    # (туман в рядах 0-1 пропадал после смены экрана), карта переднего слоя — в код по $6A00 (вход vec_blit2).
    (TR / 'tiles.asm').write_text(t.replace(old, 'InvalidateSTiles:\n\tld a,c\t; ВЕКТОР: ряды панели не рисуются — прямоугольник не нужен\n\tcp 10\n\tret nc\n\tadd a,e\n\tcp 11\n\tjp c,ist_hok\n\tld a,10\n\tsub c\n\tld e,a\t; ряды 10-11 не копим: карты RedrawInvTiles на 10 рядов\nist_hok:\n\tld a,(ndirtyrects)\t; ВЕКТОР: список на 48 записей, дальше лежит SPDATA\n\tcp 48\n\tret nc\n\tpush de'))
    # Граница списка грязных прямоугольников. У оригинала её нет (tiles_dirty: ds 192 = 48 записей, сразу
    # за ним SPDATA): 49-я запись затирала спрайты, счётчик рос дальше и раздача слотов шла по мусору.
    # В обычной игре пик — 17 записей (tools/spwatch.py, 9 уровней со штатного старта), переполнение
    # поймано только на долгом падении героя, поставленного стендом в пустоту. Полный список — запись
    # отбрасывается: худшее, что будет, — не перерисованный в этом тике стайл. Счётчик уже в A, поэтому
    # повторное чтение из тела оригинала убираем (правка стоит 3 Б ROM).
    t = (TR / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    old = 'ret nc\n\tpush de\n\tld a, (ndirtyrects)\n'
    assert t.count(old) == 1, 'InvalidateSTiles: тело после транслятора изменилось'
    (TR / 'tiles.asm').write_text(t.replace(old, 'ret nc\n\tpush de\n'))
    # ГРЯЗНОЕ ПО КОЛОНКАМ (vec_vdp.asm, vec_col_tab): InvalidateTiles округляет прямоугольник до стайлов 16x16,
    # а точные границы по X теряет. Сохраняем их в бите 7: у B (первый стайл) — «левая колонка не нужна»
    # (первый символ нечётный), у D (число стайлов) — «правая колонка последнего не нужна» (последний символ
    # чётный). Оба байта так и ложатся в запись tiles_dirty; читает их только раздача слотов (vpb_rect).
    # Проверка пересечений получает чистые значения: D перед ней удваивается (бит 7 уходит), B она маскирует.
    t = (TR / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    old = ('InvalidateTiles:\n\tld a, d\n\tadd a, b\t; A = last X tile\n\tdec a\n\trrca\n\tand $1f\t; A = max stile\n\tld d, a\n'
           '\tld a, b\n\trrca\n\tand $1f\n\tld b, a\t; B = min stile\n\tld a, d\n\tsub b\n\tinc a\n\tld d, a\t; D = number of stiles\n')
    assert t.count(old) == 1, 'InvalidateTiles: начало после транслятора изменилось'
    (TR / 'tiles.asm').write_text(t.replace(old,
        'InvalidateTiles:\n\tld a, d\n\tadd a, b\n\tdec a\n\trrca\n\tld l, a\t; L = последний символ, сдвинутый: бит 7 = он нечётный\n'
        '\tld a, b\n\trrca\n\tld h, a\t; H = первый символ, сдвинутый: бит 7 = он нечётный\n\tand $1f\n\tld b, a\t; B = min stile\n'
        '\tld a, l\n\tand $1f\n\tsub b\n\tinc a\n\tld d, a\t; D = number of stiles\n'
        '\tld a, h\n\tand $80\n\tor b\n\tld b, a\t; бит 7: левая колонка первого стайла не нужна\n'
        '\tld a, l\n\tcpl\n\tand $80\n\tor d\n\tld d, a\t; бит 7: правая колонка последнего стайла не нужна\n'))
    # (хук готовых тайлов фон+FG в DrawTile снят 2026-09-07 вместе с fgc_ovl: с пулом он был мёртв)
    # накладные обхода грязных тайлов в RedrawInvTiles_FG (z_exx x2 на тайл, EI) — зарядить в бюджет DI
    t = (TR / 'tiles.asm').read_text(encoding='utf-8', errors='replace')
    old = 'DrawFGTile:\n'
    assert t.count(old) == 1
    (TR / 'tiles.asm').write_text(t.replace(old, 'DrawFGTile:\n\tpush af\t; ВЕКТОР: накладные обхода — в бюджет DI\n\tld a,3-C8\t; обход FG: 16ц медиана 2.1/p90 2.6; c8 2.1 -> 2\n\tcall vec_budget\n\tpop af\n'))
    translate(TR / 'ianna_main_src.asm', TR / 'ianna_main.asm')
    # ВЕКТОР: вода и огонь анимируются вдвое реже оригинала (каждый 4-й тик вместо каждого 2-го).
    # Блит анимированных тайлов — заметная доля тика, а на экранах с большим водоёмом (уровень 1,
    # экран 4,0: девять анимированных супертайлов) тик из-за него растягивался до 10 кадров при
    # номинале 5, и анимация шла рывками. Патчим УЖЕ транслированный файл: вставка в _src заставляет
    # транслятор считать соседний код нуждающимся в сохранении флагов и тянуть лишние хелперы z_*.
    # IANNA_ANIM_MASK=1 возвращает оригинальный темп (для сравнения).
    _mask = os.environ.get('IANNA_ANIM_MASK', '3')
    _f = TR / 'ianna_main.asm'
    _t = _f.read_text()
    _old = '\tld a, (animate_tile)\n\tinc a\n\tld (animate_tile), a\n\tand 1\n'
    assert _old in _t, 'animate_tile в транслированном mainloop'
    _t = _t.replace(_old,
        '\tld a, (animate_tile)\n\tinc a\n\tld (animate_tile), a\n'
        f'\tand {_mask}\t\t; ВЕКТОР: анимация каждый {int(_mask)+1}-й тик\n')
    # ВЕКТОР: на уровнях с четырёхцветным спрайтом слоты палитры 1..3 отданы ему, и на каждом экране
    # там своя тройка цветов — читаем её из набора при загрузке экрана. Процедура vec_scrpal живёт
    # в образе (src/vec/vec_blit2.asm) и сама выходит, если у уровня такой таблицы нет
    # (vec_scrpal_addr = 0). Фон в эти слоты не заглядывает: перестановка увела его в 0 и 4..15.
    _old = 'LoadScreen:\n'
    assert _old in _t
    _t = _t.replace(_old, 'LoadScreen:\n\tpush af\n\tcall vec_scrpal\n\tpop af\n', 1)
    _f.write_text(_t)
    translate(TR / 'score_src.asm', TR / 'score.asm')
    translate(TR / 'font_src.asm', TR / 'font.asm')
    if not DEMO:
        translate(TR / 'music_src.asm', TR / 'music.asm')
    translate(TR / 'vars_src.asm', TR / 'vars.asm')
    data = ROOT / ('build/demo_data.asm' if DEMO else 'build/gen_data.asm')
    if not DEMO and data.exists():
        # сторож рассинхрона: gen_data.asm (таблица банков) обязан соответствовать build/ianna.edd,
        # иначе движок читает спрайты по чужим адресам — ловилось как «герой в прыжке стал скелетом»
        import re as _re
        m = _re.search(r'^; сгенерировано build_edd\.py.*$', data.read_text(), _re.M)
        edd = ROOT / 'build/ianna.edd'
        if edd.exists() and edd.stat().st_mtime > data.stat().st_mtime + 1:
            print('ВНИМАНИЕ: build/ianna.edd новее gen_data.asm — соберите их одной командой '
                  '(python3 tools/data/build_edd.py), иначе таблица банков не совпадёт с набором')
    order = [VEC / 'vec_boot.asm', TR / 'vdp_consts.asm']
    if DEMO:
        order.append(data)              # org $0200
    order += [VEC / 'vec_main.asm', TR / 'ianna_main.asm', TR / 'tiles.asm', TR / 'drawsprite.asm',
              TR / 'entities.asm', TR / 'scripts.asm', TR / 'objects.asm', TR / 'depack.asm',
              TR / 'score.asm', TR / 'font.asm'] + ([TR / 'music.asm', TR / 'arkos_rom.asm'] if not DEMO else []) + [
              VEC / 'vec_vdp.asm', VEC / 'vec_isr.asm'] + ([] if DEMO else [VEC / 'vec_intro.asm']) + ([VEC / 'vec_fdd.asm'] if C8 else []) + [VEC / 'vec_stubs.asm']
    if not DEMO:
        order.append(data)
    gen_rt = per_offset_helpers(order)
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
    (TR / 'z80rt_used.asm').write_text(''.join(keep) + gen_rt)
    order.append(TR / 'z80rt_used.asm')
    order.append(VEC / 'vec_mirr.asm')
    order.append(VEC / 'vec_blit2.asm')   # прямой блит двухплоскостных банков
    if not DEMO:
        order.append(VEC / 'vec_turbo.asm')   # Вектор Турбо+ и ожидания контроллера дисковода
    order.append(VEC / 'vec_hi.asm')        # org $6AB0 (окно в vec_col_tab), кроме демо
    order += [TR / 'vars.asm', VEC / 'vec_vars.asm']   # org VARS_ADDR
    parts = [f'DEMO\tequ {1 if DEMO else 0}\n']
    for f in order:
        parts.append(f'\n; ======== {f.name} ========\n')
        body = f.read_text(encoding='utf-8', errors='replace')
        # vec_vars держит место под загрузчик уровня (поверх rev256/slot_tab) — тело подставляем здесь,
        # чтобы правки в vec_fdd.asm не пропадали (раньше там лежала копия и молча устаревала)
        if '; @@INCLUDE vec_fdd.asm' in body:
            inc = (VEC / 'vec_fdd.asm').read_text(encoding='utf-8', errors='replace')
            body = body.replace('; @@INCLUDE vec_fdd.asm', inc)
        parts.append(body)
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
        # Конец кода — конец ПОСЛЕДНЕЙ инструкции, а не её адрес: трёхбайтовый jp на $6AFE считался
        # «до $6AFE, зазор 1», а его третий байт лежал на $6B00 и затирался строками уровня
        # (сцены с четырёхцветным спрайтом падали в данные — блит уходил по jp в мусор).
        code_end = 0
        for line in lst.split('\n'):
            if 'vars наверху ОЗУ' in line: break
            mm = re.match(r'^([0-9A-F]{4}): ([0-9A-F]+)\s', line)     # байты в листинге без пробелов
            if mm and not DEMO and 0x6AB0 <= int(mm.group(1), 16) < 0x6AF8: continue   # окно vec_hi.asm
            if mm: code_end = max(code_end, int(mm.group(1), 16) + len(mm.group(2)) // 2)
        assert code_end <= VARS_ADDR, f'код до ${code_end:04X} НАЕХАЛ на переменные ${VARS_ADDR:04X}'
        assert code_end <= 0x6A00, f'код дошёл до ${code_end:04X}: в $6A00-$6AFF лежит vec_col_tab (vec_vdp.asm)'
        def _sym(n):
            m_ = re.search(r'^' + n + r'\s+=\s+\$([0-9A-F]{4})', lst, re.M)
            return int(m_.group(1), 16) if m_ else None
        if _sym('bl_end'):   # стартовая загрузка: таблица длин на месте главного цикла старого загрузчика
            assert _sym('vfl_fill') - _sym('vec_fdd_load') >= 192, 'BL_TAB (192 Б) не влезает до vfl_fill'
            assert _sym('bl_end') <= _sym('string_area') + 2048
            print(f"стартовый загрузчик: string_area+{_sym('bl_gb') - _sym('string_area')}..+{_sym('bl_end') - _sym('string_area')} из 2048")
        mh = re.search(r'^vec_hi_end\s+=\s+\$([0-9A-F]{4})', lst, re.M)
        assert mh, 'нет vec_hi_end'
        if not DEMO:
            assert int(mh.group(1), 16) <= 0x6AF8, f'окно vec_hi.asm дошло до ${mh.group(1)}: с $6AF8 — joy_idle и ячейки читов (vec_vdp.asm)'
            print(f'окно $6AB0: до ${int(mh.group(1), 16)-1:04X} (свободно {0x6AF8-int(mh.group(1), 16)} Б)')
            # Индекс isr_fix_tab (vec_isr.asm ISR_IDX_PAGE0/PAGES, isr_idx_init): записи таблицы обязаны лежать в
            # страницах индекса, иначе поиск идёт с начала таблицы — верно, но в разы медленнее (сторож, не ошибка)
            mi = re.search(r'^ISR_IDX_PAGE0\s+=\s+\$([0-9A-F]+)', lst, re.M); mn = re.search(r'^ISR_IDX_PAGES\s+=\s+\$([0-9A-F]+)', lst, re.M)
            mt = re.search(r'^([0-9A-F]{4}):\s+isr_fix_tab:', lst, re.M)
            if mi and mn and mt:
                p0 = int(mi.group(1), 16) << 8; p1 = p0 + (int(mn.group(1), 16) << 8); ends = []
                for line in lst[mt.end():].split('\n'):
                    mm = re.match(r'^[0-9A-F]{4}: ([0-9A-F]{4})\s+(?:\[[^\]]*\]\s+)?\s*dw (\S+)', line)
                    if mm: ends.append((int(mm.group(1)[2:] + mm.group(1)[:2], 16), mm.group(2)))
                    if 'dw $FFFF' in line: break
                out = [f'{n} ${a:04X}' for a, n in ends[:-1] if not p0 < a < p1]
                if out: print(f'ВНИМАНИЕ: записи isr_fix_tab вне индекса ${p0:04X}-${p1-1:04X}: ' + ', '.join(out) + ' — поправьте ISR_IDX_PAGE0/PAGES (vec_isr.asm)')
        print(f'код до ${code_end-1:04X} включительно, переменные с ${VARS_ADDR:04X} (зазор {VARS_ADDR-code_end} Б)')
        m = re.search(r'^OBJECT_DATA\s+=\s+\$([0-9A-F]{4})', lst, re.M)
        assert m and int(m.group(1), 16) & 0xFF == 0, 'OBJECT_DATA не выровнена на страницу!'
        print(f'OK: build/{name}.rom {size} Б, конец = ${0x100+size:04X} (граница VRAM $8000, свободно {0x8000-0x100-size} Б)')
        if not DEMO:
            build_menu_bins(lst)
            check_overlays_in_edd()
        return 0
    return 1

def build_menu_bins(lst):
    """Оверлей меню и RAM-блоб: собираются отдельно с импортом символов игры из .lst."""
    need = ['depack', 'vfl_blk', 'vlt_dirty', 'ls_end', 'z_ldir', 'vfl_restore', 'vfl_seek', 'vfl_fill', 'vfl_stream', 'vfl_ctl', 'vfl_ready', 'vec_fdd_rdy',
            'vec_fdd_sec', 'vec_fdd_ctl', 'vec_fdd_dst', 'vec_fdd_sp', 'drawChar', 'fillArea', 'MUSIC_Load', 'MUSIC_Stop', 'MUSIC_Init', 'vec_fade_out', 'vec_fade_in', 'vec_frect4', 'vec_slc_unp', 'vec_palsave', 'language', 'joystick_state', 'music_playing',
            'vec_kv_shadow', 'string_area', 'vec_pal_dirty', 'current_level', 'cls',
            'player_available_weapons', 'player_level', 'player_experience', 'player_current_weapon',
            'get_player_max_exp',
            # для оверлея паузы:
            'vec_ovl_call', 'vec_ovl_tgt', 'get_keyboard', 'inventory', 'inv_current_object',
            'force_inv_redraw', 'draw_weapon', 'RedrawScreen', 'InvalidateTiles', 'RedrawAllSprites',
            'FX_Play', 'get_entity_max_energy', 'remove_object_from_inventory', 'player_dead',
            'ENTITY_PLAYER_POINTER', 'z_iy', 'vec_palette', 'vec_pc_reset', 'vec_key', 'vec_key_hook',
            'vec_end_flag', 'vec_init_rev256', 'vec_slot_init', 'vec_bank_tab', 'vec_wpntab',
            'load_scorearea', 'CHECKPOINT_AREA', 'global_timer',
            'level_width', 'current_levelx', 'current_levely', 'z_ldir', 'vec_sp_save', 'rev256',
            # для оверлея готовых тайлов (fgc_ovl.asm):
            'drawTile', 'drawTile_nosave', 'vec_pool_on', 'SPDATA', 'fg_tile_pairs', 'fg_lut_n', 'vec_budget', 'vec_blit_src',
            'vec_blit_ret', 'vec_blit128_vram', 'vec_slot_tab',
            # для зеркального двухплоскостного блита в нулевой странице (zp_blit2m.asm):
            'vec_spr_hcol', 'vec_spr_dst', 'vec_col_cnt', 'vec_row_cnt', 'vec_spr_src', 'vec_spr_skip2',
            'vec_spr_port', 'vec_spr_ny', 'vec_spr_lbot', 'vec_spr_curport', 'vec_stk_leave']
    syms = {}
    for line in lst.split('\n'):
        m = re.match(r'^([A-Za-z_][\w.]*)\s+=\s+\$([0-9A-F]{4})', line)
        if m and m.group(1) in need:
            syms[m.group(1)] = int(m.group(2), 16)
    missing = [n for n in need if n not in syms]
    assert not missing, f'нет символов для меню: {missing}'
    # vfl_seek ставит сторону 1 через dec hl x2 от vec_fdd_sec; vfl_stream ловит конец буфера по старшему байту
    assert syms['vec_fdd_sec'] - syms['vec_fdd_ctl'] == 2, 'vec_fdd_ctl должен лежать за 2 байта до vec_fdd_sec'
    assert syms['string_area'] & 0xFF == 0, 'буфер сектора (string_area) должен быть выровнен по странице'
    out = ['; сгенерировано build_vec (символы игры для оверлея меню)']
    for line in lst.split('\n'):                      # константы набора уровня (SCRPAL, LEVELTAB_PORT...)
        m = re.match(r'^(SCRPAL|LEVELTAB_PORT|LEVELTAB|FDDCOPY|FDD_TAB|FDD_BANKCODE|WPN_SRC|WPN_ORG|WPN_LEN|FGC_CODE|FGC_PTRS|FGC_TILES|ZP_BLIT2M|ZPSRC)\s+=\s+\$([0-9A-F]{2,4})', line)
        if m: out.append(f'{m.group(1)}\tequ ${m.group(2)}')
    for n, v in syms.items():
        out.append(f'{n}\tequ ${v:04X}')
    out += [f'FB_ORG\tequ ${syms["string_area"] + 1216:04X}'   # загрузчик банков: за буфером сектора,
            ,                                                   # таблицей длин и рецептом
            f'MB_ORG\tequ ${syms["string_area"]:04X}', f'MB_TRK_MENU\tequ {DL.MENU_TRACK}', f'MB_SEC_MENU\tequ {DL.MENU_SEC}', f'MB_TRK_SLIDES\tequ {DL.PIC_TRACK}',
            f'MB_CREDITS\tequ ${CREDITS_ADDR:04X}']
    (ROOT / 'build/menu_syms.asm').write_text('\n'.join(out) + '\n')
    sys.path.insert(0, str(ROOT / 'tools/data'))
    from texts_ru import encode, MENU, INTRO, ENDING, CREDITS, THE_END_RU
    def db(label, text): return f"{label}:\tdb " + ','.join(str(b) for b in encode(text)) + ',0'
    ru = ['; сгенерировано build_vec из tools/data/texts_ru.py (кодировка шрифта: кириллица 96..127)',
          db('o_play_es', MENU['play']), db('o_pass_es', MENU['pass']), db('o_mus_es', MENU['music']),  # пункта языка нет
          db('t1s', INTRO[0]), db('t2s', INTRO[1]), db('t3s', INTRO[2]),
          db('e1s', ENDING[0]), db('e2s', ENDING[1]), db('e3s', ENDING[2]), db('oe_end_es', THE_END_RU),
          db('p_ask_es', MENU['pass_ask']), db('p_ok_es', MENU['pass_ok']), db('p_bad_es', MENU['pass_bad']),
          db('ovl_ptxt', 'НАЖМИ ПРОБЕЛ')]   # заставка загрузки: ovl_press, строка 11, колонки 10..21
    (ROOT / 'build/menu_ru.asm').write_text('\n'.join(ru) + '\n')
    # Титры (37 строк по 15 знаков) — отдельным блобом в квазидиске по MB_CREDITS: в окне оверлея
    # ($8440-$9000) на них нет места, а $9400 в странице 3 свободна (за загрузчиком банков).
    # Шаг записи 16 Б (15 знаков + 0), чтобы адрес строки считался сдвигом.
    cred = bytearray()
    for line in CREDITS:
        assert len(line) == 15, line
        cred += encode(line) + b'\0'
    assert len(cred) == 37*16
    (ROOT / 'build/credits.bin').write_bytes(bytes(cred))
    # строки меню паузы: рамочные коды как в оригинале (ianna.asm), текст EN/RU одной длины (17 знаков)
    from texts_ru import encode as _enc
    def pstr(pre, text, post):
        b = list(pre) + list(_enc(text)) + list(post)
        assert len(b) == 17, (text, len(b))
        return ','.join(str(x) for x in b)
    ps = ['; сгенерировано build_vec: строки меню паузы (рамка + подсказки)']
    EN = [([42,43,43,43,43,43], 'PAUSE',        [40,40,40,40,40,41]),
          ([60,91,92,32],       'INVENTORY',    [32,32,32,60]),
          ([60,93,94,32],       'USE OBJECT',   [32,32,60]),
          ([60,64,32,32],       'PICK WEAPON',  [32,60]),
          ([61,72,32,32],       'BACK',         [32,32,88,32,81,85,73,84,61]),
          ([42,43,43,43,43,43,43,43,32], '',    [40,40,40,40,40,40,40,41])]
    # ⚠️ коды 93,94 (в оригинале — иконка кнопки огня) в шрифте МЕНЮ складываются в испанское
    # «FUEGO»: в русском издании они убраны (2026-09-08). Коды 91,92 — стрелки, они нейтральны.
    RU = [([42,43,43,43,43,43], 'ПАУЗА',        [40,40,40,40,40,41]),
          ([60,91,92,32],       'ПРЕДМЕТЫ',     [32,32,32,32,60]),
          ([60,32,32,32],       'ПРИМЕНИТЬ',    [32,32,32,60]),   # 93,94 в шрифте меню — картинка
          ([60,64,32,32],       'ОРУЖИЕ',       [32,32,32,32,32,32,60]),
          ([61] + list(_enc('ВК')) + [32], 'ИГРА', [32] + list(_enc('СС МЕНЮ')) + [61]),   # клавиши Вектора: ВК — назад в игру, СС — в главное меню
          ([42,43,43,43,43,43,43,43,32], '',    [40,40,40,40,40,40,40,41])]
    for i, (pre, t, post) in enumerate(EN): ps.append(f'pz_en{i}:\tdb ' + pstr(pre, t, post) + ',0')
    for i, (pre, t, post) in enumerate(RU): ps.append(f'pz_ru{i}:\tdb ' + pstr(pre, t, post) + ',0')
    ps.append('pz_strings_en:\tdw ' + ','.join(f'pz_en{i}' for i in range(6)))
    ps.append('pz_strings_ru:\tdw ' + ','.join(f'pz_ru{i}' for i in range(6)))
    (ROOT / 'build/pause_str.asm').write_text('\n'.join(ps) + '\n')
    # полосы валика меню: каждая его строка одного цвета -> фон под пунктами восстанавливается
    # заливкой байтами-константами (без чтения квазидиска и без DI), а не копией из квазидиска
    from build_edd import sr5_rows as _sr5
    from pletter import depack as _pd
    _menu = _sr5(_pd((SRC / 'menu_screen.SR5.plet1').read_bytes()), 192)
    _rows = []
    for y in range(144, 176):
        from build_menu import PERM as _PERM   # цвета картинок переставлены под слоты Вектора
        c = _PERM[_menu[y][120]]   # середина валика: края попадают на декор
        _rows.append([0xFF if (c >> (3 - p)) & 1 else 0x00 for p in range(4)])
    st = ['; сгенерировано build_vec: полосы валика (32 строки x 4 плоскости)', 'ovl_stripes:']
    for p in range(4):
        st.append('\tdb ' + ','.join(str(_rows[y][p]) for y in range(32)))
    (ROOT / 'build/menu_stripes.asm').write_text('\n'.join(st) + '\n')
    for src, binout, maxlen in ((VEC / 'menu_ram.asm', 'menu_ram.bin', 0x800),
                                (VEC / 'menu_ovl.asm', 'menu_ovl.bin', PAUSE_ADDR - 0x8440),
                                (VEC / 'pause_ovl.asm', 'pause_ovl.bin', PAUSE_END - PAUSE_ADDR),
                                (VEC / 'fdd_banks.asm', 'fdd_banks.bin', FDD_BANKCODE_END - FDD_BANKCODE),
                                (VEC / 'wpn_load.asm', 'wpn_load.bin', WPN_SRC_END - WPN_SRC),
                                (VEC / 'zp_blit2m.asm', 'zp.bin', 0x100 - 0x3B),
                                (ROOT / 'build/arkos_dat.asm', 'arkos_dat.bin', ARK_DAT_END - ARK_DAT),
                                (ROOT / 'build/arkos_ovl.asm', 'arkos.bin', ARK_END - ARK_ADDR)):
        work = ROOT / f'build/{src.name}'
        if src != work: work.write_text(src.read_text())
        r = subprocess.run([str(ZASM), '--8080', '-uwy', work.name, f'{binout}.lst', binout],
                           capture_output=True, text=True, cwd=str(ROOT / 'build'))
        if r.returncode != 0:
            print(f'МЕНЮ: ошибка сборки {src.name}:'); print((r.stdout + r.stderr)[-1200:]); sys.exit(1)
        if binout == 'arkos_dat.bin':            # метки данных плеера — его коду
            dl = (ROOT / 'build/arkos_dat.bin.lst').read_text(encoding='utf-8', errors='replace')
            eq = sorted({(m.group(1), m.group(2)) for m in re.finditer(r'^([A-Za-z_][A-Za-z_0-9]*)\s+= \$([0-9A-F]{4}) =', dl, re.M) if m.group(1) not in ('_end', '_size')})
            (ROOT / 'build/arkos_dat_syms.asm').write_text('; сгенерировано build_vec: метки данных плеера\n' + ''.join(f'{n}\tequ ${a}\n' for n, a in eq))
        blen = (ROOT / f'build/{binout}').stat().st_size
        assert blen <= maxlen, f'{binout}: {blen} > {maxlen}'
        print(f'меню: {binout} {blen} Б (лимит {maxlen})')

if __name__ == '__main__':
    sys.exit(main())
