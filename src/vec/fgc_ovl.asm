; fgc_ovl.asm — готовые тайлы «фон + передний слой» (FGC). Код живёт НЕ в ROM, а в хвосте
; string_area: набор уровня несёт его в блоке строк (level_tools.build_level, tail), так что
; ROM платит только за хук в DrawTile (7 Б) и байт fgc_on в таблице уровня.
;
; Зачем: передний тайл (туман уровня 3) стоит 29 ед. бюджета против 16 у фонового. Для стайла,
; который в этом тике не перекрыт спрайтом, фон и передний слой можно положить одним блитом
; готового тайла (128 Б, формат фонового) и пометить стайл в карте грязных стайлов чистым, чтобы
; передний проход (RedrawInvTiles_FG) его пропустил. Под спрайтом — обычный путь: фон, спрайт, передний слой.
;
; Данные (build_edd, FGC_*): готовые тайлы в стр.2 с FGC_TILES по 128 Б; таблица указателей
; групп FGC_PTRS[i] (i — индекс переднего тайла из fg_tile_pairs) -> список (номер фона, индекс
; готового)…, $FF. Вход из DrawTile: HL = &CURRENT_SCREEN_MAP[idx], B = X px, C = Y px.
	include "menu_syms.asm"	; FGC_CODE/FGC_PTRS/FGC_TILES приходят из build_edd через gen_data
	org FGC_CODE
KV_PORT		equ $10
KV_STK_P2	equ $18
VEC_P0H		equ $80
Y_TOP_L		equ 223

fgc_entry:
	ld a,(vec_pool_on)
	or a
	jp nz,fgc_plain		; в пуле формат слотов другой — только прямой путь
	push hl
	ld de,160		; CURRENT_SCREEN_MAP_FG = CURRENT_SCREEN_MAP + 160
	add hl,de
	ld a,(hl)
	pop hl
	or a
	jp z,fgc_plain		; переднего тайла нет
	ld e,a			; E = номер переднего тайла
	ld a,(hl)
	ld d,a			; D = номер фонового
	; --- стайл (B,C; 16x16) под спрайтом этого тика? SPDATA: 16 записей по 8: +3 x, +4 y, +7 флаг
	push hl
	push de
	ld hl,SPDATA+7
	ld e,16
fgc_sl:
	ld a,(hl)
	or a
	jp z,fgc_sn
	dec hl
	dec hl
	dec hl			; +4: y
	ld a,(hl)
	sub c
	add a,32
	cp 48			; Y-32 < y < Y+16
	jp nc,fgc_sn4
	dec hl			; +3: x
	ld a,(hl)
	sub b
	add a,24
	cp 40			; X-24 < x < X+16
	jp c,fgc_under
	inc hl
fgc_sn4:
	inc hl
	inc hl
	inc hl			; снова +7
fgc_sn:
	ld a,l
	add a,8
	ld l,a
	jp nc,fgc_sn2
	inc h
fgc_sn2:
	dec e
	jp nz,fgc_sl
	pop de
	pop hl
	; --- индекс переднего тайла: пары (номер, индекс) в fg_tile_pairs, не больше fg_lut_n
	; (скрипт уровня может подменить тайл в карте — тогда пары нет, идём обычным путём)
	push hl
	push bc
	ld a,(fg_lut_n)
	ld b,a
	ld hl,fg_tile_pairs
fgc_fl:
	ld a,(hl)
	inc hl
	cp e
	jp z,fgc_ff
	inc hl
	dec b
	jp nz,fgc_fl
	pop bc
	jp fgc_plain2
fgc_ff:
	pop bc
	ld a,(hl)		; индекс 0..31
	add a,a
	add a,FGC_PTRS & $FF
	ld l,a
	ld h,FGC_PTRS >> 8
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a			; HL = группа: (фон, готовый)…, $FF
fgc_gl:
	ld a,(hl)
	cp $FF
	jp z,fgc_plain2		; для этой пары готового нет
	inc hl
	cp d
	jp z,fgc_hit
	inc hl
	jp fgc_gl
fgc_hit:
	ld a,(hl)		; индекс готового тайла
	pop hl
	ld l,0
	rrca
	jp nc,fgc_a0
	ld l,$80
fgc_a0:
	and $7f
	add a,FGC_TILES >> 8
	ld h,a
	ld (vec_blit_src),hl
	ld a,19			; бюджет DI как у dt_direct (окно DI 13.3 ед., blitcalib)
	call vec_budget
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	push bc
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_STK_P2
	out (KV_PORT),a
	ld hl,fgc_end
	ld (vec_blit_ret),hl
	jp vec_blit128_vram
fgc_end:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	; --- стайл выведен целиком (фон + передний слой): пометить его в карте грязных стайлов
	; чистым ($FF), чтобы проход переднего слоя (RedrawInvTiles_FG) его пропустил. Карта — таблица
	; слотов, индекс = (C & $F0) | (B >> 4). Сюда попадаем только при выключенном пуле, где записи
	; карты всё равно снимает vec_slot_init в конце тика.
	ld a,b
	rrca
	rrca
	rrca
	rrca
	and $0f
	ld l,a
	ld a,c
	and $f0
	or l
	ld l,a
	ld h,vec_slot_tab >> 8
	ld (hl),$ff
	ret
fgc_under:
	pop de
	pop hl
fgc_plain:
	ld a,(hl)
	jp drawTile_nosave	; вызывающие (обход rit, DrawScreen) регистры сохраняют сами
fgc_plain2:
	pop hl
	jp fgc_plain
fgc_size	equ $ - FGC_CODE
