; vec_isr.asm — кадровое прерывание (RST7, VBlank) и опрос клавиатуры.
; Порядок как в рецепте анти-фликера: палитра -> клавиатура -> счётчик кадров.
; Аналог ISR оригинала: get_joystick -> joystick_state, frames_noredraw++, музыка.

vec_isr:
	push af
	push bc
	push de
	push hl
	; --- палитра (латч по лучу: пишем в VBlank, сразу после входа в ISR) ---
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
	ld a,1
	out ($02),a		; бордюр = цвет 1 (чёрный, как backdrop MSX2)
	; --- клавиатура -> joystick_state (биты: 0 up,1 down,2 left,3 right,4 fire,5 fire2) ---
	call get_joystick
	ld (joystick_state),a
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
	; сохранить ячейки эмуляции Z80 (главный код мог быть прерван внутри хелпера)
	ld hl,z_ix
	ld de,vec_zsave
	ld b,18
isr_zs:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec b
	jp nz,isr_zs
	ld a,KV_WIN_MUSIC
	out (KV_PORT),a
	call MUSIC_Play
	ld a,(vec_kv_shadow)
	out (KV_PORT),a
	ld hl,vec_zsave
	ld de,z_ix
	ld b,18
isr_zr:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec b
	jp nz,isr_zr
isr_nomusic:
    endif
	ld a,VEC_ISR_COST
	ld (vec_bud_used),a	; бюджет DI: фаза кадра на выходе из ISR
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

; get_keyboard: HL = код клавиши MSX (KEY_H и т.п.) -> A=0 (не нажата). Пауза не поддержана.
get_keyboard:
	xor a
	ret
