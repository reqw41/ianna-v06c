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
	; --- H/J/X: сканируем ЗДЕСЬ, в гасящем. Порт $03 — это ещё и регистр вертикального скролла,
	; и опрос посреди кадра сдвигал картинку: экран подёргивался (get_keyboard звался каждый тик
	; из mainloop — проверка паузы). Теперь get_keyboard только читает vec_keys.
	ld a,$82		; порт B ППИ -> вход
	out ($00),a
	ld a,$DF		; ряд 5: H = бит 0, J = бит 2
	out ($03),a
	in a,($02)
	cpl
	and $05
	ld c,a
	ld a,$7F		; ряд 7: X = бит 0 -> кладём в бит 3
	out ($03),a
	in a,($02)
	cpl
	rlca			; бит 0 -> бит 3 (три сдвига). Был лишний rrca перед ними: бит уезжал в
	rlca			; бит 2, `and $08` давал ноль ВСЕГДА — выход из паузы по X не работал
	rlca			; (2026-09-08, жалоба владельца «не выйти из паузы»).
	and $08
	or c
	ld (vec_keys),a
	ld a,$80		; вернуть режим ППИ, бордюр и скролл
	out ($00),a
	ld a,1
	out ($02),a
	ld a,$FF
	out ($03),a
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
	; Действие (X) — ОДНО СРАБАТЫВАНИЕ НА НАЖАТИЕ, как get_opqa_end оригинала (input.asm).
	; script_player ставит action_ack=1, как только увидел бит 5; пока кнопку держат, опрос
	; обязан этот бит гасить и сбросить action_ack только после отпускания. Без этого удержание X
	; на порте раз за разом доставало и убирало меч (локстеп с оригиналом, сцена голема 2026-09-07:
	; тики 25..29, joystick_state 32 против 0, состояние героя 36/0/34 против 38).
	ld a,(action_ack)
	or a
	ld a,c			; mov a,c флаги не трогает — Z ещё от or a
	ret z			; подтверждения не было: отдаём как есть
	and $20
	jp nz,gj_mask		; кнопку всё ещё держат — бит гасим
	ld (action_ack),a	; A=0: кнопку отпустили, разрешаем следующее действие
	ld a,c
	ret
gj_mask:
	ld a,c
	and $DF
	ret

isr_hook_call:
	jp (hl)

; get_keyboard: HL = код клавиши MSX -> A != 0, если клавиша нажата.
KEY_H_CODE	equ $2003
KEY_J_CODE	equ $8003
KEY_X_CODE	equ $2005
get_keyboard:			; читает маску, снятую в ISR: порт $03 (он же скролл) здесь не трогаем
	ld a,(vec_keys)
	ld b,a
	ld a,h
	cp KEY_J_CODE>>8
	jp nz,gk_hx
	ld a,l
	cp KEY_J_CODE&255
	jp nz,gk_no
	ld a,b
	and $04
	ret
gk_hx:				; у H и X старший байт одинаков ($20)
	cp KEY_H_CODE>>8
	jp nz,gk_no
	ld a,l
	cp KEY_H_CODE&255
	ld a,b
	jp z,gk_h
	ld a,l
	cp KEY_X_CODE&255
	jp nz,gk_no
	ld a,b
	and $08
	ret
gk_h:
	and $01
	ret
gk_no:
	xor a
	ret
