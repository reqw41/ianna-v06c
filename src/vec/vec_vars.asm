; vec_vars.asm — ячейки рантайма Вектора (транслятор + платформенный слой).
; Переменные игры (vars.asm MSX2) подключаются отдельно (build/tr/vars.asm).

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
vec_spr_src:	dw 0
vec_spr_port:	db 0
vec_spr_skip:	db 0
vec_spr_lbot:	db 0
vec_spr_hcol:	db 0

; --- стек ---
	ds 256
vec_stack_top:

; --- таблица разворота байта: выровнена на 256 ---
	ds ($ + 255) & $FF00 - $
rev256:
	ds 256
