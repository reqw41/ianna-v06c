; vec_vdp.asm — платформенный слой Вектор-06Ц вместо vdp.asm MSX2.
; Интерфейс тот же, что у VDP-процедур оригинала; реализация — pop-блит
; из квазидиска (DEMO=0) или ROM (DEMO=1).
;
; Экран: MSX y -> строка Вектора y+32 -> L = 223-y; x -> H = база плоскости + (x>>3).
; Плоскости $80,$A0,$C0,$E0; палитра idx = p0<<3|p1<<2|p2<<1|p3.
;
; Порт $10: б0-1 страница окон, б2-3 страница стека, б4 стек, б5 окно $A000-$DFFF,
; б6 окно $8000-$9FFF, б7 окно $E000-$FFFF. В стековом режиме POP читает квазидиск,
; обычные записи идут в ОЗУ/VRAM. Во время стековых блитов — DI, без call/ret.
;
; РЕНДЕР БЕЗ МЕРЦАНИЯ (DEMO=0): RedrawScreen_part1 собирает dirty-супертайлы не в VRAM,
; а в ПУЛ — страница 3 квазидиска $A000-$DFFF через ОКНО (128 слотов по 128 Б, формат
; тайла: [p][col][row]); RedrawScreen_part2 (vec_pool_flush) выбрасывает слоты в VRAM
; стеком, строками сверху вниз. Супертайлы без слота (панель, переполнение) рисуются
; напрямую. Окно открывается только внутри буферных блитов (панель рисуется между ними).

KV_PORT		equ $10
; C8 (из vdp_consts): 1 = 8 цветов, 3 плоскости. Индекс пикселя 0..7 живёт в битах 2..0 -> VRAM
; $A000/$C000/$E000; плоскость 0 ($8000-$9FFF) свободна и НИКОГДА не пишется (палитра зеркалит бит 3).
VEC_P0H		equ $80 + C8*$20	; старший байт первой пишущейся плоскости
VEC_NPL		equ 4 - C8		; плоскостей в данных/блитах
KV_STK_P0	equ $10
KV_STK_P1	equ $14
KV_STK_P2	equ $18
KV_STK_P3	equ $1C
KV_WIN_LEVEL	equ $61		; окна $8000-$DFFF -> страница 1 (карта уровня)
KV_POOL_WIN	equ $23		; окно $A000-$DFFF -> страница 3 (пул)
KV_WIN_MUSIC	equ $23		; окно $A000-$DFFF -> страница 3 (музыка по $C980, эффекты по $D980)
POOL_BASE	equ $A000
P3_FONT		equ $0000
P3_PANEL	equ $1000
P3_WEAPON	equ $2000
P3_ONOFF	equ $2400
Y_TOP_L		equ 223

; ---------------------------------------------------------------------------
setROM2:
setROM2_DI:
	ld (ROMBank1),a
	cp 1
	jp z,setrom_close
	cp 22
	jp c,setrom_sprite
	cp MUSIC_ROM_PAGE
	jp z,setrom_music
	and 1
	ret nz
    if DEMO
	ret
    else
	ld a,KV_WIN_LEVEL
	ld (vec_kv_shadow),a
	out (KV_PORT),a
	ret
    endif
setrom_music:
    if !DEMO
	ld a,KV_WIN_MUSIC
	ld (vec_kv_shadow),a
	out (KV_PORT),a
    endif
	ret
setrom_close:
    if !DEMO
	xor a
	ld (vec_kv_shadow),a
	out (KV_PORT),a
    endif
	ret
setrom_sprite:
	ld (vec_sprite_bank),a
	ret

setDisplayPage:
CopyTile:
copyPage:
VDPcmd:
VDPcmd_DI:
waitVDP:
VDP_SetPalette:
initVDPBuffers:
unpackVRAM:
fadeMSX2:
fadeinMSX2:
	ret

cls:
	ld hl,$8000
	ld bc,$8000
cls_l:
	ld (hl),0
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,cls_l
    if !DEMO
	jp vec_pc_reset		; панели на экране нет — кэш «неизвестно»
    else
	ret
    endif

; ---------------------------------------------------------------------------
    if DEMO
; Таблица банков MSX -> (порт стека, старший байт базы) для кадров спрайтов.
; банк 2 варвар общий -> стр.0 $0000; 3 прыжки -> стр.1 $0000;
; 7 скелет, 8 орк, 9 мумия, 12 камень -> стр.2 по $4000; остальные -> стр.0 (мусор, но безопасно)
vec_bank_tab:			; кадры по 576 Б (см. build_edd.SPRITE_BANKS)
	db KV_STK_P0,$00, KV_STK_P1,$A2		; 2,3 варвар: стр.0 $0000, стр.1 $A200
	db KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00	; 4,5,6 (оружие — пока нет)
	db KV_STK_P1,$00, KV_STK_P2,$00, KV_STK_P2,$60	; 7 скелет стр.1, 8 орк стр.2, 9 мумия стр.2 $6000
	db KV_STK_P0,$00, KV_STK_P0,$00			; 10,11
	db KV_STK_P3,$28				; 12 камень стр.3 $2800
	db KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00	; 13..21
    endif			; квазидисковая сборка: vec_bank_tab генерирует build_edd.py (gen_data.asm)

; ---------------------------------------------------------------------------
; Слот пула для супертайла: B=x px, C=y px -> A = слот или $FF (панель/нет)
vec_slot_for_bc:
	ld a,c
	cp 160
	jp nc,vsf_none
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
	ld h,vec_slot_tab/256
	ld a,(hl)
	ret
vsf_none:
	ld a,$ff
	ret
; A = слот -> HL = адрес в пуле ($A000 + slot*128)
vec_pool_addr:
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ret

; ---------------------------------------------------------------------------
; Общий стековый блит 128 Б «формат тайла» -> VRAM: SP уже установлен, порт выведен,
; D = H колонки 0 плоскости 0, E = L верхней строки. Возврат: jp (vec_blit_ret).
vec_blit128_vram:		; C8: 96 Б (3 плоскости)
	ld a,VEC_NPL
	ld (vec_plane_cnt),a
vb_plane:
	ld h,d
	ld l,e
	ld a,2
	ld (vec_col_cnt),a
vb_col:
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	inc h
	ld l,e
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,vb_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,vb_plane
	ld hl,(vec_blit_ret)
	jp (hl)

; Универсальный блит колонок [p][col][row] -> VRAM для панели: SP установлен, порт выведен,
; D/E = dest, vec_bl_cols = колонок, vec_bl_pops = строк/2. Возврат jp (vec_blit_ret).
vec_blit_cols:
	ld a,(vec_bl_planes)
	ld (vec_plane_cnt),a
	ld a,VEC_NPL
	ld (vec_bl_planes),a	; по умолчанию все плоскости (vec_load_panel просит по одной)
vbc_plane:
	ld a,(vec_bl_cols)
	ld (vec_col_cnt),a
	ld h,d
	ld l,e
vbc_col:
	ld a,(vec_bl_pops)
	ld (vec_row_cnt),a
vbc_row:
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,vbc_row
	inc h
	ld l,e
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,vbc_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,vbc_plane
	ld hl,(vec_blit_ret)
	jp (hl)

; Вход в стековый режим: HL = источник (SP), A = байт порта. Сохраняет SP, DI.
; (это обычная процедура: вызывается ДО подмены SP)
vec_stk_enter:
	di
	ex de,hl
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ex de,hl
	ld sp,hl
	out (KV_PORT),a
	ret			; ВНИМАНИЕ: ret по подменённому стеку недопустим — поэтому см. макро-вызов ниже
; Поэтому используем не call, а inline: см. STK_BEGIN в процедурах.

; Выход: закрыть порт, вернуть SP, EI
vec_stk_leave:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ret


; ---------------------------------------------------------------------------
; БЮДЖЕТ DI НА КАДР. На Векторе прерывание от кадра НЕ защёлкивается: если в момент обратного хода
; включён DI, оно теряется (RTL MiSTer, Emu80; vector06js держит запрос — там дефекта не видно).
; Стековые блиты идут под DI, поэтому перед каждым блитом проверяем программный счётчик потраченного
; в кадре (vec_bud_used, ед. 256 тактов): ISR в конце выставляет свою цену (VEC_ISR_COST), вывод тика
; начинается сразу после прерывания (waitforVBlank выходит только после halt, раздача слотов пула —
; до ожидания), так что счётчик = фаза кадра. Если «потрачено + стоимость» не влезает до обратного
; хода — `halt`. Стоимости откалиброваны headless по модели слотов шины Вектора (tools/profile_vec.py,
; cpu_ready: 1 обращение к шине за 4 такта): тайл 16 + 6 накладных цикла RedrawInvTiles, FG 29 + 6,
; слот сброса ~18, спрайт по КОЛОНКАМ: прямой ~1.5 ед./строку, зеркальный ~2.1 (+8 на колонку),
; панель cols*pops/2 + 2. Таймер ВИ53 не трогаем — он нужен под музыку.
; Вход: A = стоимость в единицах 256 тактов. Портит A и флаги.
VEC_BUDGET_LIMIT equ 228	; кадр = 234 ед.; запас 6 на неучтённые накладные (стоимости откалиброваны стендом calib по реальным тактам)
VEC_ISR_COST	equ 24		; ISR с музыкой: ур.2 медиана 20 / p90 24, ур.1 медиана 22 / макс 29 (calib)
vec_budget:
	push hl
	ld l,a
	ld a,(vec_bud_used)
	add a,l
	jp c,vbg_wait
	cp VEC_BUDGET_LIMIT
	jp c,vbg_ok
vbg_wait:
	push hl			; L = стоимость, нужна после halt
	ld hl,(vec_bud_halts)	; статистика: сколько раз ждали кадр
	inc hl
	ld (vec_bud_halts),hl
	pop hl
	halt			; следующий VBlank (вне блита, EI); ISR выставит свою цену
	ld a,(vec_bud_used)
	add a,l
vbg_ok:
	ld (vec_bud_used),a
	pop hl
	ret
; Бюджет колонки спрайта ИЗНУТРИ стекового режима (SP подменён — call нельзя, вход jp, возврат
; jp (vec_blit_ret)). Выходим из стекового режима, проверяем бюджет с EI, входим обратно.
; Портит A, флаги и HL.
vec_spr_colbud:
	ld hl,0
	add hl,sp
	ld (vec_spr_src),hl	; текущая позиция источника
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ld a,(vec_spr_colcost)
	call vec_budget
	di
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_curport)
	out (KV_PORT),a
	ld hl,(vec_blit_ret)	; HL в головах колоночных циклов не жив
	jp (hl)

; ---------------------------------------------------------------------------
    if C8
; Палитра экрана: VEC_SCRPAL + (levely*width+levelx)*8 -> vec_palette (0..7 и зеркало 8..15), флаг ISR.
; Зовётся из DrawScreen (патч build_vec). Окно уровня открывается через setROM2 (тень для ISR согласована).
vec_scr_palette:
	push hl
	push de
	push bc
	ld a,(ROMBank1)
	push af
	ld a,22
	call setROM2
	ld a,(current_levely)
	ld b,a
	ld a,(level_width)
	ld c,a
	xor a
vsp_mul:
	dec b
	jp m,vsp_muld
	add a,c
	jp vsp_mul
vsp_muld:
	ld c,a
	ld a,(current_levelx)
	add a,c
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,VEC_SCRPAL
	add hl,de
	ld de,vec_palette
	ld b,8
vsp_cp:
	ld a,(hl)
	ld (de),a
	push hl
	ld hl,8
	add hl,de
	ld (hl),a
	pop hl
	inc hl
	inc de
	dec b
	jp nz,vsp_cp
	pop af
	call setROM2
	ld a,1
	ld (vec_pal_dirty),a
	pop bc
	pop de
	pop hl
	ret
    endif
; ---------------------------------------------------------------------------
; drawTile: A = тайл, B = X px, C = Y px
drawTile:
	push hl
	push de
	push bc
	push af
	pop af
    if DEMO
	ld l,a
	ld h,demo_tile_lut/256
	ld a,(hl)
	ld l,0
	rrca
	jp nc,dt_a0
	ld l,$80
dt_a0:
	and $7f
	ld h,a
	ld de,DEMO_TILES_BASE
	add hl,de
    else
	ld d,a
	rrca
	and $7f
	add a,BG_TILES_BASE/256
	ld h,a
	ld a,d
	and 1
	rrca
	ld l,a
    endif
	ld (vec_blit_src),hl
    if !DEMO
	ld a,(vec_pool_on)
	or a
	jp z,dt_direct
	call vec_slot_for_bc
	cp 80
	jp nc,dt_direct		; $FE (грязный без слота) и $FF — прямо в VRAM
	call vec_pool_addr
	ld a,18 - C8*3		; бюджет DI: тайл в слот — 16ц медиана 17.5 / c8 14.1 (calib)
	call vec_budget
	ex de,hl		; DE = слот в окне
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_POOL_WIN|KV_STK_P0
	out (KV_PORT),a
	ex de,hl		; HL = dest
	ld a,8 - C8*2		; C8: 96 Б = 6 итераций по 16
	ld (vec_row_cnt),a
dtb_loop:
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dtb_loop
	jp dt_end
    endif
dt_direct:
	ld a,22 - C8*4		; бюджет DI: тайл прямо в VRAM — 16ц медиана 20.8 / c8 17.1 (calib; вкл. обход RedrawInvTiles)
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
    if !DEMO
	ld a,KV_STK_P0
	out (KV_PORT),a
    endif
	ld hl,dt_end
	ld (vec_blit_ret),hl
	jp vec_blit128_vram
dt_end:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	pop de
	pop hl
	ret

; ---------------------------------------------------------------------------
; drawFGTile: A = тайл (≠0), B, C. Передний тайл [p][col][row]:[data,mask], 256 Б
drawFGTile:
	push hl
	push de
	push bc
	push af
	ld a,31 - C8*6		; FG: 16ц медиана 29-30 / c8 24.4 (calib)
	call vec_budget
	pop af
	ld l,a
	ld h,fg_tile_lut/256
	ld a,(hl)
	or a
	jp z,dft_exit
	dec a
	add a,FG_TILES_BASE/256
	ld h,a
	ld l,0
	ld (vec_blit_src),hl
    if !DEMO
	ld a,(vec_pool_on)
	or a
	jp z,dft_direct
	call vec_slot_for_bc
	cp 80
	jp nc,dft_direct
	call vec_pool_addr
	ex de,hl
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_POOL_WIN|KV_STK_P0	; FG-тайлы — страница 0 ($5D00)
	out (KV_PORT),a
	ex de,hl
	ld a,16 - C8*4		; C8: 192 Б = 12 итераций
	ld (vec_row_cnt),a
dftb_loop:
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dftb_loop
	jp dft_end
    endif
dft_direct:
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
    if !DEMO
	ld a,KV_STK_P0		; FG-тайлы — страница 0
	out (KV_PORT),a
    endif
	ld a,VEC_NPL
	ld (vec_plane_cnt),a
dft_plane:
	ld h,d
	ld l,e
	ld a,2
	ld (vec_col_cnt),a
dft_col:
	; 16 строк развёрнуто (счётчик в памяти стоил ~52 такта на байт)
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	inc h
	ld l,e
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dft_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dft_plane
dft_end:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
dft_exit:
	pop bc
	pop de
	pop hl
	ret

; ---------------------------------------------------------------------------
; drawSprite: A = направление (0 прямо / 1 зеркало), B = X px (кратно 8), C = Y px,
; HL = адрес MSX ($8000 + n*384). Высота NY = (vdpCmdSprite+VDP_NY).
; Кадр 384 Б: for col 0..2: for row 31..0: [p0,p1,p2,p3]; маска на лету.
drawSprite:
	push af
	ld a,10 + C8*2		; накладные DrawSpriteList/пролога спрайта: 16ц 9.8 / c8 11.8 ед. (calib)
	call vec_budget
	pop af
	push af
	ld de,-$8000
	add hl,de		; n*384 (MSX) -> n*576: + половина
	ld a,h
	or a
	rra
	ld d,a
	ld a,l
	rra
	ld e,a
	add hl,de
    if DEMO
	ld de,DEMO_FRAMES_BASE
	add hl,de
    else
	push hl
	ld a,(vec_sprite_bank)
	sub 2
	and $1f
	add a,a
	ld l,a
	ld h,0
	ld de,vec_bank_tab
	add hl,de
	ld a,(hl)
	ld (vec_spr_port),a
	inc hl
	ld d,(hl)
	ld e,0
	pop hl
	add hl,de
    endif
	ld a,(vdpCmdSprite+VDP_NY)
	ld (vec_spr_ny),a
	ld e,a
	ld a,32
	sub e
	add a,a
	ld d,a
	add a,a
	add a,d			; (32-NY)*6: строка = 6 байт [p0,маска,p1,p2,p3,пропуск]
	ld (vec_spr_skip),a
	ld e,a
	ld d,0
	add hl,de
	ld (vec_spr_src),hl
	ld a,(vec_spr_ny)
	add a,c
	dec a
	ld (vec_spr_ybot),a	; нижняя строка (MSX y)
	ld e,a
	ld a,Y_TOP_L
	sub e
	ld (vec_spr_lbot),a	; L нижней строки
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	ld (vec_spr_cx),a	; колонка экрана 0..31
	add a,VEC_P0H
	ld (vec_spr_hcol),a
	pop af
	ld (vec_spr_dir),a
	; бюджет по колонкам, калибровка по стенду (calib: реальные такты между вызовами бюджета, сцена с големом):
	; прямой через пул медиана 1.35 ед./строку (p90 1.7) -> NY + NY/2 + 5; зеркальный 2.25 (p90 2.4) -> 2*NY + NY/4 + 5
	push de
	ld a,(vec_spr_ny)
	ld e,a
	ld a,(vec_spr_dir)
	or a
	ld a,e
	jp z,ds_cost_fwd
	rrca
	rrca
	and $3f			; NY/4
	add a,e
	add a,e			; зеркало: 2*NY + NY/4
	jp ds_cost
ds_cost_fwd:
	rrca
	and $7f			; NY/2
	add a,e			; прямой: NY + NY/2
ds_cost:
	add a,5
	ld (vec_spr_colcost),a
	pop de
    if !DEMO
	; буферный путь: пул включён и все супертайлы спрайта имеют слоты
	ld a,(vec_pool_on)
	or a
	jp z,ds_direct
	call vec_spr_slots_ok
	jp nc,ds_direct
	jp drawSprite_pool
    endif
ds_direct:
	ld a,(vec_spr_dir)
	or a
	jp nz,drawSprite_mirror
	ld a,3
	ld (vec_col_cnt),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
    if !DEMO
	ld a,(vec_spr_port)
	ld (vec_spr_curport),a
	out (KV_PORT),a
    endif
ds_col:
	ld hl,ds_col_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud	; бюджет DI на колонку
ds_col_go:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
ds_row:
	pop bc			; C = p0, B = маска (готовая)
	pop de			; E = p1, D = p2
	ld a,b
	and (hl)
	or c
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or d
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
    if C8
	pop de			; E = 0, D = пропуск (пустых строк выше)
	ld a,h
	sub $60			; указатель уже шагнул за 3-ю плоскость (+$60)
	ld h,a
    else
	pop de			; E = p3, D = пропуск (пустых строк выше)
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
    endif
	inc l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp z,ds_col_end
	ld e,a			; осталось строк
	ld a,d			; пропуск: k = min(пропуск, осталось-1)
	or a
	jp z,ds_row
	ld a,e
	dec a
	jp z,ds_row
	cp d
	jp c,ds_k
	ld a,d
ds_k:
	ld d,a
	ld a,e
	sub d
	ld (vec_row_cnt),a
	ld a,l
	add a,d
	ld l,a			; k строк вверх
	ld (vec_spr_p01),hl
	ld a,d
	add a,a
	ld e,a
	add a,a
	add a,e		; 6k байт источника
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,(vec_spr_p01)
	jp ds_row
ds_col_end:
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_spr_hcol)
	inc a
	ld (vec_spr_hcol),a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,ds_col
	jp vec_stk_leave
drawSprite_mirror:
	ld a,(vec_spr_hcol)
	add a,2
	ld (vec_spr_hcol),a
	ld a,3
	ld (vec_col_cnt),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
    if !DEMO
	ld a,(vec_spr_port)
	ld (vec_spr_curport),a
	out (KV_PORT),a
    endif
dsm_col:
	ld hl,dsm_col_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud	; бюджет DI на колонку
dsm_col_go:
	ld a,(vec_spr_hcol)
	ld d,a
	ld a,(vec_spr_lbot)
	ld e,a
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
dsm_row:
	ex de,hl
	ld (vec_spr_dst),hl	; адрес VRAM (H колонки, L строки) — на время просмотра rev256
	ld h,rev256/256
	pop bc			; C = p0, B = маска
	ld l,c
	ld a,(hl)
	ld (vec_spr_p01),a	; p0 зеркально
	ld l,b
	ld a,(hl)
	ld (vec_spr_mask),a	; маска зеркально
	pop de			; E = p1, D = p2
	ld l,e
	ld e,(hl)
	ld l,d
	ld d,(hl)
    if C8
	pop bc			; C = 0, B = пропуск
	ld hl,(vec_spr_dst)
	ld a,h
	add a,$40
	ld h,a			; плоскость 2 из трёх ($E000)
	ld a,(vec_spr_mask)
	and (hl)
	or d
	ld (hl),a
    else
	pop bc			; C = p3, B = пропуск
	ld l,c
	ld c,(hl)
	ld hl,(vec_spr_dst)
	ld a,h
	add a,$60
	ld h,a			; плоскость 3
	ld a,(vec_spr_mask)
	and (hl)
	or c
	ld (hl),a
	ld a,h
	sub $20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)
	or d
	ld (hl),a
    endif
	ld a,h
	sub $20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)
	or e
	ld (hl),a
	ld a,h
	sub $20
	ld h,a
	ld a,(vec_spr_p01)
	ld e,a
	ld a,(vec_spr_mask)
	and (hl)
	or e
	ld (hl),a
	inc l
	ex de,hl		; DE = адрес следующей строки
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp z,dsm_col_end
	ld c,a			; осталось строк
	ld a,b			; пропуск
	or a
	jp z,dsm_row
	ld a,c
	dec a
	jp z,dsm_row
	cp b
	jp c,dsm_k
	ld a,b
dsm_k:
	ld b,a
	ld a,c
	sub b
	ld (vec_row_cnt),a
	ld a,e
	add a,b
	ld e,a			; k строк вверх
	ld a,b
	add a,a
	ld c,a
	add a,a
	add a,c
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl		; 6k байт источника
	jp dsm_row
dsm_col_end:
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_spr_hcol)
	dec a
	ld (vec_spr_hcol),a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dsm_col
	jp vec_stk_leave

    if !DEMO
; ---- проверка слотов под спрайт: CY=1 если все супертайлы (cx..cx+2, ybot-ny+1..ybot) имеют слот
vec_spr_slots_ok:
	ld a,(vec_spr_ybot)
	cp 160
	jp nc,vss_no
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld (vec_tmp_sx),a	; sx0
	ld a,(vec_spr_cx)
	add a,2
	rrca
	and $0f
	ld (vec_tmp_sx1),a	; sx1
	ld a,(vec_spr_ybot)
	and $f0
	ld c,a			; sy1*16
	ld a,(vec_spr_ny)
	ld b,a
	ld a,(vec_spr_ybot)
	sub b
	inc a
	and $f0
	ld b,a			; sy0*16
vss_y:
	ld a,(vec_tmp_sx)
vss_x:
	or b
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	cp 80
	jp nc,vss_no
	ld a,l
	and $0f
	ld l,a
	ld a,(vec_tmp_sx1)
	cp l
	jp z,vss_ynext
	ld a,l
	inc a
	jp vss_x
vss_ynext:
	ld a,b
	cp c
	jp z,vss_yes
	add a,16
	ld b,a
	jp vss_y
vss_yes:
	scf
	ret
vss_no:
	or a
	ret

; ---- спрайт в пул. Колонка экрана cx (0..31); слот супертайла (cx>>1, row>>4);
; адрес = $A000 + slot*128 + (cx&1)*16 + (row&15); плоскости +32 (в пределах страницы).
drawSprite_pool:
	ld a,(vec_spr_dir)
	or a
	jp nz,dsp_mirror
	ld a,3
	ld (vec_col_cnt),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	or KV_POOL_WIN
	ld (vec_spr_curport),a
	out (KV_PORT),a
dsp_col:			; бюджет DI — по сегментам (dsp_seg), не по колонкам
dsp_col_go:
	ld a,(vec_spr_ny)
	ld (vec_rows_left),a
	ld a,(vec_spr_ybot)
	ld (vec_spr_row),a
dsp_seg:
	; слот и адрес сегмента
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld l,a
	ld a,(vec_spr_row)
	and $f0
	or l
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ld a,(vec_spr_cx)
	and 1
	rlca
	rlca
	rlca
	rlca
	add a,l
	ld l,a
	ld a,(vec_spr_row)
	and 15
	add a,l
	ld l,a			; HL = адрес плоскости 0 нижней строки сегмента
	; n = min(rows_left, (row&15)+1)
	ld a,(vec_spr_row)
	and 15
	inc a
	ld b,a
	ld a,(vec_rows_left)
	cp b
	jp nc,dsp_n_ok
	ld b,a
dsp_n_ok:
	ld a,b
	ld (vec_seg_cnt),a
	ld a,(vec_rows_left)
	sub b
	ld (vec_rows_left),a
	ld a,(vec_spr_row)
	sub b
	ld (vec_spr_row),a
	; бюджет DI на сегмент (calib: прямой 1.35 ед./строку + голова): n + n/2 + 2. HL — единственный живой регистр
	ld (vec_spr_dst),hl
	ld a,b
	rrca
	and $7f
	add a,b
	add a,2
	ld (vec_spr_colcost),a
	ld hl,dsp_seg_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud
dsp_seg_go:
	ld hl,(vec_spr_dst)
dsp_row:
	pop bc			; C = p0, B = маска
	pop de			; E = p1, D = p2
	ld a,b
	and (hl)
	or c
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or d
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
    if C8
	pop de			; E = 0 (заполнитель), D = пропуск
	ld a,l
	sub 96+1		; указатель уже шагнул за 3-ю плоскость (+96) — назад на плоскость 0 и строкой выше
    else
	pop de			; E = p3, D = пропуск
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,l
	sub 96+1		; назад на плоскость 0 и строкой выше
    endif
	ld l,a
	ld a,(vec_seg_cnt)
	dec a
	ld (vec_seg_cnt),a
	jp z,dsp_seg_end
	ld e,a			; осталось строк в сегменте
	ld a,d
	or a
	jp z,dsp_row
	ld a,e
	dec a
	jp z,dsp_row
	cp d
	jp c,dsp_k
	ld a,d
dsp_k:
	ld d,a
	ld a,e
	sub d
	ld (vec_seg_cnt),a
	ld a,l
	sub d
	ld l,a			; k строк вверх (в пуле строка = -1)
	ld (vec_spr_p01),hl
	ld a,d
	add a,a
	ld e,a
	add a,a
	add a,e
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,(vec_spr_p01)
	jp dsp_row
dsp_seg_end:
	ld a,(vec_rows_left)
	or a
	jp nz,dsp_seg
	; следующая колонка
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_spr_cx)
	inc a
	ld (vec_spr_cx),a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dsp_col
	jp vec_stk_leave
dsp_mirror:
	ld a,(vec_spr_cx)
	add a,2
	ld (vec_spr_cx),a
	ld a,3
	ld (vec_col_cnt),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	or KV_POOL_WIN
	ld (vec_spr_curport),a
	out (KV_PORT),a
dspm_col:			; бюджет DI — по сегментам (dspm_seg)
dspm_col_go:
	ld a,(vec_spr_ny)
	ld (vec_rows_left),a
	ld a,(vec_spr_ybot)
	ld (vec_spr_row),a
dspm_seg:
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld l,a
	ld a,(vec_spr_row)
	and $f0
	or l
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ld a,(vec_spr_cx)
	and 1
	rlca
	rlca
	rlca
	rlca
	add a,l
	ld l,a
	ld a,(vec_spr_row)
	and 15
	add a,l
	ld l,a
	ex de,hl		; DE = адрес в пуле
	ld a,(vec_spr_row)
	and 15
	inc a
	ld b,a
	ld a,(vec_rows_left)
	cp b
	jp nc,dspm_n_ok
	ld b,a
dspm_n_ok:
	ld a,b
	ld (vec_seg_cnt),a
	ld a,(vec_rows_left)
	sub b
	ld (vec_rows_left),a
	ld a,(vec_spr_row)
	sub b
	ld (vec_spr_row),a
	; бюджет DI на сегмент, зеркальный. 16ц: 2n + n/2 + 2 (медиана 2.25/строку, p90 2.4); c8: 2n + 2
	; (медиана 18.6 при n~8, p90 33.8 при n=16 — впритык к 34). Живой регистр — DE (адрес в пуле)
	ex de,hl
	ld (vec_spr_dst),hl
	ld a,b
    if C8
	add a,b
	add a,2
    else
	rrca
	and $7f
	add a,b
	add a,b
	add a,2
    endif
	ld (vec_spr_colcost),a
	ld hl,dspm_seg_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud
dspm_seg_go:
	ld hl,(vec_spr_dst)
	ex de,hl
dspm_row:
	ex de,hl
	ld (vec_spr_dst),hl	; адрес в пуле — на время просмотра rev256
	ld h,rev256/256
	pop bc			; C = p0, B = маска
	ld l,c
	ld a,(hl)
	ld (vec_spr_p01),a
	ld l,b
	ld a,(hl)
	ld (vec_spr_mask),a
	pop de			; E = p1, D = p2
	ld l,e
	ld e,(hl)
	ld l,d
	ld d,(hl)
    if C8
	pop bc			; C = 0, B = пропуск
	ld hl,(vec_spr_dst)
	ld a,l
	add a,64
	ld l,a			; плоскость 2 из трёх
	ld a,(vec_spr_mask)
	and (hl)
	or d
	ld (hl),a
    else
	pop bc			; C = p3, B = пропуск
	ld l,c
	ld c,(hl)
	ld hl,(vec_spr_dst)
	ld a,l
	add a,96
	ld l,a			; плоскость 3
	ld a,(vec_spr_mask)
	and (hl)
	or c
	ld (hl),a
	ld a,l
	sub 32
	ld l,a
	ld a,(vec_spr_mask)
	and (hl)
	or d
	ld (hl),a
    endif
	ld a,l
	sub 32
	ld l,a
	ld a,(vec_spr_mask)
	and (hl)
	or e
	ld (hl),a
	ld a,l
	sub 32
	ld l,a
	ld a,(vec_spr_p01)
	ld e,a
	ld a,(vec_spr_mask)
	and (hl)
	or e
	ld (hl),a
	dec l			; строкой выше
	ex de,hl
	ld a,(vec_seg_cnt)
	dec a
	ld (vec_seg_cnt),a
	jp z,dspm_seg_end
	ld c,a
	ld a,b
	or a
	jp z,dspm_row
	ld a,c
	dec a
	jp z,dspm_row
	cp b
	jp c,dspm_k
	ld a,b
dspm_k:
	ld b,a
	ld a,c
	sub b
	ld (vec_seg_cnt),a
	ld a,e
	sub b
	ld e,a			; k строк вверх
	ld a,b
	add a,a
	ld c,a
	add a,a
	add a,c
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	jp dspm_row
dspm_seg_end:
	ld a,(vec_rows_left)
	or a
	jp nz,dspm_seg
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_spr_cx)
	dec a
	ld (vec_spr_cx),a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dspm_col
	jp vec_stk_leave

; ---------------------------------------------------------------------------
; vec_pool_begin — вызывается в начале RedrawScreen_part1 / RedrawScreen:
; раздать слоты пула dirty-супертайлам (строки 0..9). Переполнение (>128) -> прямой режим.
; vec_slot_init: таблица слотов = $FF (единожды при старте; дальше её чистит сам сброс пула)
vec_slot_init:
	ld hl,vec_slot_tab
	ld b,0
vpb_clr:
	ld (hl),$ff
	inc l
	dec b
	jp nz,vpb_clr
	ret
vec_pool_begin:
	; таблицу слотов НЕ чистим (256 байт = 40 ед. каждый тик): все помеченные $FE/слот записи
	; проходит сброс пула и возвращает $FF; при переполнении чистится целиком
	xor a
	ld (vec_slot_next),a
	ld (vec_pool_on),a
	ld a,(ndirtyrects)
	or a
	ret z
	ld c,a
	ld de,tiles_dirty
vpb_rect:
	ld a,(de)		; xs
	ld (vec_tmp_sx),a
	inc de
	ld a,(de)		; ys
	ld (vec_tmp_sy),a
	inc de
	ld a,(de)		; nx
	ld (vec_tmp_nx),a
	inc de
	ld a,(de)		; ny
	ld (vec_tmp_ny),a
	inc de
	push de
	push bc
vpb_y:
	ld a,(vec_tmp_sy)
	cp 10
	jp nc,vpb_rect_done	; панель — без слотов
	rlca
	rlca
	rlca
	rlca
	ld (vec_tmp_row16),a
	ld a,(vec_tmp_nx)
	ld b,a
	ld a,(vec_tmp_sx)
	ld c,a
vpb_x:
	ld a,(vec_tmp_row16)
	or c
	ld l,a
	ld h,vec_slot_tab/256
	ld (hl),$fe		; грязный супертайл без слота: рисуется прямо в VRAM (и BG, и FG)
vpb_x_next:
	inc c
	dec b
	jp nz,vpb_x
	ld a,(vec_tmp_sy)
	inc a
	ld (vec_tmp_sy),a
	ld a,(vec_tmp_ny)
	dec a
	ld (vec_tmp_ny),a
	jp nz,vpb_y
vpb_rect_done:
	pop bc
	pop de
	dec c
	jp nz,vpb_rect
	; Слоты — только грязным супертайлам под спрайтами, которые рисуются в этом тике: и под текущей,
	; и под ПРОШЛОЙ позицией (иначе старое место стирается прямым путём в фазе сборки, а спрайт на новом
	; появляется лишь при сбросе — на кадр герой пропадает/режется). Остальное — в VRAM одним проходом.
	xor a
	ld (vec_tmp_ovf),a
	ld de,SPDATA
	ld c,MAX_SPRITES
	ld hl,vec_spr_prev
	ld (vec_tmp_rp),hl
vpb_spr:
	ld a,(de)		; включён?
	inc de
	ld l,a
	ld a,(de)
	dec de
	or l
	jp z,vpb_spr_off
	ld hl,7
	add hl,de
	ld a,(hl)		; перерисовывается?
	or a
	jp z,vpb_spr_copy
	push de
	push bc
	ld hl,3
	add hl,de
	call vpb_rect_assign	; текущий прямоугольник
	ld hl,(vec_tmp_rp)
	call vpb_rect_assign	; прошлый
	pop bc
	pop de
vpb_spr_copy:
	ld hl,3			; prev := текущий (x,y,nx,ny)
	add hl,de
	push de
	ex de,hl
	ld hl,(vec_tmp_rp)
	ld b,4
vpb_cp:
	ld a,(de)
	ld (hl),a
	inc hl
	inc de
	dec b
	jp nz,vpb_cp
	pop de
	jp vpb_spr_adv
vpb_spr_off:
	ld hl,(vec_tmp_rp)	; выключен: prev.nx = 0
	inc hl
	inc hl
	ld (hl),0
vpb_spr_adv:
	ld hl,(vec_tmp_rp)
	inc hl
	inc hl
	inc hl
	inc hl
	ld (vec_tmp_rp),hl
	ld hl,8
	add hl,de
	ex de,hl
	dec c
	jp nz,vpb_spr
	ld a,(vec_tmp_ovf)
	or a
	jp nz,vpb_overflow2
	ld a,1
	ld (vec_pool_on),a
	ret
vpb_overflow2:
	ld hl,vec_slot_tab
	ld b,0
vpb_clr3:
	ld (hl),$ff
	inc l
	dec b
	jp nz,vpb_clr3
	xor a
	ld (vec_pool_on),a
	ret
; vpb_rect_assign: HL -> [x px, y px, nx, ny (символы по 8)]; грязным ($FE) супертайлам под ним — слоты.
; nx = 0 — пропуск. Переполнение слотов -> vec_tmp_ovf = 1.
vpb_rect_assign:
	inc hl
	inc hl
	ld a,(hl)		; nx
	or a
	ret z
	ld b,a
	dec hl
	dec hl
	ld a,(hl)		; x
	rrca
	rrca
	rrca
	rrca
	and $0f
	ld (vec_tmp_sx),a	; sx0
	ld a,(hl)
	dec a
vpb_sx1:
	add a,8
	jp c,vpb_sx1_clip
	dec b
	jp nz,vpb_sx1		; x + nx*8 - 1
	rrca
	rrca
	rrca
	rrca
	and $0f
	jp vpb_sx1_ok
vpb_sx1_clip:
	ld a,15
vpb_sx1_ok:
	ld (vec_tmp_sx1),a	; sx1
	inc hl
	ld a,(hl)		; y px
	cp 160
	ret nc			; панель
	and $f0
	ld (vec_tmp_sy),a	; sy0*16
	inc hl
	inc hl
	ld b,(hl)		; ny
	dec hl
	dec hl
	ld a,(hl)		; y
	dec a
vpb_sy1:
	add a,8
	dec b
	jp nz,vpb_sy1		; y + ny*8 - 1
	cp 160
	jp c,vpb_sy_ok
	ld a,159
vpb_sy_ok:
	and $f0
	ld (vec_tmp_ny),a	; sy1*16
vpb_sy:
	ld a,(vec_tmp_sx)
vpb_sxl:
	ld b,a
	ld a,(vec_tmp_sy)
	or b
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	cp $fe
	jp nz,vpb_sx_next	; не грязный (или уже со слотом)
	ld a,(vec_slot_next)
	cp 80			; слоты 0..79 = $A000-$C7FF; выше $C980 — музыка
	jp nc,vpb_ovf
	ld (hl),a
	inc a
	ld (vec_slot_next),a
vpb_sx_next:
	ld a,(vec_tmp_sx1)
	cp b
	jp z,vpb_sy_next
	ld a,b
	inc a
	jp vpb_sxl
vpb_sy_next:
	ld a,(vec_tmp_sy)
	ld b,a
	ld a,(vec_tmp_ny)
	cp b
	ret z
	ld a,b
	add a,16
	ld (vec_tmp_sy),a
	jp vpb_sy
vpb_ovf:
	ld a,1
	ld (vec_tmp_ovf),a
	ret
vpb_overflow:
	pop bc
	pop de
	ld hl,vec_slot_tab
	ld b,0
vpb_clr2:
	ld (hl),$ff
	inc l
	dec b
	jp nz,vpb_clr2
	xor a
	ld (vec_pool_on),a
	ret

; vec_pool_flush — вместо TransferDirtyTiles в RedrawScreen_part2: слоты -> VRAM,
; строками супертайлов сверху вниз (0..9), затем ndirtyrects=0.
vec_pool_flush:
	; Сброс идёт С РАЗРЕШЁННЫМИ прерываниями и БЕЗ единого обращения к настоящему стеку: порт весь
	; сброс держится в стековом режиме (страница 3 = пул), цикл — на ячейках, адрес слота считается
	; inline, блит возвращается через jp (vec_blit_ret). RST/push прерывания ложатся в страницу 3 под
	; SP — это уже вытолкнутые байты пула или свободная область. ISR держит стековые биты порта
	; (vec_kv_shadow = KV_STK_P3). Переходы режима (2 на сброс) — под коротким DI и только не у края
	; кадра (по счётчику бюджета), чтобы не потерять прерывание.
	ld a,(vec_kv_shadow)
	ld (vec_kv_prev),a	; окно главного кода — вернуть в конце (и когда пула нет)
	ld a,(vec_pool_on)
	or a
	jp z,vpf_done
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl	; настоящий SP
	ld a,(vec_bud_used)	; у края кадра (> 205 ед.) — дождаться прерывания: переход режима не должен
	cp 206			; совпасть с обратным ходом
	jp c,vpf_go
	halt
vpf_go:
	ld a,KV_STK_P3
	di
	ld (vec_kv_shadow),a
	out (KV_PORT),a
	ei
	xor a
	ld (vec_tmp_sy),a	; текущая строка
vpf_yloop:
	ld a,(ndirtyrects)
	ld (vec_tmp_rc),a
	ld hl,tiles_dirty
	ld (vec_tmp_rp),hl
vpf_rect:
	ld hl,(vec_tmp_rp)
	ld a,(hl)		; xs
	ld (vec_tmp_sx),a
	inc hl
	ld b,(hl)		; ys
	inc hl
	ld a,(hl)		; nx
	ld (vec_tmp_nx),a
	inc hl
	ld a,(hl)		; ny
	inc hl
	ld (vec_tmp_rp),hl
	add a,b
	ld c,a			; ys+ny
	ld a,(vec_tmp_sy)
	cp b
	jp c,vpf_next		; y < ys
	cp c
	jp nc,vpf_next		; y >= ys+ny
	ld a,(vec_tmp_nx)
	ld (vec_tmp_bx),a	; счётчик колонок
	ld a,(vec_tmp_sx)
	ld (vec_tmp_cx),a	; текущая колонка
vpf_x:
	ld a,(vec_tmp_sy)
	rlca
	rlca
	rlca
	rlca
	ld b,a			; sy*16
	ld a,(vec_tmp_cx)
	or b
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	cp 80
	jp c,vpf_slot
	ld (hl),$ff		; прямой ($FE) или уже выведен — вернуть «пусто» (таблица не чистится)
	jp vpf_x_next
vpf_slot:
	ld (hl),$ff		; слот выведен — больше не выводить (пересечения прямоугольников)
	ld l,a			; адрес слота: $A000 + slot*128 (inline vec_pool_addr)
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ld sp,hl
	ld a,(vec_tmp_cx)
	add a,a
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub b
	ld e,a
	ld hl,(vec_bud_used)	; фаза кадра: считать и сброс (ISR обнулит при прерывании)
	ld a,l
	add a,20 - C8*4		; слот сброса: 96 Б при C8
	jp nc,vpf_bud_ok
	ld a,255
vpf_bud_ok:
	ld (vec_bud_used),a
	ld hl,vpf_x_next
	ld (vec_blit_ret),hl
	jp vec_blit128_vram
vpf_x_next:
	ld a,(vec_tmp_cx)
	inc a
	ld (vec_tmp_cx),a
	ld a,(vec_tmp_bx)
	dec a
	ld (vec_tmp_bx),a
	jp nz,vpf_x
vpf_next:
	ld a,(vec_tmp_rc)
	dec a
	ld (vec_tmp_rc),a
	jp nz,vpf_rect
	ld a,(vec_tmp_sy)
	inc a
	ld (vec_tmp_sy),a
	cp 10
	jp nz,vpf_yloop
	ld hl,(vec_sp_save)
	ld sp,hl		; настоящий SP (порт ещё в стековом режиме — стек не трогаем до перехода)
	ld a,(vec_bud_used)
	cp 206
	jp c,vpf_done
	halt			; halt в стековом режиме безопасен: ISR целиком работает в странице 3
vpf_done:
	ld a,(vec_kv_prev)
	di
	ld (vec_kv_shadow),a
	out (KV_PORT),a		; вернуть окно, каким его держит главный код
	ei
	xor a
	ld (ndirtyrects),a
	ld (vec_pool_on),a
	ret
    endif

; ---------------------------------------------------------------------------
; ПАНЕЛЬ (страница 3 квазидиска; в DEMO панели нет)
; drawChar: A = символ, B = X (символы), C = Y (символы)
drawChar:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	sub 32
	and 63
	ld e,a			; E = код символа 0..63
	; кэш по ячейкам (ряды 20..23): тот же символ уже в VRAM — не рисуем.
	; Оригинал перерисовывает панель в каждом кадре ожидания (waitforVBlank), для VDP это
	; дёшево, для нас — стековый блит 4x8x4 на символ.
	ld a,c
	sub 20
	cp 4
	jp nc,dc_draw
	rrca
	rrca
	rrca			; ряд*32
	add a,b
	ld l,a
	ld h,0
	push de
	ld de,vec_pc_char
	add hl,de
	pop de
	ld a,(hl)
	cp e
	jp z,dc_skip
	ld (hl),e
dc_draw:
	ld a,e
	; src = P3_FONT + A*32
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld (vec_blit_src),hl
	ld a,b
	add a,VEC_P0H
	ld d,a
	ld a,c
	rlca
	rlca
	rlca
	ld c,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	ld a,1
	ld (vec_bl_cols),a
	ld a,4
	ld (vec_bl_pops),a
	jp vec_panel_blit
dc_skip:
	pop bc
	pop de
	pop hl
	ret
    endif
; drawWeapon: A = X источника (оружие*32), B = X px, C = Y px; 24x16
drawWeapon:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	call vec_pc_inv3	; картинка ложится на ячейки символов — их кэш сбросить
	rrca
	rrca
	rrca
	rrca
	rrca
	and 3			; номер оружия
	ld l,a
	ld h,0
	ld d,h
	ld e,l
	add hl,hl		; *2
	add hl,de		; *3
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl		; *192
	ld de,P3_WEAPON
	add hl,de
	ld (vec_blit_src),hl
	ld a,8
	ld (vec_bl_pops),a
	jp vec_panel_blit3
    endif
; drawScoreOnOff: A = 0 выкл / 1 вкл, B = X px, C = Y px; 24x24
drawScoreOnOff:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	inc a			; 1 = выкл, 2 = вкл (0/$FF = неизвестно)
	ld e,a
	ld a,b
	rrca
	rrca
	rrca
	and $1f			; колонка
	ld l,a
	ld h,0
	push de
	ld de,vec_pc_onoff
	add hl,de
	pop de
	ld a,(hl)
	cp e
	jp z,dc_skip		; та же картинка уже в VRAM
	ld (hl),e
	call vec_pc_inv3	; 24x24 накрывает ячейки цифр — их кэш сбросить
	ld a,e
	dec a
	ld hl,P3_ONOFF
	or a
	jp z,dso_0
	ld hl,P3_ONOFF+288
dso_0:
	ld (vec_blit_src),hl
	ld a,12
	ld (vec_bl_pops),a
vec_panel_blit3:
	ld a,3
	ld (vec_bl_cols),a
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
vec_panel_blit:
	push bc
	ld a,(vec_bl_cols)
	ld b,a
	ld a,(vec_bl_pops)
	ld c,a
	xor a
vpn_cost:
	add a,c			; cols * pops
	dec b
	jp nz,vpn_cost
	ld c,a			; cols*pops (pop-ов на плоскость); цена ~0.69 ед. на pop x 4 плоскости -> *3/4
	rrca
	and $7f
	ld b,a			; /2
	rrca
	and $7f			; /4
	add a,b
	add a,32		; + логика куска панели (draw_*_state, Div16_8) перед блитом — EI, но время кадра
	call vec_budget
	pop bc
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_STK_P3
	out (KV_PORT),a
	ld hl,vpn_ret
	ld (vec_blit_ret),hl
	jp vec_blit_cols
vpn_ret:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	pop de
	pop hl
	ret
    endif
; vec_panel_blit_call: вызов vec_panel_blit как процедуры (сам он снимает hl/de/bc со стека и делает ret)
vec_panel_blit_call:
	push hl
	push de
	push bc
	jp vec_panel_blit
; vec_load_panel: картинка панели 256x32 -> строки 160..191
vec_load_panel:
    if DEMO
	ret
    else
	call vec_pc_reset
	push hl
	push de
	push bc
	ld a,VEC_NPL
	ld (vec_tmp_sx),a	; счётчик плоскостей
	ld hl,P3_PANEL
	ld d,VEC_P0H
vlp_plane:
	ld (vec_blit_src),hl
	ld a,32
	ld (vec_bl_cols),a
	ld a,16
	ld (vec_bl_pops),a
	ld a,1
	ld (vec_bl_planes),a	; одна плоскость за блит (512 pop, ~0.4 кадра) — влезает в бюджет DI
	ld e,Y_TOP_L-160
	push de
	call vec_panel_blit_call
	pop de
	ld hl,(vec_blit_src)
	ld bc,32*32
	add hl,bc		; следующая плоскость источника
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_tmp_sx)
	dec a
	ld (vec_tmp_sx),a
	jp nz,vlp_plane
	pop bc
	pop de
	pop hl
	ret
    endif
; vec_pc_reset: весь кэш панели = $FF («неизвестно»). Портит A, HL, B.
vec_pc_reset:
    if !DEMO
	ld hl,vec_pc_char
	ld b,128+32+64
vpr_l:
	ld (hl),$ff
	inc hl
	dec b
	jp nz,vpr_l
    endif
	ret
; vec_pc_inv3: сбросить кэш символов под картинкой 3x3 ячейки: B = X px, C = Y px.
; Бережёт все регистры, кроме A.
vec_pc_inv3:
	push bc
	push de
	push hl
	ld a,c
	rrca
	rrca
	rrca
	and $1f
	sub 20
	ld c,a			; ряд относительно 20 (вне 0..3 — пропуск)
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	ld b,a			; колонка
	ld d,3
vpi_r:
	ld a,c
	cp 4
	jp nc,vpi_next
	rrca
	rrca
	rrca			; ряд*32
	add a,b
	ld l,a
	ld h,0
	ld e,d
	ld de,vec_pc_char
	add hl,de
	ld d,3
	ld (hl),$ff
	inc hl
	ld (hl),$ff
	inc hl
	ld (hl),$ff
vpi_next:
	inc c
	dec d
	jp nz,vpi_r
	pop hl
	pop de
	pop bc
	ret
; fillArea / fillArea_slow: A = цвет, B = X px, C = Y px, D = ширина px, E = высота px
; Единственный клиент в игре — draw_meter (шкалы панели): цветная часть (цвет != $11) со строки
; 190-n высотой n и пустая ($11) со строки 169 высотой 21-n. Кэш по колонке: цветная — ключ Y,
; пустая — ключ высота. Полная пустая (21) или полная цветная (Y=169) накрывает соседа — его ключ
; сбрасываем, иначе после «энергия 0 -> прежняя» цветная часть посчиталась бы уже нарисованной.
fillArea:
fillArea_slow:
	push hl
	push de
	push bc
	push af
	ld (vec_fill_color),a
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,a
	ld l,a
	ld h,0
	push de			; E (высота) нужен ниже как ключ пустой части
	ld de,vec_pc_meter
	add hl,de		; HL -> [Y цветной], [высота пустой]
	pop de
	ld a,(vec_fill_color)
	cp $11
	jp z,fa_blank
	ld a,c			; цветная: ключ Y
	cp (hl)
	jp z,fa_skip
	ld (hl),a
	cp 169			; полная — пустой части не будет, её ключ сбросить
	jp nz,fa_go
	inc hl
	ld (hl),$ff
	jp fa_go
fa_blank:
	inc hl
	ld a,e			; пустая: ключ высота
	cp (hl)
	jp z,fa_skip
	ld (hl),a
	cp 21
	jp nz,fa_go
	dec hl
	ld (hl),$ff
fa_go:
	pop af
	pop bc
	pop de
	pop hl
	push hl
	push de
	push bc
    if C8
	cp $11			; «пустая» часть шкалы -> слот 0 (чёрный)
	jp nz,fa_c8map
	xor a
	jp fa_c8ok
fa_c8map:
	push hl
	ld hl,vec_color_map	; выровнена (сразу за fg_tile_lut)
	add a,l
	ld l,a
	ld a,(hl)
	pop hl
fa_c8ok:
    endif
	ld (vec_fill_color),a
	ld a,e
	ld (vec_fill_hgt),a
	or a
	jp z,fa_exit
	ld a,d
	or a
	jp z,fa_exit
	add a,b
	dec a
	ld (vec_fill_xr),a	; правый край
fa_col:
	; c0 = B&7; c1 = (xr в той же колонке) ? xr&7 : 7   (C = Y не трогаем!)
	ld a,b
	and 7
	ld e,a			; E = c0
	ld a,(vec_fill_xr)
	ld d,a
	xor b
	and $f8
	ld a,7
	jp nz,fa_c1
	ld a,d
	and 7
fa_c1:
	ld d,a			; D = c1
	; m1 = $FF >> c0
	ld a,$ff
	inc e
fa_m1:
	dec e
	jp z,fa_m1d
	or a
	rra
	jp fa_m1
fa_m1d:
	ld e,a			; E = m1
	; m2 = $FF << (7-c1)
	ld a,7
	sub d
	ld d,a
	ld a,$ff
	inc d
fa_m2:
	dec d
	jp z,fa_m2d
	add a,a
	jp fa_m2
fa_m2d:
	and e
	ld (vec_fill_mask),a
	; адрес: H = $80 + (B>>3), L = 223 - C
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld h,a
	ld a,Y_TOP_L
	sub c
	ld l,a
	push bc
	ld a,VEC_NPL
	ld (vec_plane_cnt),a
fa_plane:
	push hl
	ld a,(vec_fill_hgt)
	ld d,a
	; бит плоскости p (p = 4 - plane_cnt) = бит (3-p) цвета = бит (plane_cnt-1)
	ld a,(vec_plane_cnt)
	ld e,a
	ld a,(vec_fill_color)
fa_bit:
	dec e
	jp z,fa_bitd
	rrca
	jp fa_bit
fa_bitd:
	and 1
	jp z,fa_clear
fa_set:
	ld a,(vec_fill_mask)
	or (hl)
	ld (hl),a
	dec l
	dec d
	jp nz,fa_set
	jp fa_plane_next
fa_clear:
	ld a,(vec_fill_mask)
	cpl
	and (hl)
	ld (hl),a
	dec l
	dec d
	jp nz,fa_clear
fa_plane_next:
	pop hl
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,fa_plane
	pop bc
	; следующая байтовая колонка
	ld a,b
	or 7
	inc a
	jp z,fa_exit		; вышли за 255
	ld b,a
	ld a,(vec_fill_xr)
	cp b
	jp nc,fa_col
fa_exit:
	pop bc
	pop de
	pop hl
	ret
fa_skip:
	pop af
	pop bc
	pop de
	pop hl
	ret
