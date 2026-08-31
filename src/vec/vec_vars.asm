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
; vec_fdd.asm — стадия 2 загрузки с дискеты: EDD (256К, дорожки 4..29) -> квазидиск.
; Портовая карта Вектора (инверсия адресов ВГ93): $1B=команда/статус, $1A=трек, $19=сектор, $18=данные,
; $1C=управление (бит2 = сторона, инвертированная; $34/$30 как в штатном загрузчике).
; Протокол списан со штатного ПЗУ (loader.rom $02DB..): выбор/ожидание, RESTORE, чтение сектора ($80),
; шаг на трек ($58). Геометрия: 5 секторов по 1024 на сторону.
; Вызов: vec_fdd_load — если в квазидиске нет маркера 'IA' (страница 3, $C800) — читает 256 секторов.
FDD_MARK	equ $C800	; страница 3, свободное место перед музыкой
FDD_TRACK0	equ 4		; EDD начинается с дорожки 4 (raw 40960)

vec_fdd_load:
	; маркер уже есть (квазидиск загружен стендом/эмулятором) — выходим
	ld a,KV_WIN_MUSIC	; окно $A000-$DFFF -> страница 3
	out (KV_PORT),a
	ld a,(FDD_MARK)
	cp 'I'
	jp nz,vfl_go
	ld a,(FDD_MARK+1)
	cp 'A'
	jp z,vfl_done
vfl_go:
	xor a
	out (KV_PORT),a
	ld a,$34
	ld (vec_fdd_ctl),a
	call vfl_ctl		; выбрать дисковод/сторону, дождаться готовности
	xor a
	out ($1B),a		; RESTORE (на дорожку 0)
	call vfl_wait
	; дойти до дорожки FDD_TRACK0 шагами
	ld b,FDD_TRACK0
vfl_seek:
	ld a,$58
	out ($1B),a		; STEP-IN с обновлением трека
	call vfl_wait
	dec b
	jp nz,vfl_seek
	; 256 секторов = 256К: страницы квазидиска 0..3
	ld c,0			; страница
vfl_page:
	ld a,c
	rlca
	rlca			; биты 2-3 = страница стека
	or $10			; стековый режим
	ld (vec_fdd_kv),a
	ld hl,0			; адрес внутри страницы
	ld (vec_fdd_dst),hl
	ld b,64			; 64 сектора на страницу
vfl_sec:
	push bc
	; прочитать сектор (номер в vec_fdd_sec) в буфер string_area
	ld a,(vec_fdd_sec)
	ld c,a
	ld hl,string_area
	call vfl_read
	jp nz,vfl_go		; ошибка — начать сначала
	; буфер -> квазидиск стековым режимом (1024 Б = 512 push)
	ld hl,0
	add hl,sp
	ld (vec_fdd_sp),hl
	ld hl,(vec_fdd_dst)
	ld de,1024
	add hl,de
	ld (vec_fdd_dst),hl	; конец блока = стартовый SP (push пишет вниз)
	di
	ld a,(vec_fdd_kv)
	out (KV_PORT),a
	ld sp,hl
	ld hl,string_area+1023
	ld c,0			; счётчик пар (256 x 2 push = 1024 Б? нет: 512 push) — двумя вложенными
	ld b,2
vfl_push:
	ld d,(hl)
	dec hl
	ld e,(hl)
	dec hl
	push de
	dec c
	jp nz,vfl_push
	dec b
	jp nz,vfl_push
	xor a
	out (KV_PORT),a
	ld hl,(vec_fdd_sp)
	ld sp,hl
	ei
	; следующий сектор: 1..5 сторона 0, затем 1..5 сторона 1, затем шаг трека
	ld a,(vec_fdd_sec)
	inc a
	ld (vec_fdd_sec),a
	cp 6
	jp nz,vfl_next
	ld a,1
	ld (vec_fdd_sec),a
	ld a,(vec_fdd_ctl)
	xor 4			; смена стороны
	ld (vec_fdd_ctl),a
	call vfl_ctl
	and 4
	jp z,vfl_next		; перешли на сторону 1 — трек тот же
	ld a,$58
	out ($1B),a		; обе стороны прочитаны — шаг на следующий трек
	call vfl_wait
vfl_next:
	pop bc
	dec b
	jp nz,vfl_sec
	inc c
	ld a,c
	cp 4
	jp nz,vfl_page
vfl_done:
	xor a
	out (KV_PORT),a
	ret

; чтение одного сектора C -> (HL); Z = успех (как sub_0366 ПЗУ)
vfl_read:
	call vfl_ctl
	ld a,c
	out ($19),a
	ld de,$0103
	ld a,$80
	out ($1B),a
vfr_busy:
	in a,($1B)
	rrca
	jp nc,vfr_busy
vfr_drq:
	in a,($1B)
	and e
	sub d
	jp z,vfr_drq
	in a,($18)
	ld (hl),a
	inc hl
	jp p,vfr_drq
	dec hl
	in a,($1B)
	and $9C
	ret

vfl_ctl:
	ld a,(vec_fdd_ctl)
	out ($1C),a
	in a,($1B)
	rrca
	jp c,vfl_ctl
	ld a,(vec_fdd_ctl)
	ret
vfl_wait:
	in a,($1B)
	rrca
	jp c,vfl_wait
	ret
	ds 512 - ($ - rev256)
vec_slot_tab equ rev256 + 256
    endif
