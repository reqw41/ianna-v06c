; vec_vars.asm — ячейки рантайма Вектора (транслятор + платформенный слой).
; Идёт СРАЗУ после vars.asm (string_area по $0200). Стек и rev256 выровнены на страницу.

; --- эмуляция Z80 (z80rt.asm) ---
z_ix:	dw 0
z_iy:	dw 0
z_a:	db 0
z_tmp:	db 0
z_ret:	dw 0
z_af2:	dw 0
z_bc2:	dw 0
z_de2:	dw 0
z_hl2:	dw 0

; --- vec_vdp ---
vec_sprite_bank: db 2
vec_tile_src:	dw 0
vec_sp_save:	dw 0
vec_plane_cnt:	db 0
vec_col_cnt:	db 0
vec_row_cnt:	db 0
vec_spr_src:	dw 0
vec_spr_port:	db 0
vec_spr_skip:	db 0
vec_spr_ny:	db 0
vec_spr_lbot:	db 0
vec_spr_hcol:	db 0
vec_spr_mask:	db 0
vec_spr_p01:	dw 0

; --- стек: до ближайшей границы страницы (минимум ~200 Б) ---
	ds 200
	ds ($ + 255) & $FF00 - $
vec_stack_top:
; --- таблица разворота байта: ровно страница ---
rev256:
	ds 256
