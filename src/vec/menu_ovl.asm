; menu_ovl.asm — оверлей фазы меню/интро. Исполняется ИЗ ОКНА квазидиска (стр.3, $8440-$9BFF,
; окно b6, порт $43). Все вызовы движка — через переходник блоба (mb_call закрывает окно).
; Блоб (menu_ram.asm) лежит по фиксированным адресам от MB_ORG (string_area).
	include "menu_syms.asm"
MB_CALL		equ MB_ORG+0
MB_SCREEN	equ MB_ORG+3
MB_SLIDE	equ MB_ORG+6
MB_SONG		equ MB_ORG+9
MB_SAVELVL	equ MB_ORG+12
MB_KEY		equ MB_ORG+15
MB_CHR		equ MB_ORG+18
MB_VSAVE	equ MB_ORG+21
MB_VREST	equ MB_ORG+24
MB_MCHR		equ MB_ORG+27
MB_WAVE		equ MB_ORG+30
MB_STRIPES	equ MB_ORG+33
	org $8440

ovl_entry:
	; скопировать блоб порт-примитивов из окна ($9800..$9FFF) в ОЗУ string_area
	ld hl,$9800
	ld de,MB_ORG
	ld bc,$0800
ovl_cp:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	ld a,b
	or c
	jp nz,ovl_cp
	call MB_SAVELVL		; песню уровня — в сторонку
	xor a
	call MB_SONG		; песня меню -> $C980
	ld a,13			; music_menu
	ld hl,MUSIC_Load
	call MB_CALL
	call ovl_dark		; погасить: загрузка идёт прямо в VRAM
	call MB_SCREEN		; экран меню с дискеты
	push af
	call ovl_light
	pop af
	jp nz,ovl_start		; дисковода нет (стенд) — сразу в игру
	xor a
	ld (ovl_opt),a
	ld (ovl_cred),a
	ld (ovl_ct),a
	call ovl_options
	call ovl_credit		; первый титр — сразу, не через 256 кадров
	call ovl_wrel		; дренаж: после автозагрузки скан может отдать фантомные нажатия
ovl_loop:
	ei
	halt
	call ovl_wave		; волна на отражении (как waveeffect оригинала)
	; кредиты: раз в ~128 кадров следующая строка
	ld a,(ovl_ct)
	inc a
	ld (ovl_ct),a
	jp nz,ovl_input
	call ovl_credit
	ld a,(ovl_cred)
	inc a
	cp 3
	jp nz,ovl_cr1
	xor a
ovl_cr1:
	ld (ovl_cred),a
ovl_input:
	ld a,(joystick_state)
	ld d,a
	and 1			; вверх
	jp nz,ovl_up
	ld a,d
	and 2			; вниз
	jp nz,ovl_down
	ld a,d
	and $10			; fire
	jp nz,ovl_fire
	jp ovl_loop
ovl_up:
	ld a,(ovl_opt)
	call ovl_prev3
	jp ovl_setopt
ovl_down:
	ld a,(ovl_opt)
	call ovl_next3
ovl_setopt:
	ld (ovl_opt),a
	call ovl_options
	call ovl_wrel
	jp ovl_loop
; РУССКОЕ ИЗДАНИЕ: пунктов три (ИГРАТЬ, ПАРОЛЬ, МУЗ./ЭФФ) — пункт выбора языка снят,
; поэтому кольцо обходится по модулю ТРИ, а не `and 3`.
ovl_next3:
	inc a
	cp 3
	ret c
	xor a
	ret
ovl_prev3:
	dec a
	ret p
	ld a,2
	ret
ovl_fire:
	call ovl_wrel
	ld a,(ovl_opt)
	or a
	jp z,ovl_start		; ИГРАТЬ
	cp 2
	jp z,ovl_music		; МУЗ./ЭФФ
	jp ovl_pass		; ПАРОЛЬ
ovl_music:
	ld a,(music_playing)
	xor 1
	ld (music_playing),a
	jp ovl_loop

; --- запуск: интро-слайды и выход в игру ---
ovl_start:
	ld a,1
	call MB_SONG		; песня интро
	ld a,12			; music_intro
	ld hl,MUSIC_Load
	call MB_CALL
	xor a
	ld (ovl_slide),a
ovl_sl:
	ld a,(ovl_slide)
	call ovl_dark
	call MB_SLIDE
	push af			; ovl_light портит флаги — результат загрузки сохраняем
	call ovl_light
	pop af
	jp nz,ovl_go		; дисковода нет — без слайдов
	; текст слайда (по языку)
	ld a,(ovl_slide)
	ld hl,ovl_txt_en
	push af
	ld a,(language)
	or a
	jp nz,ovl_sl1
	pop af
	ld hl,ovl_txt_es
	push af
ovl_sl1:
	pop af
	call ovl_tab3
	call ovl_wrap		; печать с переносами со строки 18
	call ovl_waitfire
	ld a,(ovl_slide)
	inc a
	ld (ovl_slide),a
	cp 3
	jp nz,ovl_sl
ovl_go:
	ld hl,MUSIC_Stop	; заглушить AY
	call MB_CALL
	ld hl,MUSIC_Init
	call MB_CALL
	ld a,2
	call MB_SONG		; вернуть песню уровня
	ld hl,cls
	call MB_CALL		; VRAM вне игрового поля чистой (рамка слайда/меню)
	ret			; в vec_menu_phase -> begin_level

; --- пункты меню: 4 строки на синей полосе (11..14), стрелка у выбранного ---
ovl_options:
	push af
	ld hl,ovl_stripes	; фон валика — заливка полосами (быстро, без DI и без квазидиска)
	ld b,11
	ld c,18
	ld d,10			; ровно валик: x=88..167 (колонки 11..20)
	ld e,4
	call MB_STRIPES
	pop af
ovl_opts_only:			; только пункты (для экрана пароля: строку 19 занимает приглашение)
	; как в оригинале: предыдущий пункт сверху, текущий двойной высоты, следующий снизу
	ld a,(ovl_opt)
	call ovl_prev3
	ld c,18
	ld e,0
	call ovl_opt_print
	ld a,(ovl_opt)
	ld c,19
	ld e,1			; текущий — двойная высота (строки 15-16)
	call ovl_opt_print
	ld a,(ovl_opt)
	call ovl_next3
	ld c,21
	ld e,0
	call ovl_opt_print
	ret

; A = номер пункта, C = строка, E = 1 -> двойная высота
ovl_opt_print:
	push bc
	push de
	ld hl,ovl_opts_en
	ld d,a
	ld a,(language)
	or a
	ld a,d
	jp nz,ovl_op1
	ld hl,ovl_opts_es
ovl_op1:
	call ovl_tab3		; HL = строка пункта
	pop de
	pop bc
	ld b,12			; валик 88..168: текст 8 знаков по центру -> колонка 12 (как в оригинале)
ovl_op2:
	ld a,(hl)
	or a
	ret z
	push hl
	push bc
	push de
	ld d,e			; D = флаг двойной высоты для mb_mchr
	call MB_MCHR
	pop de
	pop bc
	pop hl
	inc hl
	inc b
	jp ovl_op2

; --- помощники ---
ovl_wave:			; 8 строк отражения за кадр, полный проход за 5 кадров
	ld a,(ovl_wy)
	ld b,a
	ld c,8
	ld a,(ovl_wph)
	call MB_WAVE
	ld a,(ovl_wy)
	add a,8
	cp 112+40
	jp c,ovl_wv1
	ld a,112		; полоса отражения оригинала y=80..119 + сдвиг картинки 32
	push af
	ld a,(ovl_wph)
	inc a
	and 15
	ld (ovl_wph),a		; фаза бежит — волна движется
	pop af
ovl_wv1:
	ld (ovl_wy),a
	ret
ovl_wy:		db 112
ovl_wph:	db 0


; --- гашение экрана на время загрузки с дискеты (иначе видно, как картинка рисуется) ---
ovl_dark:
	ld hl,vec_palette
	ld de,ovl_palsave
	ld b,16
ovl_dk1:
	ld a,(hl)
	ld (de),a
	xor a
	ld (hl),a		; всё чёрное
	inc hl
	inc de
	dec b
	jp nz,ovl_dk1
	jp ovl_palapply
ovl_light:
	ld hl,ovl_palsave
	ld de,vec_palette
	ld b,16
ovl_lt1:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec b
	jp nz,ovl_lt1
ovl_palapply:
	ld a,1
	ld (vec_pal_dirty),a	; ISR перепишет палитру в ближайшем кадре
	ei
	halt
	halt
	ret
ovl_palsave:	ds 16

ovl_credit:			; строка титров (23): три записи по 16 знаков с колонки 8 — как в оригинале,
	push af			; они одинаковой длины и затирают друг друга сами, очистка не нужна
	ld hl,vec_pc_reset	; строки 20..23 — область панели: у drawChar там кэш «по изменению»
	call MB_CALL
	ld a,(ovl_cred)
	ld hl,ovl_credtab
	call ovl_tab3
	ld b,8
	ld c,23
	call ovl_printf
	pop af
	ret
ovl_tab3:			; HL = таблица dw, A = индекс -> HL = элемент
	add a,a
	ld e,a
	ld d,0
	add hl,de
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	ret
ovl_printf:			; HL = ASCIIZ, B = x, C = y — НЕПРОЗРАЧНО (drawChar движка, фон шрифта чёрный),
ovl_pf_loop:			; как print_string3 -> drawCharFront оригинала
	ld a,(hl)
	or a
	ret z
	push hl
	push bc
	ld hl,drawChar
	call MB_CALL
	pop bc
	pop hl
	inc hl
	inc b
	jp ovl_pf_loop

ovl_print_c:			; HL = ASCIIZ, C = строка: печать по центру экрана (32 колонки)
	push hl
	ld b,0
ovl_pc1:
	ld a,(hl)
	or a
	jp z,ovl_pc2
	inc hl
	inc b
	jp ovl_pc1
ovl_pc2:
	ld a,32
	sub b
	rrca
	and $7F			; (32 - длина) / 2
	ld b,a
	pop hl
	jp ovl_printf		; нижняя строка — непрозрачно, как в оригинале

ovl_print:			; HL = ASCIIZ, B = x, C = y
	ld a,(hl)
	or a
	ret z
	push hl
	push bc
	call MB_CHR
	pop bc
	pop hl
	inc hl
	inc b
	jp ovl_print
ovl_wrap:			; HL = длинный текст, печать с колонки 1, строки 18, ширина 30
	ld b,1
	ld c,18
ovl_w1:
	ld a,(hl)
	or a
	ret z
	cp ' '
	jp nz,ovl_w2
	; пробел: если следующее слово не влезает — перенос
	push hl
	push bc
	ld d,0
ovl_wl:
	inc hl
	inc d
	ld a,(hl)
	or a
	jp z,ovl_wl1
	cp ' '
	jp nz,ovl_wl
ovl_wl1:
	pop bc
	ld a,b
	add a,d
	cp 31
	pop hl
	jp c,ovl_w2
	inc hl			; пробел съесть
	ld b,1
	inc c
	jp ovl_w1
ovl_w2:
	ld a,(hl)		; символ (A затёрт проверкой переноса)
	push hl
	push bc
	call MB_CHR
	pop bc
	pop hl
	inc hl
	inc b
	ld a,b
	cp 31
	jp c,ovl_w1
	ld b,1
	inc c
	jp ovl_w1
ovl_waitfire:			; ~340 кадров или fire (с отпусканием)
	ld bc,340
ovl_wf1:
	ei
	halt
	ld a,(joystick_state)
	and $10
	jp nz,ovl_wrel
	dec bc
	ld a,b
	or c
	jp nz,ovl_wf1
	ret
ovl_wrel:
	ei
	halt
	ld a,(joystick_state)
	and $13
	jp nz,ovl_wrel
	ret

ovl_opt:	db 0
ovl_row:	db 0
ovl_cred:	db 0
ovl_ct:		db 0
ovl_slide:	db 0

ovl_opts_en:	dw o_play,o_pass,o_mus			; РУССКОЕ ИЗДАНИЕ: пункта языка нет
ovl_opts_es:	dw o_play_es,o_pass_es,o_mus_es		; language всегда 0: русский (menu_ru.asm)
o_play:		db "  PLAY  ",0
o_pass:		db "PASSWORD",0
o_mus:		db "MUSIC/FX",0
ovl_credtab:	dw c_code,c_art,c_snd
c_code:		db "  CODE: UTOPIAN ",0
c_art:		db "ART: PAGANTIPACO",0
c_snd:		db "  SOUND: MCALBY ",0

ovl_txt_en:	dw t1e,t2e,t3e
ovl_txt_es:	dw t1s,t2s,t3s
t1e: db "A LONG TIME AGO, THE WORLD WAS RULED BY THE NOCUOUS LORD OF CHAOS.",0
t2e: db "THE GODDESS IANNA APPOINTED TUKARAM TO WIELD THE SACRED SWORD THAT COULD DEFEAT EVILNESS.",0
t3e: db "TUKARAM BROUGHT PEACE TO OUR LANDS, AND HIS LINEAGE WAS BLESSED AS SERVANTS OF THE GODDESS.",0

; ---- экран пароля: ввод 10 шестнадцатеричных знаков в строке 19, как в оригинале ----
; формат (menu.asm): [0] младший ниббл = уровень, биты 7..4 = доступное оружие; [1] уровень героя;
; [2] опыт; [3] текущее оружие; [4] контрольная сумма (сумма [0..3]). Байты 0..3 хранятся XOR $55.
ovl_pass:
	ld hl,MB_KEY		; включить сканер клавиатуры в ISR (VBlank)
	ld (vec_key_hook),hl
	call ovl_clr19
	ld hl,ovl_p_ask_en
	ld a,(language)
	or a
	jp nz,ovl_p1
	ld hl,p_ask_es
ovl_p1:
	ld b,7			; «ПАРОЛЬ:» + пробел + 10 знаков = 18 -> с колонки 7 (по центру)
	ld c,23
	call ovl_printf
	; буфер = 10 пробелов
	ld hl,ovl_pbuf
	ld b,10
	ld a,' '
ovl_p2:
	ld (hl),a
	inc hl
	dec b
	jp nz,ovl_p2
	xor a
	ld (ovl_pn),a
ovl_p_loop:
	ei
	halt
	ld a,(vec_key)		; клавишу читает ISR (хук) — сканировать посреди кадра нельзя: дёргается скролл
	or a
	jp z,ovl_p_loop
	cp 13
	jp z,ovl_p_check
	ld (ovl_pch),a		; mb_key портит C — хранить знак в памяти
	call ovl_p_wrel		; дождаться отпускания (иначе символ повторится)
	ld a,(ovl_pn)
	cp 10
	jp z,ovl_p_loop		; буфер полон — ждём ВК
	ld e,a
	ld d,0
	ld hl,ovl_pbuf
	add hl,de
	ld a,(ovl_pch)
	ld (hl),a
	ld a,e
	inc a
	ld (ovl_pn),a
	; показать введённое
	ld hl,ovl_pbuf
	ld b,16			; поле ввода сразу за приглашением
	ld c,23
	call ovl_print10
	jp ovl_p_loop
ovl_p_wrel:
	ei
	halt
	ld a,(vec_key)
	or a
	jp nz,ovl_p_wrel
	ret
; печать ровно 10 знаков буфера
ovl_print10:
	ld d,10
ovl_p10:
	ld a,(hl)
	push hl
	push bc
	push de
	call MB_CHR
	pop de
	pop bc
	pop hl
	inc hl
	inc b
	dec d
	jp nz,ovl_p10
	ret
; --- проверка ---
ovl_p_check:
	ld a,(ovl_pn)
	cp 10
	jp nz,ovl_p_fail	; введено меньше 10 знаков
	ld hl,ovl_pbuf
	ld de,ovl_pval
	ld b,5
ovl_p_conv:
	push bc
	call ovl_hex2		; A = байт из двух знаков (HL двигается)
	pop bc
	ld (de),a
	inc de
	dec b
	jp nz,ovl_p_conv
	; байты 0..3 расшифровать (XOR $55), сумму — нет
	ld hl,ovl_pval
	ld b,4
	xor a
	ld c,a			; C = контрольная сумма
ovl_p_xor:
	ld a,(hl)
	xor $55
	ld (hl),a
	add a,c
	ld c,a
	inc hl
	dec b
	jp nz,ovl_p_xor
	ld a,(ovl_pval+4)
	cp c
	jp nz,ovl_p_fail
	; уровень < 8 и базовый меч на месте
	ld a,(ovl_pval)
	and $0F
	cp 8
	jp nc,ovl_p_fail
	ld a,(ovl_pval)
	and $80
	jp z,ovl_p_fail
	ld a,(ovl_pval+1)	; уровень героя < 8
	cp 8
	jp nc,ovl_p_fail
	; опыт не больше максимума для уровня героя
	ld a,(ovl_pval+1)
	ld hl,get_player_max_exp
	call MB_CALL
	ld b,a
	ld a,(ovl_pval+2)
	cp b
	jp z,ovl_p_ok
	jp nc,ovl_p_fail
ovl_p_ok:
	; применить (DECODE оригинала)
	ld a,(ovl_pval)
	and $0F
	ld (current_level),a
	ld hl,player_available_weapons
	xor a
	ld (hl),a
	inc hl
	ld (hl),a
	inc hl
	ld (hl),a
	inc hl
	ld (hl),a
	ld a,(ovl_pval)
	ld c,a
	ld hl,player_available_weapons
	ld b,4
	ld e,$80
ovl_p_wp:
	ld a,c
	and e
	jp z,ovl_p_wp1
	ld (hl),1
ovl_p_wp1:
	inc hl
	ld a,e
	rrca
	ld e,a
	dec b
	jp nz,ovl_p_wp
	ld a,(ovl_pval+1)
	ld (player_level),a
	ld a,(ovl_pval+2)
	ld (player_experience),a
	ld a,(ovl_pval+3)
	ld (player_current_weapon),a
	ld hl,ovl_p_ok_en
	ld a,(language)
	or a
	jp nz,ovl_p_okp
	ld hl,p_ok_es
ovl_p_okp:
	push hl
	ld hl,0
	ld (vec_key_hook),hl	; сканер больше не нужен
	pop hl
	call ovl_p_msg
	jp ovl_start		; пароль принят — в игру
ovl_p_fail:
	ld hl,ovl_p_bad_en
	ld a,(language)
	or a
	jp nz,ovl_p_badp
	ld hl,p_bad_es
ovl_p_badp:
	push hl
	ld hl,0
	ld (vec_key_hook),hl	; сканер больше не нужен
	pop hl
	call ovl_p_msg
	call ovl_options	; вернуть пункты
	call ovl_credit		; и кредиты вместо сообщения
	jp ovl_loop
; сообщение в строке 19 + ожидание огня
ovl_p_msg:
	push hl
	call ovl_clr19
	pop hl
	ld c,23
	call ovl_print_c
	call ovl_wrel
ovl_p_m1:
	ei
	halt
	ld a,(joystick_state)
	and $10
	jp z,ovl_p_m1
	call ovl_wrel
	call ovl_clr19
	ret
; два знака (HL) -> байт A
ovl_hex2:
	call ovl_hex1
	rlca
	rlca
	rlca
	rlca
	ld c,a
	call ovl_hex1
	or c
	ret
ovl_hex1:
	ld a,(hl)
	inc hl
	sub '0'
	cp 10
	ret c
	sub 7			; 'A'..'F' -> 10..15
	ret
; вернуть фон меню (строки 18..23) из копии в квазидиске
ovl_clr19:			; menu_cleancreditsattr оригинала: строка 23 забивается пробелами
	ld hl,vec_pc_reset
	call MB_CALL
	ld b,0
ovl_c19:
	push bc
	ld a,' '
	ld c,23
	ld hl,drawChar
	call MB_CALL
	pop bc
	inc b
	ld a,b
	cp 32
	jp nz,ovl_c19
	ret
ovl_pn:		db 0
ovl_pch:	db 0
ovl_pbuf:	ds 10
ovl_pval:	ds 5
ovl_p_ask_en:	db "PASSWORD:",0
ovl_p_ok_en:	db "  PASSWORD OK  ",0
ovl_p_bad_en:	db "INVALID PASSWORD",0
	include "menu_ru.asm"
	include "menu_stripes.asm"
