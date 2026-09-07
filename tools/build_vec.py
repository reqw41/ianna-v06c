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
    old = '\tld a, (current_level)\n\tcall MUSIC_Load\n'
    assert old in text, 'MUSIC_Load в game'
    text = text.replace(old, old + '\txor a\t; ВЕКТОР: сбросить шум и огибающую от песни меню/интро\n'
                                   '\tld (_atVAR_Reg6), a\n\tld (_atVAR_Reg11), a\n\tld (_atVAR_Reg12), a\n')
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
    # ВЕКТОР: плеер Arkos — НЕ перевод Z80-исходника, а нативный i8080 (src/vec/arkos_hot.asm),
    # написанный по спецификации tools/arkos_model.py. Оригинал ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm
    # остался только эталоном: по нему сверяются гейты tests/music/check_all.py и сама модель.
    (TR / 'arkos.asm').write_text((VEC / 'arkos_hot.asm').read_text(encoding='utf-8'))

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
    for name, addr in (('menu_ovl.bin', 0x8440), ('pause_ovl.bin', 0x9000), ('menu_ram.bin', 0x9800)):
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
    мёртвого кода в образе фактически нет — см. ANALYSIS.md, «резерв мёртвого кода оказался мифом».
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
    (TR / 'tiles.asm').write_text(t.replace(old, 'InvalidateSTiles:\n\tld a,c\t; ВЕКТОР: ряды панели не рисуются — прямоугольник не нужен\n\tcp 10\n\tret nc\n\tadd a,e\n\tcp 11\n\tjp c,ist_hok\n\tld a,10\n\tsub c\n\tld e,a\t; ряды 10-11 не копим: карты RedrawInvTiles на 10 рядов\nist_hok:\n\tpush de'))
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
              TR / 'score.asm', TR / 'font.asm'] + ([TR / 'music.asm', TR / 'arkos.asm'] if not DEMO else []) + [
              VEC / 'vec_vdp.asm', VEC / 'vec_isr.asm'] + ([VEC / 'vec_fdd.asm'] if C8 else []) + [VEC / 'vec_stubs.asm']
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
            if mm: code_end = max(code_end, int(mm.group(1), 16) + len(mm.group(2)) // 2)
        assert code_end <= VARS_ADDR, f'код до ${code_end:04X} НАЕХАЛ на переменные ${VARS_ADDR:04X}'
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
    need = ['depack', 'z_ldir', 'vfl_restore', 'vfl_seek', 'vfl_fill', 'vfl_stream',
            'vec_fdd_sec', 'vec_fdd_ctl', 'vec_fdd_dst', 'vec_fdd_sp', 'drawChar', 'fillArea', 'MUSIC_Load', 'MUSIC_Stop', 'MUSIC_Init', '_atVAR_Reg6', '_atVAR_Reg11', '_atVAR_Reg12', 'language', 'joystick_state', 'music_playing',
            'vec_kv_shadow', 'string_area', 'vec_pal_dirty', 'current_level', 'cls',
            'player_available_weapons', 'player_level', 'player_experience', 'player_current_weapon',
            'get_player_max_exp',
            # для оверлея паузы:
            'vec_ovl_call', 'vec_ovl_tgt', 'get_keyboard', 'inventory', 'inv_current_object',
            'force_inv_redraw', 'draw_weapon', 'RedrawScreen', 'InvalidateTiles', 'RedrawAllSprites',
            'FX_Play', 'get_entity_max_energy', 'remove_object_from_inventory', 'player_dead',
            'ENTITY_PLAYER_POINTER', 'z_iy', 'vec_palette', 'vec_pc_reset', 'vec_key', 'vec_key_hook',
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
    out = ['; сгенерировано build_vec (символы игры для оверлея меню)']
    for line in lst.split('\n'):                      # константы набора уровня (SCRPAL, LEVELTAB_PORT...)
        m = re.match(r'^(SCRPAL|LEVELTAB_PORT|LEVELTAB|FDD_TAB|FGC_CODE|FGC_PTRS|FGC_TILES|ZP_BLIT2M|ZPSRC)\s+=\s+\$([0-9A-F]{2,4})', line)
        if m: out.append(f'{m.group(1)}\tequ ${m.group(2)}')
    for n, v in syms.items():
        out.append(f'{n}\tequ ${v:04X}')
    out += [f'FB_ORG\tequ ${syms["string_area"] + 1216:04X}'   # загрузчик банков: за буфером сектора,
            ,                                                   # таблицей длин и рецептом
            f'MB_ORG\tequ ${syms["string_area"]:04X}', 'MB_TRK_MENU\tequ 3', 'MB_SEC_MENU\tequ 3', 'MB_TRK_SLIDES\tequ 75']
    (ROOT / 'build/menu_syms.asm').write_text('\n'.join(out) + '\n')
    sys.path.insert(0, str(ROOT / 'tools/data'))
    from texts_ru import encode, MENU, INTRO
    def db(label, text): return f"{label}:\tdb " + ','.join(str(b) for b in encode(text)) + ',0'
    ru = ['; сгенерировано build_vec из tools/data/texts_ru.py (кодировка шрифта: кириллица 96..127)',
          db('o_play_es', MENU['play']), db('o_pass_es', MENU['pass']), db('o_esp', MENU['lang']), db('o_mus_es', MENU['music']),
          db('t1s', INTRO[0]), db('t2s', INTRO[1]), db('t3s', INTRO[2]),
          db('p_ask_es', MENU['pass_ask']), db('p_ok_es', MENU['pass_ok']), db('p_bad_es', MENU['pass_bad'])]
    (ROOT / 'build/menu_ru.asm').write_text('\n'.join(ru) + '\n')
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
    RU = [([42,43,43,43,43,43], 'ПАУЗА',        [40,40,40,40,40,41]),
          ([60,91,92,32],       'ПРЕДМЕТЫ',     [32,32,32,32,60]),
          ([60,93,94,32],       'ПРИМЕНИТЬ',    [32,32,32,60]),
          ([60,64,32,32],       'ОРУЖИЕ',       [32,32,32,32,32,32,60]),
          ([61,72,32],          'НАЗАД',        [32,88,32] + list(_enc('ВЫХОД')) + [61]),
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
        c = _menu[y][120]   # середина валика: края попадают на декор
        _rows.append([0xFF if (c >> (3 - p)) & 1 else 0x00 for p in range(4)])
    st = ['; сгенерировано build_vec: полосы валика (32 строки x 4 плоскости)', 'ovl_stripes:']
    for p in range(4):
        st.append('\tdb ' + ','.join(str(_rows[y][p]) for y in range(32)))
    (ROOT / 'build/menu_stripes.asm').write_text('\n'.join(st) + '\n')
    for src, binout, maxlen in ((VEC / 'menu_ram.asm', 'menu_ram.bin', 0x800),
                                (VEC / 'menu_ovl.asm', 'menu_ovl.bin', 0x9000 - 0x8440),
                                (VEC / 'pause_ovl.asm', 'pause_ovl.bin', 0x9800 - 0x9000),
                                (VEC / 'fdd_banks.asm', 'fdd_banks.bin', 0x9600 - 0x9280),
                                (VEC / 'zp_blit2m.asm', 'zp.bin', 0x100 - 0x3B)):
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
