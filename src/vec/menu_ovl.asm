; menu_ovl.asm — оверлей фазы меню/интро. Исполняется ИЗ ОКНА квазидиска (стр.3, $8440-$9BFF,
; окно b6, порт $43). Все вызовы движка — через переходник блоба (mb_call закрывает окно).
; Блоб (menu_ram.asm) лежит по фиксированным адресам от MB_ORG (string_area).
	include "menu_syms.asm"
MB_CALL		equ MB_ORG+0
MB_SCREEN	equ MB_ORG+3
MB_SLIDE	equ MB_ORG+6
MB_SONG		equ MB_ORG+9
MB_SAVELVL	equ MB_ORG+12
	org $8440

ovl_entry:
	; скопировать блоб порт-примитивов из окна ($9C00..$9FFF) в ОЗУ string_area
	ld hl,$9C00
	ld de,MB_ORG
	ld bc,$0400
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
	call MB_SCREEN		; экран меню с дискеты
	jp nz,ovl_start		; дисковода нет (стенд) — сразу в игру
	xor a
	ld (ovl_opt),a
	ld (ovl_cred),a
	ld (ovl_ct),a
	call ovl_options
	call ovl_wrel		; дренаж: после автозагрузки скан может отдать фантомные нажатия
ovl_loop:
	ei
	halt
	; кредиты: раз в ~128 кадров следующая строка
	ld a,(ovl_ct)
	inc a
	ld (ovl_ct),a
	jp nz,ovl_input
	ld a,(ovl_cred)
	ld hl,ovl_credtab
	call ovl_tab3
	ld b,8
	ld c,23
	call ovl_print
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
	dec a
	and 3
	jp ovl_setopt
ovl_down:
	ld a,(ovl_opt)
	inc a
	and 3
ovl_setopt:
	ld (ovl_opt),a
	call ovl_options
	call ovl_wrel
	jp ovl_loop
ovl_fire:
	call ovl_wrel
	ld a,(ovl_opt)
	or a
	jp z,ovl_start		; PLAY
	cp 2
	jp z,ovl_lang		; LANGUAGE
	cp 3
	jp z,ovl_music		; MUSIC/FX
	jp ovl_loop		; PASSWORD — в следующей итерации
ovl_lang:
	ld a,(language)
	xor 1
	ld (language),a
	call ovl_options
	jp ovl_loop
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
	call MB_SLIDE
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
	ld a,2
	call MB_SONG		; вернуть песню уровня
	ld hl,cls
	call MB_CALL		; VRAM вне игрового поля чистой (рамка слайда/меню)
	ret			; в vec_menu_phase -> begin_level

; --- пункты меню: 4 строки на синей полосе (11..14), стрелка у выбранного ---
ovl_options:
	xor a
	ld (ovl_row),a
ovl_o1:
	ld a,(ovl_row)
	ld hl,ovl_opts_en
	push af
	ld a,(language)
	or a
	jp nz,ovl_o2
	pop af
	ld hl,ovl_opts_es
	push af
ovl_o2:
	pop af
	call ovl_tab3		; HL = строка A (таблица из 4)
	ld a,(ovl_row)
	add a,11
	ld c,a
	ld b,11
	call ovl_print
	; стрелки
	ld a,(ovl_row)
	ld d,a
	ld a,(ovl_opt)
	cp d
	ld a,'>'
	jp z,ovl_o3
	ld a,' '
ovl_o3:
	push af
	ld a,(ovl_row)
	add a,11
	ld c,a
	ld b,9
	pop af
	push bc
	ld hl,drawChar
	call MB_CALL
	pop bc
	ld a,(ovl_row)
	inc a
	ld (ovl_row),a
	cp 4
	jp nz,ovl_o1
	ret

; --- помощники ---
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
ovl_print:			; HL = ASCIIZ, B = x, C = y
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
	ld hl,drawChar
	call MB_CALL
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

ovl_opts_en:	dw o_play,o_pass,o_eng,o_mus
ovl_opts_es:	dw o_play_es,o_pass,o_esp,o_mus
o_play:		db "  PLAY  ",0
o_play_es:	db " JUGAR  ",0
o_pass:		db "PASSWORD",0
o_eng:		db "ENGLISH ",0
o_esp:		db "ESPANOL ",0
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
t1s: db "HACE TIEMPO, EL MUNDO ESTUVO DOMINADO POR EL SENOR DEL CAOS.",0
t2s: db "ANTE TAL SITUACION, LA DIOSA IANNA ELIGIO A TUKARAM PARA PORTAR LA ESPADA SAGRADA QUE ELIMINARIA EL MAL.",0
t3s: db "TUKARAM CONSIGUIO TRAER LA PAZ A NUESTRAS TIERRAS, SIENDO SU ESTIRPE BENDECIDA COMO SIERVOS DE LA DIOSA.",0
