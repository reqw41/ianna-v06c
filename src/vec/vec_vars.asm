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
vec_spr_dst:	dw 0		; зеркальные варианты: адрес назначения на время просмотра rev256
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
vec_bl_planes:	db 4 - C8	; vec_blit_cols: плоскостей за блит (сбрасывается кодом в VEC_NPL; C8 из vdp_consts)
vec_pool_on:	db 0
vec_slot_next:	db 0
vec_tmp_sx:	db 0
vec_tmp_sx1:	db 0
vec_tmp_sy:	db 0
vec_tmp_nx:	db 0
vec_tmp_ny:	db 0
vec_tmp_row16:	db 0
vec_tmp_rc:	db 0		; сброс пула без стека: счётчик прямоугольников, указатель, счётчик и текущая колонка
vec_tmp_rp:	dw 0
vec_tmp_bx:	db 0
vec_tmp_cx:	db 0
vec_tmp_ovf:	db 0		; раздача слотов: переполнение
vec_an_cnt:	db 0		; AnimateSTiles: счётчик, длина/начало серии
vec_an_run:	db 0
vec_an_x:	db 0
vec_an_y:	db 0
rit_cnt:	db 0		; RedrawInvTiles: счётчики обхода грязных прямоугольников
rit_x0:		db 0
rit_y:		db 0
rit_nx:		db 0
rit_ny:		db 0
rit_cx:		db 0
rit_ptr:	dw 0
vec_spr_prev:	ds 64		; прошлые прямоугольники спрайтов (x,y,nx,ny) x16 — слоты и под старым местом
vec_fill_color:	db 0
vec_fill_xr:	db 0
vec_fill_mask:	db 0
vec_fill_hgt:	db 0
vec_kv_shadow:	db 0		; порт $10, каким его держит главный код (ISR возвращает его; во время сброса пула — стековый режим)
vec_kv_prev:	db 0
vec_bud_halts:	dw 0		; счётчик halt в vec_budget (статистика)
vec_bud_used:	db 0		; бюджет DI: потрачено в кадре (ед. 256 тактов); ISR выставляет свою цену
vec_wait_halted: db 0		; waitforVBlank: был ли halt в этом вызове
vec_spr_colcost: db 0		; бюджет DI: стоимость колонки спрайта
vec_spr_curport: db 0		; порт квазидиска текущего варианта спрайта (для возврата в стековый режим)
; --- кэш панели («по изменению»): что уже стоит в VRAM панели, $FF = неизвестно ---
vec_pc_char:	ds 128		; символы, ряды 20..23 x 32 колонки (код 0..63)
vec_pc_onoff:	ds 32		; drawScoreOnOff по колонке: 1 = выкл, 2 = вкл
vec_pc_meter:	ds 64		; шкалы draw_meter по колонке: [0] Y цветной части, [1] высота пустой
vec_key_hook:	dw 0		; экран пароля: ISR зовёт этот сканер (0 = не звать)
; --- таблицы уровня: читаются из набора (квазидиск, LEVELTAB) при старте уровня. Порядок и размеры
; обязаны совпадать с build_edd.level_table_blob: палитра, банки, число передних тайлов, пары ---
vec_palette:	ds 16
vec_bank_tab:	ds 40
fg_lut_n:	db 0
vec_pool_ban:	db 0		; 1 = на уровне есть двухплоскостной спрайт, пул не включаем
fg_tile_pairs:	ds 40		; до 20 передних тайлов на уровень

vec_dirtab:	ds 16		; копия таблицы дорожек уровней: в ROM она живёт по $7FEC и
				; затирается таблицей слотов, а при смене уровня нужна снова
vec_spr_skip2:	db 0		; хвост колонки для 2-плоскостного кадра: (32-NY)*3
vec_keys:	db 0		; маска клавиш H/J/X, снятая в ISR (бит0 H, бит2 J, бит3 X)
vec_key:	db 0		; ASCII нажатой клавиши (0 = ничего)
vec_ovl_tgt:	dw 0		; адрес функции движка для vec_ovl_call (оверлей паузы)
vec_in_game:	db 0		; 1 = идёт game (ISR разрешает выход по СТОП)
vec_pal_dirty:	db 1		; палитра: записать в ISR (старт / смена)
vec_zsave:	ds 8		; z_ix..z_ret на время плеера в ISR		; сохранение z_ix..z_hl2 на время плеера в ISR
ply_sd_cnt:	db 0		; Arkos: сдвиг частоты (4k) вместо самомодификации jr
ply_hd_cnt:	db 0
ply_sd_loop:	db 0
vec_fdd_ctl:	db $34		; НГМД: управление ($1C), бит 2 — сторона
vec_fdd_kv:	db 0
vec_fdd_sec:	db 1
vec_fdd_dst:	dw 0
vec_fdd_sp:	dw 0
vec_fdd_ptr:	dw 0		; загрузчик уровня: указатель в буфере сектора

; --- стек: до ближайшей границы страницы (минимум ~200 Б) ---
	ds 200
	ds ($ + 255) & $FF00 - $
vec_stack_top:
    if C8
; C8: обе таблицы заполняются на старте — живут в свободной плоскости 0 (VRAM бит 3 не отображается)
rev256		equ $8000
vec_slot_tab	equ $8100
    else
; --- таблица разворота байта (страница) и таблица слотов: в ОБРАЗЕ здесь лежит код vec_fdd_load —
; он отрабатывает при старте ДО инициализации таблиц, после чего его затирают rev256/слоты ---
rev256:
; Здесь, поверх области rev256/vec_slot_tab, лежит загрузчик уровня (src/vec/vec_fdd.asm):
; он отрабатывает при старте ДО того, как эти таблицы заполняются, после чего затирается ими.
; Тело подставляет build_vec (см. INCLUDE_FDD) — держать копию здесь нельзя: правки в vec_fdd.asm
; молча не попадали бы в сборку.
; @@INCLUDE vec_fdd.asm
	ds 512 - ($ - rev256)
vec_slot_tab equ rev256 + 256
    endif
