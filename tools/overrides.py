# Ручные замены для мест, где автоматический перевод даёт неточные флаги.
# Ключ: (имя файла, номер строки оригинала). Значение: список строк i8080-кода.
OVERRIDES = {
    # score_src.asm (препроцессированный score.asm): `score_gameover_string: db "   PULSA DISPARO",0` -> русский (language=0), кодировка шрифта
    ('score_src.asm', 391): ['db 32,32,32,109,96,102,108,104,32,110,99,110,109,124,32,32,0'],
    # depack.asm: `rl c` / `jr nc,apget4bits` / `ld a,b` / `jr z,apwritebyte`
    # Z80: Z после rl c = (C==0). i8080 RAL не ставит Z -> считаем явно перед ld a,b.
    ('depack.asm', 20): ['ld (z_a),a', 'ld a,c', 'rla', 'ld c,a', 'ld a,(z_a)'],   # A = битовый буфер, беречь!
    ('depack.asm', 22): ['ld a,c', 'or a', 'ld a,b'],          # Z=(C==0), CY здесь дальше не нужен (and a)
    # depack.asm: `ld c,(hl)` / `rr c` / `ret z` / ... `ld a,2` / `adc a,b`
    # нужны и Z (C==0 -> конец потока), и CY (младший бит) для adc.
    ('depack.asm', 34): ['ld a,c', 'rra', 'ld c,a', 'push af', 'or a', 'jp nz,apb3_nz', 'pop af', 'ret', 'apb3_nz:', 'pop af'],
    ('depack.asm', 35): [],

    # tiles_src.asm: три цикла отрисовки тайлов экрана вида `push bc / exx / pop bc / call X / exx` —
    # идиома «вызвать X с BC, сохранив BC/DE/HL основного набора». Перевод давал два z_exx на тайл
    # (~300 тактов, 5.9 % тактов на сценах с двумя орками). Альтернативный набор после цикла нигде не
    # читается, флаги следом ставит dec b / inc b, так что стек делает то же самое втрое дешевле.
    ('tiles_src.asm', 34): ['push hl', 'push de', 'push bc'],      # drawsc_x_loop
    ('tiles_src.asm', 35): [],
    ('tiles_src.asm', 36): [],
    ('tiles_src.asm', 38): ['pop bc', 'pop de', 'pop hl'],
    ('tiles_src.asm', 47): ['push hl', 'push de', 'push bc'],      # drawsc_x_loop_fg
    ('tiles_src.asm', 48): [],
    ('tiles_src.asm', 49): [],
    ('tiles_src.asm', 51): ['pop bc', 'pop de', 'pop hl'],
    ('tiles_src.asm', 258): ['push hl', 'push de', 'push bc'],     # dirty_x_loop_2 (CopyTile)
    ('tiles_src.asm', 259): [],
    ('tiles_src.asm', 260): [],
    ('tiles_src.asm', 262): ['pop bc', 'pop de', 'pop hl'],

    # entities.asm, начало entity_gravity (178..185) — выполняется на КАЖДОМ вызове (игрок и два
    # врага за тик). Перевод читал три поля тремя хелперами (~144 такта каждый, z_ix_hl дороже);
    # здесь запись сущности один раз берётся в HL и поля адресуются инкрементами. HL на входе не
    # нужен (CheckGravities его не читает), а между строками 182 и 185 стоят только ret z и cp —
    # HL они не трогают, поэтому указатель доживает до поля +5.
    ('entities.asm', 182): ['ld hl,(z_ix)', 'ld a,(hl)'],                 # ld a,(ix+0)
    ('entities.asm', 183): ['inc hl', 'or (hl)'],                          # or (ix+1); HL = z_ix+1
    ('entities.asm', 185): ['inc hl', 'inc hl', 'inc hl', 'inc hl', 'ld a,(hl)'],  # ld a,(ix+5)
    # ветка «уже падаем» (208..232): HL доживает от строки 185 (между ними только cp/ret z/jr)
    ('entities.asm', 210): ['inc hl', 'ld a,(hl)'],                        # ld a,(ix+6); HL = z_ix+6
    # после call/pop ix указатель в HL уже не тот — берём заново
    ('entities.asm', 220): ['ld hl,(z_ix)', 'inc hl', 'inc hl', 'inc hl', 'inc hl', 'inc hl', 'ld a,(hl)'],
    # entity_fall_notfallingyet (234..255): три чтения и две записи полей одной сущности.
    # 240 и 245 берут указатель заново (перед ними call entity_checkgravity и условный
    # call clean_second_sprite), а 251/254/255 живут на HL от 245: and/cp/jr/add его не трогают.
    ('entities.asm', 240): ['ld hl,(z_ix)'] + ['inc hl']*7 + ['ld a,(hl)'],   # ld a,(ix+7)
    ('entities.asm', 245): ['ld hl,(z_ix)'] + ['inc hl']*5 + ['ld a,(hl)'],   # ld a,(ix+5)
    ('entities.asm', 251): ['ld a,(hl)'],                                     # ld a,(ix+5); HL = z_ix+5
    ('entities.asm', 254): ['ld (hl),a'],                                     # ld (ix+5),a
    ('entities.asm', 255): ['inc hl', 'ld (hl),0'],                           # ld (ix+6),0
    # после entity_move указатель берём заново
    ('entities.asm', 268): ['ld hl,(z_ix)', 'ld a,(hl)'],                     # ld a,(ix+0)
    ('entities.asm', 269): ['inc hl', 'or (hl)'],                             # or (ix+1)
    # entity_dontfall / entity_finishedfalling: вход только по jp z из 281/283, HL доживает
    ('entities.asm', 279): ['ld hl,(z_ix)'] + ['inc hl']*5 + ['ld a,(hl)'],   # ld a,(ix+5)
    ('entities.asm', 291): ['ld a,(hl)'],                                     # ld a,(ix+5); HL = z_ix+5
    ('entities.asm', 294): ['ld (hl),a'],                                     # ld (ix+5),a

    # scripts.asm, run_script (128..179) — вызывается для игрока, обоих врагов и пяти объектов
    # каждый тик. HL на входе не параметр (RunScripts его не передаёт) и до строки 136 не нужен,
    # поэтому указатель сущности живёт прямо в нём.
    ('scripts.asm', 131): ['ld hl,(z_ix)', 'ld (entity_current),hl'],   # ld (entity_current),ix
    ('scripts.asm', 132): ['inc hl', 'inc hl', 'ld a,(hl)'],            # ld a,(ix+2); HL = z_ix
    # здесь HL занят указателем на скрипт — сохраняем его на стеке (всё равно втрое дешевле хелпера)
    ('scripts.asm', 142): ['push hl', 'ld hl,(z_ix)', 'inc hl', 'inc hl', 'inc hl', 'ld c,(hl)', 'pop hl'],
    # после IndCall старый HL никому не нужен: строки 171-172 всё равно кладут в него IY
    ('scripts.asm', 168): ['ld hl,(z_ix)', 'inc hl', 'inc hl', 'inc hl', 'add a,(hl)'],  # add a,(ix+3)
    ('scripts.asm', 169): ['ld (hl),a'],                                # ld (ix+3),a
    ('scripts.asm', 171): ['ld hl,(z_iy)'],                             # push iy / pop hl = HL := IY
    ('scripts.asm', 172): [],
}
