; series_ovl.asm — se_try: серийный блит одинаковых аним. стайлов (вода/огонь/лава).
; BG >=240 или непрозрачный FG. Вход: HL=&slot[idx]. Выход: CY+A=N / NC.
; SERIES_ADDR=$DE80 стр.3 (за эффектами; $C800-$C980 заняты MIRRBUF и стеком сброса пула), SERIES_PORT.
; Без call в ROM (окно сбросится).
	include "menu_syms.asm"
KV_PORT		equ $10
KV_STK_P0	equ $10
VEC_P0H		equ $80
Y_TOP_L		equ 223
VEC_NPL		equ 4
BG_TILES_BASE	equ $0000
FG_TILES_BASE	equ $8000

	org SERIES_ADDR

se_try:
	ld a,(hl)
	cp $FE
	jp z,se_fe
	ld a,(vec_pool_on)
	or a
	ret nz
se_fe:	ld a,l
	ld (vec_tmp_sx),a
	ld h,0
	ld l,a
	ld de,CURRENT_SCREEN_MAP
	add hl,de
	ld a,(rit_fg)
	or a
	jp z,se_cell
	ld de,160
	add hl,de
se_cell:
	ld a,(hl)
	cp 240
	jp c,se_no
	ld (vec_tmp_sx1),a
	ld a,(rit_cx)
	ld b,a
	ld c,1
	ld a,(vec_tmp_sx)
	ld l,a
	ld h,vec_slot_tab/256
se_sc:	dec b
	jp z,se_got
	inc l
	ld a,(vec_pool_on)
	or a
	jp z,se_sid
	ld a,(hl)
	cp $FE
	jp nz,se_got
se_sid:	push hl
	push bc
	ld a,l
	ld h,0
	ld l,a
	ld de,CURRENT_SCREEN_MAP
	add hl,de
	ld a,(rit_fg)
	or a
	jp z,se_cmp
	ld de,160
	add hl,de
se_cmp:	ld a,(vec_tmp_sx1)
	cp (hl)
	pop bc
	pop hl
	jp nz,se_got
	inc c
	jp se_sc
se_got:	ld a,c
	cp 2
	jp c,se_no
	ld (vec_tmp_sy),a
	ld a,(rit_fg)
	or a
	ld a,(vec_tmp_sx1)
	jp nz,se_fg
	ld d,a
	rrca
	and $7f
	add a,BG_TILES_BASE/256
	ld h,a
	ld a,d
	and 1
	rrca
	ld l,a
	jp se_go
se_fg:	ld hl,fg_tile_pairs
	ld b,a
	ld a,(fg_lut_n)
	or a
	jp z,se_no
	ld c,a
	ld a,b
se_f:	cp (hl)
	inc hl
	jp z,se_ff
	inc hl
	dec c
	jp nz,se_f
se_no:	or a
	ret
se_ff:	ld a,(hl)
	ld c,a
	rlca
	jp nc,se_no
	ld a,c
	and $7f
	add a,FG_TILES_BASE/256
	ld h,a
	ld l,0
se_go:	ld (vec_blit_src),hl
	ld a,(vec_tmp_sx)
	and $f0
	ld c,a
	ld a,(vec_tmp_sx)
	rlca
	rlca
	rlca
	rlca
	and $f0
	ld b,a
	ld a,(vec_tmp_sy)
	add a,a
	add a,8
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
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,SERIES_PORT
	or KV_STK_P0
	out (KV_PORT),a
	ld a,d
	ld (vec_tmp_nx),a
	ld a,e
	ld (vec_tmp_ny),a
	ld a,VEC_NPL
se_pl:	ld (vec_plane_cnt),a
	ld a,(vec_tmp_nx)
	ld d,a
	ld a,2
se_c2:	ld (vec_col_cnt),a
	ld a,(vec_tmp_ny)
	ld (vec_row_cnt),a
	ld a,8
se_w:	ld (vec_tmp_ovf),a
	pop bc
	ld a,(vec_tmp_sy)
	ld e,a
	ld a,(vec_row_cnt)
	ld l,a
	ld h,d
se_r:	ld (hl),c
	dec l
	ld (hl),b
	ld l,a
	inc h
	inc h
	dec e
	jp nz,se_r
	sub 2
	ld (vec_row_cnt),a
	ld a,(vec_tmp_ovf)
	dec a
	jp nz,se_w
	inc d
	ld a,(vec_col_cnt)
	dec a
	jp nz,se_c2
	ld a,(vec_tmp_nx)
	add a,$20
	ld (vec_tmp_nx),a
	ld a,(vec_plane_cnt)
	dec a
	jp nz,se_pl
	; окно до ret: иначе fetch хвоста из VRAM
	ld a,SERIES_PORT
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ld a,(vec_tmp_sy)
	scf
	ret

series_size	equ $ - SERIES_ADDR
