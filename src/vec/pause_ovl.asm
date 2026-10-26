; pause_ovl.asm — меню паузы (H в игре). Исполняется ИЗ ОКНА квазидиска (стр.3 $8B00, окно b6, порт $43).
; В ROM не влезло (не хватало ~420 Б), поэтому живёт здесь; функции движка вызываются через
; переходник vec_ovl_call (он закрывает окно на время вызова и возвращает его перед возвратом сюда:
; возврат идёт в код, который виден только при открытом окне).
; Логика повторяет pause_menu оригинала (ianna.asm): рамка с подсказками, выбор предмета влево/вправо,
; применение предмета огнём, смена оружия вниз, H — назад в игру; выход в главное меню — АР2 (в оригинале X).
	include "menu_syms.asm"
	org $9000

KEY_H_CODE	equ $2003
KEY_X_CODE	equ $2005
INVENTORY_SIZE	equ 6
OBJECT_HEALTH	equ 16
FX_INV_MOVE	equ 12
FX_INV_SELECT	equ 13

; вызов функции движка: HL/A/BC/DE — параметры, адрес кладётся в vec_ovl_tgt
PZ_SET		macro
		endm

pz_entry:
	; сначала дождаться отпускания H (иначе меню закроется тем же нажатием)
pz_wait_h:
	call pz_key_h
	or a
	jp nz,pz_wait_h
	call pz_print
pz_loop:
	ei
	halt
	ld a,(joystick_state)
	ld d,a
	and $10			; огонь — применить предмет
	jp nz,pz_use
	ld a,d
	and $04			; влево
	jp nz,pz_left
	ld a,d
	and $08			; вправо
	jp nz,pz_right
	ld a,d
	and $02			; вниз — сменить оружие
	jp nz,pz_weapon
pz_check_exit:
	call pz_key_h
	or a
	jp nz,pz_done		; H — назад в игру
	call pz_key_x
	or a
	jp z,pz_loop
	; АР2 — выход в главное меню (в оригинале X)
	ld a,2
	ld (player_dead),a
pz_done:
	call pz_key_h		; дождаться отпускания
	or a
	jp nz,pz_done
	; перерисовать поле целиком (текст меню стереть)
	ld hl,InvalidateTiles
	ld (vec_ovl_tgt),hl
	ld bc,0
	ld de,32*256 + 20
	call vec_ovl_call
	ld hl,RedrawAllSprites
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	ret

; ---- выбор предмета ----
pz_left:
	call pz_wait_release
	ld a,(inv_current_object)
	or a
	jp z,pz_loop		; левее первого — некуда
	dec a
	ld (inv_current_object),a
	jp pz_inv_upd
pz_right:
	call pz_wait_release
	ld a,(inv_current_object)
	cp INVENTORY_SIZE - 1
	jp z,pz_loop
	inc a
	ld (inv_current_object),a
pz_inv_upd:
	ld a,FX_INV_MOVE
	call pz_fx
	ld hl,force_inv_redraw
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	call pz_print		; панель перерисовалась — вернуть рамку
	jp pz_loop

; ---- применить предмет (в оригинале работает только зелье здоровья) ----
pz_use:
	call pz_wait_release
	ld a,(inv_current_object)
	ld e,a
	ld d,0
	ld hl,inventory
	add hl,de
	ld a,(hl)
	cp OBJECT_HEALTH
	jp nz,pz_loop
	ld hl,ENTITY_PLAYER_POINTER
	ld (z_iy),hl		; get_entity_max_energy читает IY (у нас z_iy)
	ld hl,get_entity_max_energy
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	ld (ENTITY_PLAYER_POINTER+4),a	; энергия = максимум
	ld a,FX_INV_SELECT
	call pz_fx
	ld a,OBJECT_HEALTH
	ld hl,remove_object_from_inventory
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	jp pz_inv_upd

; ---- смена оружия (по кругу, только доступные) ----
pz_weapon:
	call pz_wait_release
pz_wp1:
	ld a,(player_current_weapon)
	inc a
	and 3
	ld (player_current_weapon),a
	ld e,a
	ld d,0
	ld hl,player_available_weapons
	add hl,de
	ld a,(hl)
	or a
	jp z,pz_wp1		; это оружие не найдено — следующее
	ld a,FX_INV_MOVE
	call pz_fx
	; Спрайты героя под выбранное оружие подкачиваются ТОЛЬКО при загрузке уровня (fdd_banks.fb_wpn):
	; здесь, в паузе, чтение с дискеты рвало картинку на живой машине (Emu80, 2026-09-08) — поле и
	; панель оставались обрывками буфера загрузки и после выхода. Headless-модель дефект не
	; воспроизводит, причина не найдена, поэтому смена оружия в паузе снова мгновенная: меняются
	; название и значок в панели, а спрайт в руке — со следующего входа в уровень.
	ld hl,draw_weapon
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	ld hl,RedrawScreen
	ld (vec_ovl_tgt),hl
	call vec_ovl_call
	call pz_print
	jp pz_loop

; ---- помощники ----
pz_fx:				; A = номер эффекта
	push af
	ld hl,FX_Play
	ld (vec_ovl_tgt),hl
	pop af
	jp vec_ovl_call

pz_key_h:
	ld hl,get_keyboard
	ld (vec_ovl_tgt),hl
	ld hl,KEY_H_CODE
	jp vec_ovl_call
pz_key_x:
	ld hl,get_keyboard
	ld (vec_ovl_tgt),hl
	ld hl,KEY_X_CODE
	jp vec_ovl_call

pz_wait_release:		; ждать, пока джойстик отпущен (как pause_menu_waitkey)
	xor a
	ld (joystick_state),a
	ei
	halt
	ld a,(joystick_state)
	or a
	jp nz,pz_wait_release
	ret

; рамка с подсказками: 6 строк по 18 знаков с колонки 7, строки 8..13
pz_print:
	xor a
	ld (pz_row),a
pz_p1:
	ld a,(language)
	or a
	ld hl,pz_strings_en
	jp nz,pz_p2
	ld hl,pz_strings_ru
pz_p2:
	ld a,(pz_row)
	ld e,a
	ld d,0
	add hl,de
	add hl,de
	ld a,(hl)		; таблица адресов строк
	inc hl
	ld h,(hl)
	ld l,a
	ld a,(pz_row)
	add a,8
	ld c,a			; строка 8..13
	ld b,7			; колонка 7 (18 знаков -> ровно центр экрана)
	call pz_str
	ld a,(pz_row)
	inc a
	ld (pz_row),a
	cp 6
	jp nz,pz_p1
	ret

pz_str:				; HL = строка, B = колонка, C = строка
	ld a,(hl)
	or a
	ret z
	push hl
	push bc
	ld hl,drawChar
	ld (vec_ovl_tgt),hl
	pop bc
	pop hl
	push hl
	push bc
	ld a,(hl)
	call vec_ovl_call
	pop bc
	pop hl
	inc hl
	inc b
	jp pz_str

pz_row:		db 0
	include "pause_str.asm"
