; vec_isr.asm — кадровое прерывание (RST7, VBlank) и опрос клавиатуры.
; Порядок как в рецепте анти-фликера: палитра -> клавиатура -> счётчик кадров.
; Аналог ISR оригинала: get_joystick -> joystick_state, frames_noredraw++, музыка.

vec_isr:
	push af
	push bc
	push de
	push hl
    if VI53
	; счётчик 0 ВИ53 = фаза кадра: режим 0, старт с 0 (=65536), 1.5 МГц (такт счётчика = 2 такта ЦП).
	; Выход канала 0 при счёте низкий — в микшер ничего не подмешивает; каналы 1-2 свободны под музыку.
	ld a,$30
	out ($08),a
	xor a
	out ($0B),a
	out ($0B),a
    endif
	; --- палитра (латч по лучу: пишем в VBlank, сразу после входа в ISR) — только когда изменилась
	; (vec_pal_dirty: 1 при старте и после смены палитры уровня); каждый кадр это ~1.7К тактов зря ---
	ld a,(vec_pal_dirty)
	or a
	jp z,isr_nopal
	xor a
	ld (vec_pal_dirty),a
	ld hl,vec_palette
	ld c,0
isr_pal:
	ld a,c
	out ($02),a
	ld a,(hl)
	out ($0C),a
	out ($0C),a
	out ($0C),a
	inc hl
	inc c
	ld a,c
	cp 16
	jp nz,isr_pal
isr_nopal:
	ld a,1
	out ($02),a		; бордюр = цвет 1 (чёрный, как backdrop MSX2)
	; --- клавиатура -> joystick_state (биты: 0 up,1 down,2 left,3 right,4 fire,5 fire2) ---
	call get_joystick
	ld (joystick_state),a
	; хук клавиатуры (экран пароля): сканирование только здесь, в VBlank — порт $03 это ещё и
	; вертикальный скролл, дёргать его посреди кадра нельзя (картинка подпрыгивает)
	ld hl,(vec_key_hook)
	ld a,h
	or l
	jp z,isr_nokey
	call isr_hook_call
isr_nokey:
	; --- счётчик кадров без перерисовки ---
	ld a,(frames_noredraw)
	inc a
	ld (frames_noredraw),a
	ld hl,(FrameCounter)
	inc hl
	ld (FrameCounter),hl
    if !DEMO
	; --- музыка: как в ISR оригинала (mzk_subroutine -> MUSIC_Play), но данные в квазидиске ---
	ld a,(music_playing)
	or a
	jp z,isr_nomusic
	; сохранить ячейки эмуляции Z80 (главный код мог быть прерван внутри хелпера): холодная часть
	; плеера трогает только z_ix, z_a, z_ret (+ z_iy/z_tmp рядом) — 8 байт z_ix..z_ret, без циклов
	ld hl,(z_ix)
	ld (vec_zsave),hl
	ld hl,(z_iy)
	ld (vec_zsave+2),hl
	ld hl,(z_a)
	ld (vec_zsave+4),hl
	ld hl,(z_ret)
	ld (vec_zsave+6),hl
	ld a,(vec_kv_shadow)
	and $1c			; сохранить стековые биты: сброс пула идёт с EI, стек — в странице 3
	or KV_WIN_MUSIC
	out (KV_PORT),a
	call MUSIC_Play
	ld a,(vec_kv_shadow)
	out (KV_PORT),a
	ld hl,(vec_zsave)
	ld (z_ix),hl
	ld hl,(vec_zsave+2)
	ld (z_iy),hl
	ld hl,(vec_zsave+4)
	ld (z_a),hl
	ld hl,(vec_zsave+6)
	ld (z_ret),hl
isr_nomusic:
    endif
    if !VI53
	ld a,VEC_ISR_COST
	ld (vec_bud_used),a	; бюджет DI (программный): фаза кадра на выходе из ISR
    endif
	pop hl
	pop de
	pop bc
	pop af
	ei
	ret

; get_joystick: A = состояние. Матрица Вектора: out(3)=~(1<<ряд), in(2) — активный 0.
; ряд 0: б7 вниз, б6 вправо, б5 вверх, б4 влево;  ряд 7: б7 пробел, б2 Z, б0 X.
; ПОРТ 3 = ТАКЖЕ ВЕРТИКАЛЬНЫЙ СКРОЛЛ — после опроса обязательно вернуть $FF.
get_joystick:
	ld a,$82		; ППИ: порт B -> ВХОД (иначе in(2) отдаёт защёлку = «всё нажато»)
	out ($00),a
	ld a,$FE		; ряд 0
	out ($03),a
	in a,($02)
	cpl
	ld b,a			; B: б7 down, б6 right, б5 up, б4 left (1 = нажато)
	ld c,0
	ld a,b
	and $20
	jp z,gj_1
	ld c,1			; up
gj_1:
	ld a,b
	and $80
	jp z,gj_2
	ld a,c
	or 2			; down
	ld c,a
gj_2:
	ld a,b
	and $10
	jp z,gj_3
	ld a,c
	or 4			; left
	ld c,a
gj_3:
	ld a,b
	and $40
	jp z,gj_4
	ld a,c
	or 8			; right
	ld c,a
gj_4:
	ld a,$FD		; ряд 1: СТОП (бит 2) — выход в меню
	out ($03),a
	in a,($02)
	cpl
	and $04
	jp z,gj_r7
	ld a,(vec_in_game)	; вне игры (меню/интро) клавишу игнорируем
	or a
	jp z,gj_r7
	ld a,2
	ld (player_dead),a	; движок сам выйдет из game; vec_main вернёт в меню
gj_r7:
	ld a,$7F		; ряд 7
	out ($03),a
	in a,($02)
	cpl
	ld b,a
	ld a,$80		; ППИ: порт B -> ВЫХОД (mode512 держим в 0, полосы на железе)
	out ($00),a
	xor a
	out ($02),a		; режим 256 точек
	ld a,$FF
	out ($03),a		; вернуть скролл! (mode set сбросил защёлки)
	ld a,b
	and $84			; пробел или Z
	jp z,gj_5
	ld a,c
	or $10			; fire
	ld c,a
gj_5:
	ld a,b
	and $01			; X
	jp z,gj_6
	ld a,c
	or $20			; fire2 (action)
	ld c,a
gj_6:
	ld a,c
	ret

isr_hook_call:
	jp (hl)

; get_keyboard: HL = код клавиши MSX -> A != 0, если клавиша нажата.
; Поддержаны H (меню паузы оригинала) и J (джукбокс): ряд 5 матрицы Вектора = H I J K L M N O.
KEY_H_CODE	equ $2003
KEY_J_CODE	equ $8003
KEY_X_CODE	equ $2005
get_keyboard:
	ld a,h
	cp KEY_H_CODE>>8
	jp nz,gk_j
	ld a,l
	cp KEY_H_CODE&255
	jp nz,gk_j		; старший байт у KEY_H и KEY_X одинаков ($20) — перебор продолжаем
	ld c,$01		; H = бит 0
	jp gk_scan
gk_j:
	ld a,h
	cp KEY_J_CODE>>8
	jp nz,gk_x
	ld a,l
	cp KEY_J_CODE&255
	jp nz,gk_x
	ld c,$04		; J = бит 2
	jp gk_scan
gk_x:
	ld a,h
	cp KEY_X_CODE>>8
	jp nz,gk_no
	ld a,l
	cp KEY_X_CODE&255
	jp nz,gk_no
	ld c,$81		; X: ряд 7 бит 0 (маркер старшего бита = другой ряд)
gk_scan:
	di
	ld a,$82		; порт B ППИ -> вход
	out ($00),a
	ld a,$DF		; ряд 5 (H I J K L M N O)
	ld b,a
	ld a,c
	and $80
	jp z,gk_row
	ld b,$7F		; ряд 7 (X Y Z [ \\ ] ^ ПРОБЕЛ)
	ld a,c
	and $7F
	ld c,a
gk_row:
	ld a,b
	out ($03),a
	in a,($02)
	cpl
	and c
	ld c,a
	ld a,$80		; вернуть режим и скролл (как в get_joystick)
	out ($00),a
	xor a
	out ($02),a
	ld a,$FF
	out ($03),a
	ei
	ld a,c
	ret
gk_no:
	xor a
	ret
