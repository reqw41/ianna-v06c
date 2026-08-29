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
vec_spr_dir:	db 0
vec_spr_cx:	db 0
vec_spr_ybot:	db 0
vec_spr_row:	db 0
vec_rows_left:	db 0
vec_seg_cnt:	db 0
vec_blit_src:	dw 0
vec_blit_ret:	dw 0
vec_bl_cols:	db 0
vec_bl_pops:	db 0
vec_pool_on:	db 0
vec_slot_next:	db 0
vec_tmp_sx:	db 0
vec_tmp_sx1:	db 0
vec_tmp_sy:	db 0
vec_tmp_nx:	db 0
vec_tmp_ny:	db 0
vec_tmp_row16:	db 0
vec_fill_color:	db 0
vec_fill_xr:	db 0
vec_fill_mask:	db 0
vec_fill_hgt:	db 0
vec_kv_shadow:	db 0
vec_bud_frame:	db 0		; бюджет DI: кадр (мл. байт FrameCounter) и потрачено (x256 тактов)
vec_bud_used:	db 0		; текущее значение порта $10 вне блитов (для ISR)
vec_bud_halts:	dw 0		; счётчик halt в vec_budget (статистика)
vec_zsave:	ds 18		; сохранение z_ix..z_hl2 на время плеера в ISR
ply_sd_cnt:	db 0		; Arkos: сдвиг частоты (4k) вместо самомодификации jr
ply_hd_cnt:	db 0
ply_sd_loop:	db 0

; --- стек: до ближайшей границы страницы (минимум ~200 Б) ---
	ds 200
	ds ($ + 255) & $FF00 - $
vec_stack_top:
; --- таблица разворота байта: ровно страница ---
rev256:
	ds 256
; --- таблица слотов пула (160 супертайлов, индекс = (y&$F0)|x), страница ---
vec_slot_tab:
	ds 256
