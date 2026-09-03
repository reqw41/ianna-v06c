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

    # entities.asm, get_sprite_pointer_iy (453..457) и хвост get_sprite_pointer_ix (478..481) —
    # обе читают (ix+0)/(ix+1) и кладут пару в IY/IX. Перевод делал это четырьмя блоками
    # (два раза ld hl,(z_ix) с push/pop и два раза push af / ld (z_i?+n),a / pop af).
    # HL бережём стеком (оригинал его не портит, у функций десятки вызывающих), A не трогаем
    # вовсе (в get_sprite_pointer_ix он — результат строки 477), флаги ни одна команда не меняет.
    ('entities.asm', 454): ['push hl', 'ld hl,(z_ix)', 'ld e,(hl)'],      # ld e,(ix+0)
    ('entities.asm', 455): ['inc hl', 'ld d,(hl)'],                       # ld d,(ix+1)
    ('entities.asm', 456): ['ld h,d', 'ld l,e', 'ld (z_iy),hl', 'pop hl'],  # ld iyh,d / ld iyl,e
    ('entities.asm', 457): [],
    ('entities.asm', 478): ['push hl', 'ld hl,(z_ix)', 'ld e,(hl)'],      # ld e,(ix+0)
    ('entities.asm', 479): ['inc hl', 'ld d,(hl)'],                       # ld d,(ix+1)
    ('entities.asm', 480): ['ld h,d', 'ld l,e', 'ld (z_ix),hl', 'pop hl'],  # ld ixh,d / ld ixl,e
    ('entities.asm', 481): [],

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

    # ianna_main_src.asm, RunScripts и runs_object_loop (428..488) — тело тика: восемь сущностей,
    # у пяти объектов ещё и обход циклом. HL здесь не нужен ни на входе, ни на выходе (в оригинале
    # его всё равно портит run_script), поэтому все push hl/pop hl вокруг работы с z_ix/z_iy лишние,
    # а push ix / pop ix — это просто ld hl,(z_ix) / push hl и pop hl / ld (z_ix),hl.
    ('ianna_main_src.asm', 431): ['ld hl,ENTITY_PLAYER_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 434): ['ld hl,scratch_area_player', 'ld (z_iy),hl'],
    ('ianna_main_src.asm', 438): ['ld hl,ENTITY_PLAYER_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 444): ['ld hl,ENTITY_ENEMY1_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 445): ['ld a,(hl)'],                     # ld a,(ix+0); HL = z_ix
    ('ianna_main_src.asm', 446): ['inc hl', 'or (hl)'],             # or (ix+1)
    ('ianna_main_src.asm', 451): ['ld hl,scratch_area_enemy1', 'ld (z_iy),hl'],
    ('ianna_main_src.asm', 453): ['ld hl,ENTITY_ENEMY1_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 456): ['ld hl,ENTITY_ENEMY2_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 457): ['ld a,(hl)'],
    ('ianna_main_src.asm', 458): ['inc hl', 'or (hl)'],
    ('ianna_main_src.asm', 463): ['ld hl,scratch_area_enemy2', 'ld (z_iy),hl'],
    ('ianna_main_src.asm', 465): ['ld hl,ENTITY_ENEMY2_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 469): ['ld hl,ENTITY_OBJECT1_POINTER', 'ld (z_ix),hl'],
    ('ianna_main_src.asm', 470): ['ld hl,scratch_area_obj1', 'ld (z_iy),hl'],
    ('ianna_main_src.asm', 472): ['ld hl,(z_iy)', 'push hl'],       # push iy
    ('ianna_main_src.asm', 473): ['ld hl,(z_ix)', 'push hl'],       # push ix; HL остаётся z_ix
    ('ianna_main_src.asm', 475): ['ld a,(hl)'],                     # ld a,(ix+0) — push bc HL не трогает
    ('ianna_main_src.asm', 476): ['inc hl', 'or (hl)'],             # or (ix+1)
    ('ianna_main_src.asm', 481): ['pop hl', 'ld (z_ix),hl'],        # pop ix
    ('ianna_main_src.asm', 482): ['pop hl', 'ld (z_iy),hl'],        # pop iy
    ('ianna_main_src.asm', 484): ['ld hl,(z_ix)', 'add hl,de', 'ld (z_ix),hl'],   # add ix,de
    ('ianna_main_src.asm', 486): ['ld hl,(z_iy)', 'add hl,de', 'ld (z_iy),hl'],   # add iy,de

    # score_src.asm, draw_enemy_state (216..) — панель энергии обоих врагов, дважды за кадр
    # (waitforvblank) плюс полная перерисовка счёта. HL не параметр и не результат (вызывающие
    # задают только IX и A), внутри он живёт до строки 243, где его перезаписывает ld h,c.
    ('score_src.asm', 218): ['ld hl,(z_ix)', 'ld a,(hl)'],                # ld a,(ix+0)
    ('score_src.asm', 219): ['inc hl', 'or (hl)'],                        # or (ix+1); HL = z_ix+1
    ('score_src.asm', 221): ['inc hl', 'inc hl', 'inc hl', 'ld a,(hl)'],  # ld a,(ix+4)
    ('score_src.asm', 224): ['inc hl']*6 + ['ld a,(hl)'],                 # ld a,(ix+10); HL = z_ix+4
    ('score_src.asm', 239): ['ld hl,(z_ix)', 'ld (z_iy),hl'],             # push ix / pop iy = IY := IX
    ('score_src.asm', 240): [],
    ('score_src.asm', 242): ['ld hl,(z_ix)'] + ['inc hl']*4 + ['ld c,(hl)'],   # ld c,(ix+4)
    ('score_src.asm', 256): ['ld hl,(z_ix)'] + ['inc hl']*4 + ['ld e,(hl)'],   # ld e,(ix+4)

    # scripts.asm, get_enemy_rom_page (533..543) — тип врага лежит далеко, в (ix+10), поэтому
    # смещение прибавляем через A, а не десятью inc hl. Функция теперь портит HL; проверено, что
    # ни один из шести вызывающих (ianna.asm 652/664/702/709, scripts.asm 547, entities.asm 3304)
    # после неё HL не читает — все они либо задают его заново, либо сразу идут в функцию,
    # которая начинается с ld hl,(z_ix).
    ('scripts.asm', 534): ['ld hl,(z_ix)', 'ld a,l', 'add a,10', 'ld l,a', 'jp nc,$+4', 'inc h',
                           'ld a,(hl)'],                                  # ld a,(ix+10)

    # scripts.asm, action_patrol (184..234) — скрипт патрулирования обоих врагов каждый тик,
    # восемь обращений к (ix+5)/(iy+d) на вызов. HL здесь — указатель на скрипт (строка 185
    # ex de,hl), но живёт он только до строки 191: строка 199 кладёт в HL ENTITY_PLAYER_POINTER,
    # а после строки 202 HL больше нигде в функции не читается — ниже он свободен под указатель.
    ('scripts.asm', 187): ['push hl', 'ld hl,(z_ix)'] + ['inc hl']*5 + ['ld a,(hl)', 'pop hl'],
    ('scripts.asm', 195): ['ld hl,(z_ix)', 'ld e,(hl)'],                  # ld e,(ix+0)
    ('scripts.asm', 196): ['inc hl', 'ld d,(hl)'],                        # ld d,(ix+1)
    ('scripts.asm', 197): ['ld h,d', 'ld l,e', 'ld (z_iy),hl'],           # ld iyh,d / ld iyl,e
    ('scripts.asm', 198): [],
    ('scripts.asm', 208): ['ld hl,(z_iy)'] + ['inc hl']*4 + ['cp (hl)'],  # cp (iy+4)
    # 212 и 216 читают одно и то же поле подряд: between них только and/cp/jp — HL доживает
    ('scripts.asm', 212): ['ld hl,(z_ix)'] + ['inc hl']*5 + ['ld a,(hl)'],   # ld a,(ix+5)
    ('scripts.asm', 216): ['ld a,(hl)'],                                     # ld a,(ix+5)
    ('scripts.asm', 221): ['ld hl,(z_iy)', 'inc hl', 'inc hl', 'inc hl', 'sub (hl)'],  # sub (iy+3)
    ('scripts.asm', 231): ['ld hl,(z_iy)', 'inc hl', 'inc hl', 'inc hl', 'sub (hl)'],  # sub (iy+3)
    # в action_patrol_noplayer приходят с тремя разными HL (z_iy+4, z_iy+3, z_ix+5) — берём заново
    ('scripts.asm', 234): ['ld hl,(z_ix)'] + ['inc hl']*5 + ['ld a,(hl)'],   # ld a,(ix+5)

    # scripts.asm, check_stile_entity_overlap (1727..1751) — зовётся из десятка скриптов объектов
    # каждый тик, десять обращений к (ix+d)/(iy+d) на вызов. Три наблюдения:
    #  * HL функция и так не бережёт: внутри стоит call check_sprite_overlap, который его портит,
    #    поэтому push hl/ex (sp),hl вокруг каждой строки лишние;
    #  * IY здесь всегда simulatedsprite (строка 1730), значит (iy+3..6) — АБСОЛЮТНЫЕ адреса;
    #  * (ix+6) и (ix+7) читаются подряд, между ними только add a,a и запись по абсолютному адресу,
    #    так что указатель в HL доживает.
    # A на строках 1743/1744 портится (там кладётся 2): между 1744 и call check_sprite_overlap
    # A никто не читает — нативный check_sprite_overlap (src/vec/overlap_hot.asm) на входе сразу
    # грузит B и A из полей записей. Флаги: pop/ld (nn),hl/ld (hl),r их не трогают, поэтому CY,
    # который функция возвращает из check_sprite_overlap, доживает до ret (строка 1751).
    ('scripts.asm', 1728): ['ld hl,(z_ix)', 'push hl'],                   # push ix
    ('scripts.asm', 1729): ['ld hl,(z_iy)', 'push hl'],                   # push iy
    ('scripts.asm', 1730): ['ld hl,simulatedsprite', 'ld (z_iy),hl'],     # ld iy,simulatedsprite
    ('scripts.asm', 1731): ['ld hl,(z_ix)'] + ['inc hl']*6 + ['ld a,(hl)'],   # ld a,(ix+6)
    ('scripts.asm', 1736): ['ld (simulatedsprite+3),a'],                  # ld (iy+3),a
    ('scripts.asm', 1737): ['inc hl', 'ld a,(hl)'],                       # ld a,(ix+7); HL = z_ix+6
    ('scripts.asm', 1742): ['ld (simulatedsprite+4),a'],                  # ld (iy+4),a
    ('scripts.asm', 1743): ['ld a,2', 'ld (simulatedsprite+5),a'],        # ld (iy+5),2
    ('scripts.asm', 1744): ['ld (simulatedsprite+6),a'],                  # ld (iy+6),2
    # снятый со стека указатель на сущность нужен тут же (строки 1746/1747), а z_ix всё равно
    # перезаписывается строкой 1748 — промежуточное сохранение не нужно
    ('scripts.asm', 1745): ['pop hl'],                                    # pop ix
    ('scripts.asm', 1746): ['ld e,(hl)'],                                 # ld e,(ix+0)
    ('scripts.asm', 1747): ['inc hl', 'ld d,(hl)'],                       # ld d,(ix+1)
    ('scripts.asm', 1748): ['ld h,d', 'ld l,e', 'ld (z_ix),hl'],          # ld ixh,d / ld ixl,e
    ('scripts.asm', 1749): [],
    ('scripts.asm', 1751): ['pop hl', 'ld (z_ix),hl'],                    # pop ix (CY сохраняется)

    # drawsprite_src.asm, UpdateSprite (85..99) — вызывается на каждое движение любой сущности
    # (игрок + два врага + объекты), пять обращений к записи спрайта подряд. HL здесь занят новой
    # позицией в символах (строки 78/84), поэтому прячем его на стек, а запись адресуем одним
    # указателем: +3, +4, +5, +6, +7. Флаг перерисовки (ix+7) переехал со строки 85 на строку 99 —
    # между ними ни одного вызова и ни одного чтения SPDATA, порядок записей не наблюдаем.
    # Флаги: push/ld hl,(nn)/inc hl/ld (hl),n их не трогают, как и оригинальные ld (ix+d),n / ld r,(ix+d).
    ('drawsprite_src.asm', 85): ['push hl', 'ld hl,(z_ix)', 'inc hl', 'inc hl', 'inc hl'],  # -> +3
    ('drawsprite_src.asm', 86): ['ld a,(hl)'],                            # ld a,(ix+3)
    ('drawsprite_src.asm', 92): ['inc hl', 'ld a,(hl)'],                  # ld a,(ix+4)
    ('drawsprite_src.asm', 98): ['inc hl', 'ld d,(hl)'],                  # ld d,(ix+5)
    ('drawsprite_src.asm', 99): ['inc hl', 'ld e,(hl)',                   # ld e,(ix+6)
                                 'inc hl', 'ld (hl),1',                   # ld (ix+7),1 (со строки 85)
                                 'pop hl'],                               # HL = новая позиция
    # update_storenewpos (142..143): сюда приходят и по jr из Update_inv_two, и падением из
    # Update_inv. HL на входе разный (после InvalidateTiles — мусор), поэтому его бережём.
    ('drawsprite_src.asm', 142): ['push hl', 'ld hl,(z_ix)', 'inc hl', 'inc hl', 'inc hl',
                                  'ld (hl),b'],                           # ld (ix+3),b
    ('drawsprite_src.asm', 143): ['inc hl', 'ld (hl),c', 'pop hl'],       # ld (ix+4),c
}
