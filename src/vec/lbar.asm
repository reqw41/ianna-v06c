; lbar.asm — полоса загрузки при смене уровня, выходе в меню и концовке (vec_reload_set), такая же, как
; на заставке стартовой загрузки (vec_lscreen.asm). Лежит в каждом наборе (стр.3 LB_SRC); vec_reload_set
; копирует её в хвост string_area (LB_ORG: за буфером сектора, таблицей длин и загрузчиком банков, до
; оверлея готовых тайлов) и зовёт lb_start, а после загрузки снимает хук сам.
; VRAM при загрузке — буфер: сжатое в $8000 (плоскость цвета 8), распакованное в $C000 (цвет 2). Поэтому
; полоса — в двух других плоскостях: подложка в $E000 (бит 1 — кремовый), заливка в $A000 (биты 1 и 4 —
; красный), а палитра от битов 8 и 2 не зависит. Один бит 4 — чёрный: сжатый кусок банка бывает чуть
; длиннее 8 КБ и заходит из $8000 в первые колонки $A000 — так этот хвост не виден. Ширина — как у стартовой: vfl_blk 0..31 — блоки набора,
; дальше +2 на каждый кусок банка (fdd_banks.asm).
	include "menu_syms.asm"
	org LB_ORG
LB_COL		equ 10		; колонки 10..21 (x 80..175), строки y 114..133 — как у стартовой полосы
LB_L0		equ 255-114
LB_L1		equ LB_L0-19

lb_start:
	xor a
	ld (vfl_blk),a		; от прошлой загрузки там 32 и больше — полоса мелькнула бы полной
	call vfl_pal		; экран — в чёрное (через прерывание): плоскости ещё хранят прошлый экран
	ld a,$C9
	ld (vfl_pal),a		; дальше палитру ставим сами, загрузчик её не трогает
	ld hl,$A000		; плоскости $A000 и $E000 — в нули
	ld de,$E000
lbs_z:
	xor a
	ld (hl),a
	ld (de),a
	inc hl
	inc de
	ld a,h
	cp $C0
	jp nz,lbs_z
	ld h,$E0+LB_COL		; подложка
lbs_c:
	ld l,LB_L1
lbs_r:
	ld (hl),$FF
	inc l
	ld a,l
	cp LB_L0+1
	jp nz,lbs_r
	inc h
	ld a,h
	cp $E0+LB_COL+12
	jp nz,lbs_c
	ld hl,lb_pal16
	ld de,vec_palette
	ld bc,16
	call z_ldir
	ld hl,lb_hook		; lb_wl = $FF: блоб копируется из набора заново перед каждой загрузкой
	ld (vec_key_hook),hl
	ld a,1
	ld (vec_pal_dirty),a
	ret

; хук прерывания: ширина w = min(94, p + p/4), p = vfl_blk; рисуем только при смене ширины
lb_hook:
	ld a,(vfl_blk)
	ld b,a
	rrca
	rrca
	and $3F
	add a,b
	cp 95
	jp c,lbh_w
	ld a,94
lbh_w:
	ld hl,lb_wl
	cp (hl)
	ret z
	ld (hl),a
	add a,LB_COL*8+1	; правый край заливки (не включая); левая точка — поле
	ld c,a
	ld h,$A0+LB_COL
	ld b,LB_COL*8		; x0 колонки
lbh_c:
	ld a,c			; сколько точек колонки залито: clamp(xe - x0, 0, 8)
	sub b
	jp nc,lbh_1
	xor a
lbh_1:
	cp 9
	jp c,lbh_2
	ld a,8
lbh_2:
	ld e,a
	ld a,$FF		; маска: старшие e бит
	inc e
lbh_m:
	dec e
	jp z,lbh_3
	or a			; CY = 0... сдвигаем единицы слева: mask = ~($FF >> e)
	rra
	jp lbh_m
lbh_3:
	cpl
	ld l,LB_L1
lbh_r:
	ld (hl),a
	inc l
	ld e,a
	ld a,l
	cp LB_L0+1
	ld a,e
	jp nz,lbh_r
	ld a,b
	add a,8
	ld b,a
	inc h
	ld a,h
	cp $A0+LB_COL+12
	jp nz,lbh_c
	ret

lb_wl:	db $FF
lb_pal16:			; биты 1 и 4 — красный, один бит 1 ($E000) — кремовый, остальное чёрное
	db $00,$B7,$00,$B7,$00,$0E,$00,$0E,$00,$B7,$00,$B7,$00,$0E,$00,$0E
