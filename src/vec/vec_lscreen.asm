;;; vec_lscreen.asm — хук ISR на время стартовой загрузки: полоса на заставке-обложке (16 цветов).
;;; Лежит за загрузчиком vec_bootload.asm в хвосте string_area: буфер сектора и таблица длин его не
;;; задевают, затирает его только блоб меню — оверлей снимает хук раньше. Ставит хук bl_cover.
;;; Полоса — бит плоскости $8000 внутри рамки в центре экрана: там цвет 7 (пусто), а с битом $8000 —
;;; цвет 15, красный (build_vec.cover_asm). Окно квазидиска загрузчика ($A000-$DFFF) плоскость $8000 не
;;; накрывает. Место полосы — LS_COL (12 колонок от неё), строки LS_L0..LS_L1+1 — задаёт cover_asm.

ls_hook:
	ld a,(vfl_fill)		; примитивы старого загрузчика затёрты таблицей слотов — загрузка кончилась
	cp LS_OP0
	jp nz,ls_end
	ld a,(vfl_blk)		; 0..31 блоки набора, 32..72 — куски банков (+2 на кусок)
ls_fill:
	ld l,a			; ширина заливки w = min(94, p*21/16)
	ld h,0
	ld e,l
	ld d,h
	add hl,hl
	add hl,hl
	ld b,h
	ld c,l			; 4p
	add hl,hl
	add hl,hl		; 16p
	add hl,bc
	add hl,de		; 21p
	ld a,l
	rrca
	rrca
	rrca
	rrca
	and $0F
	ld e,a
	ld a,h
	rlca
	rlca
	rlca
	rlca
	and $F0
	or e			; 21p/16
	cp 95
	jp c,ls_w
	ld a,94
ls_w:
	ld hl,ls_wl		; рисуем только при смене ширины: перерисовка — ~6 тыс. тактов, это 10 % кадра
	cp (hl)
	ret z
	ld (hl),a
	add a,LS_COL*8+1
	ld (ls_xe),a		; правый край заливки (не включая)
	ld h,$80+LS_COL
	ld b,LS_COL*8		; x0 колонки
ls_c:
	ld a,(ls_xe)		; hi = clamp(xe - x0, 0, 8)
	sub b
	jp nc,ls_c1
	xor a
ls_c1:
	cp 9
	jp c,ls_c2
	ld a,8
ls_c2:
	push hl
	ld e,a
	ld d,0
	ld hl,ls_sh
	add hl,de
	ld a,(hl)
	cpl
	ld c,a			; ~($FF >> hi)
	pop hl
	ld a,h
	cp $80+LS_COL
	ld a,$FF
	jp nz,ls_c3
	ld a,$7F		; первая колонка: левая точка — рамка
ls_c3:
	and c
	ld l,LS_L0
ls_r:
	ld (hl),a
	dec l
	ld e,a
	ld a,l
	cp LS_L1
	ld a,e
	jp nz,ls_r
	ld a,b
	add a,8
	ld b,a
	inc h
	ld a,h
	cp $80+LS_COL+12
	jp nz,ls_c
	ret

; конец загрузки: полоса вместе с рамкой — в чёрный (все 4 плоскости), хук снимает себя. Надпись «НАЖМИ ПРОБЕЛ»
; печатает оверлей меню шрифтом меню (ovl_press): здесь шрифта нет, а места в string_area — тоже.
; Зовут хук (из ISR) или оверлей меню (под DI: хук не должен войти сюда же посреди стирания).
ls_end:
	xor a			; окно закрыть: оверлей меню работает из окна $63, а оно накрывает и $8000
	out (KV_PORT),a
	ld d,$80+LS_COL		; старший байт: плоскость + колонка
ls_e0:
	ld h,d
ls_e1:
	ld l,LS_L0+1		; верх рамки
ls_e2:
	ld (hl),0
	dec l
	ld a,l
	cp LS_L1-1		; низ рамки — LS_L1
	jp nz,ls_e2
	inc h
	ld a,h
	and $1F
	cp LS_COL+12
	jp nz,ls_e1
	ld a,d
	add a,$20		; следующая плоскость: $80 -> $A0 -> $C0 -> $E0 -> перенос
	ld d,a
	jp nc,ls_e0
	ld hl,0
	ld (vec_key_hook),hl
	ld a,(vec_kv_shadow)	; вернуть порт (в оверлее — $63, в vec_start — 0)
	out (KV_PORT),a
	ret

ls_xe:	db 0
ls_wl:	db $FF		; последняя нарисованная ширина
ls_sh:	db $FF,$7F,$3F,$1F,$0F,$07,$03,$01,$00
