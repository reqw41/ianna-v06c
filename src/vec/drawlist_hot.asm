;;; drawlist_hot.asm — ВЕКТОР: DrawSpriteList на i8080 вручную
;;; (оригинал: ref/msx2/src/drawsprite.asm, DrawSpriteList..drawsprlist_end).
;;; Перевод обходил 16 записей через IX и на каждой звал z_ix_* (~100 тактов вместо 19 у Z80):
;;; только холостой обход пустой записи стоил ~255 тактов, а их за тик 11..14 из 16.
;;; Здесь IX держим в DE (указатель на поле redraw, +7 записи), поля адресуем HL с inc/dec,
;;; счётчик IYH не нужен — конец списка виден по самому указателю.
;;; Раскладка записи SPDATA (8 байт): +0/+1 адрес кадра, +2 тип (страница ROM + бит направления),
;;; +3 X, +4 Y, +5 nchars X, +6 nchars Y, +7 флаг перерисовки.
DSL_END	equ SPDATA+7+8*MAX_SPRITES	; за последней записью списка
DSL_END_L	equ DSL_END & 255
DSL_END_H	equ DSL_END >> 8
DrawSpriteList:
	ld de,SPDATA+7			; DE -> флаг перерисовки текущей записи
drawsprlist_loop:
	ld a,(de)
	and a
	jp nz,drawsprlist_draw
drawsprlist_next:
	ld a,e				; DE += 8 (следующая запись)
	add a,8
	ld e,a
	jp nc,dsl_nocarry
	inc d
dsl_nocarry:
	cp DSL_END_L
	jp nz,drawsprlist_loop
	ld a,d
	cp DSL_END_H
	jp nz,drawsprlist_loop
drawsprlist_end:
	ld a,1
	jp setROM2			; хвостовой вызов вместо call/ret

drawsprlist_draw:
	xor a
	ld (de),a			; флаг снят: спрайт перерисовывается сейчас
	push de				; drawSprite портит DE
	ld a,e				; HL = DE-7 = начало записи
	sub 7
	ld l,a
	ld a,d
	sbc a,0
	ld h,a
	inc hl
	inc hl				; HL -> +2 (тип)
	ld a,(hl)			; бит 7 типа = направление взгляда
	rlca
	and 1
	ld e,a				; направление — в E до самого вызова (setROM2 портит только A)
	ld a,(hl)
	and $7f				; страница ROM спрайта
	call setROM2
	inc hl
	inc hl
	inc hl
	inc hl				; HL -> +6 (высота в символах)
	ld a,(hl)
	add a,a
	add a,a
	add a,a				; *8 -> пиксели
	dec hl
	dec hl				; HL -> +4 (Y)
	add a,(hl)			; нижняя граница спрайта
	cp 160
	jp nc,dsl_clip			; ниже экрана — обрезать по Y
	ld a,SPRITE_HEIGHT
	jp dsl_ny
dsl_clip:
	cpl				; оригинал: sub 160 / neg / add SPRITE_HEIGHT,
	add a,193			; то есть 192-A (mod 256) = ~A+193
dsl_ny:
	ld (vdpCmdSprite+VDP_NY),a
	ld c,(hl)			; C = Y   (HL -> +4)
	dec hl
	ld b,(hl)			; B = X   (+3)
	dec hl
	dec hl
	dec hl				; HL -> +0
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a				; HL = адрес кадра спрайта
	ld a,e				; A = направление
	call drawSprite
	pop de
	jp drawsprlist_next
