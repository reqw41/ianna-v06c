; vec_vdp.asm — платформенный слой Вектор-06Ц вместо vdp.asm MSX2.
; Интерфейс тот же, что у VDP-процедур оригинала (drawTile, drawFGTile,
; drawSprite, setROM2, setDisplayPage...), реализация — прямой вывод в 4
; плоскости pop-блитом. Источник данных: квазидиск (DEMO=0) или ROM (DEMO=1).
;
; Экран: MSX y=0..191 -> строка Вектора y+32 -> L = 255-(y+32) = 223-y.
;        MSX x=0..255 -> колонка H = база_плоскости + (x>>3). Бит7 = левый пиксель.
; Плоскости: $80,$A0,$C0,$E0 (старший байт), палитра idx = p0<<3|p1<<2|p2<<1|p3.
;
; Квазидиск (порт $10): бит4 = стековый режим, биты 2-3 = страница стека;
; в стековом режиме POP читает страницу квазидиска, обычные записи идут в VRAM.
; На время стековых блитов прерывания запрещены (ISR пушит в стек!).

KV_PORT		equ $10
KV_STACK_P0	equ $10		; стек -> страница 0
KV_STACK_P1	equ $14		; стек -> страница 1
KV_WIN_LEVEL	equ $61		; окна $8000-$9FFF (б6) + $A000-$DFFF (б5), страница 1 (карта уровня)
KV_OFF		equ $00

Y_TOP_L		equ 223		; L для MSX y=0

; ---------------------------------------------------------------------------
; setROM2: A = «ROM-страница» MSX. Семантика на Векторе:
;   1        -> закрыть все окна (обычная память)
;   2..21    -> запомнить банк спрайтов (используется drawSprite)
;   22..39   -> страница уровня/тайлов: LEVEL -> открыть окно карты уровня
setROM2:
setROM2_DI:
	ld (ROMBank1),a
	cp 1
	jp z,setrom_close
	cp 22
	jp c,setrom_sprite
	and 1
	ret nz			; тайлы: ничего не делаем
    if DEMO
	ret			; карта уровня в ROM
    else
	ld a,KV_WIN_LEVEL
	out (KV_PORT),a
	ret
    endif
setrom_close:
    if !DEMO
	xor a
	out (KV_PORT),a
    endif
	ret
setrom_sprite:
	ld (vec_sprite_bank),a
	ret

; ---------------------------------------------------------------------------
; Заглушки двойной буферизации: на Векторе рисуем сразу в экран.
; TransferDirtyTiles остаётся оригинальный (tiles.asm): CopyTile — заглушка,
; а обнуление ndirtyrects в его хвосте нам и нужно.
setDisplayPage:
CopyTile:
copyPage:
VDPcmd:
VDPcmd_DI:
waitVDP:
fillArea:
VDP_SetPalette:
initVDPBuffers:
unpackVRAM:
fadeMSX2:
fadeinMSX2:
	ret

; cls: очистить все 4 плоскости
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
	ret

; ---------------------------------------------------------------------------
; drawTile: A = номер тайла, B = X (px, кратно 16), C = Y (px, кратно 16)
; Тайл фона 128 Б: for p in 0..3: for col in 0..1: 16 строк сверху вниз.
; ВНУТРИ стекового блита нельзя call/ret (стек подменён).
drawTile:
	push hl
	push de
	push bc
    if DEMO
	; адрес = DEMO_TILES_BASE + lut[A]*128
	ld l,a
	ld h,demo_tile_lut/256
	ld a,(hl)
	ld l,0
	rrca			; CY = бит0, A>>1 в младших 7 битах
	jp nc,dt_a0
	ld l,$80
dt_a0:
	and $7f
	ld h,a
	ld de,DEMO_TILES_BASE
	add hl,de
    else
	; адрес = $8000 + A*128 (страница 0)
	ld d,a
	rrca
	and $7f
	add a,$80
	ld h,a
	ld a,d
	and 1
	rrca
	ld l,a
    endif
	ld (vec_tile_src),hl
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,$80
	ld d,a			; D = H колонки 0 плоскости 0
	ld a,Y_TOP_L
	sub c
	ld e,a			; E = L верхней строки
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_tile_src)
	ld sp,hl
    if !DEMO
	ld a,KV_STACK_P0
	out (KV_PORT),a
    endif
	ld a,4
	ld (vec_plane_cnt),a
dt_plane:
	ld h,d
	ld l,e
	ld a,2
	ld (vec_col_cnt),a
dt_col:
	; 8 pop = 16 строк
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
	jp nz,dt_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dt_plane
    if !DEMO
	ld a,KV_OFF
	out (KV_PORT),a
    endif
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	pop de
	pop hl
	ret

; ---------------------------------------------------------------------------
; drawFGTile: A = номер тайла (≠0), B = X, C = Y. Передний тайл с маской:
; 256 Б по адресу FG_TILES_BASE + (lut[A]-1)*256; lut[A]=0 -> тайла нет.
;   for p: for col: 16 строк сверху вниз: [data, mask]
drawFGTile:
	push hl
	push de
	push bc
	ld l,a
	ld h,fg_tile_lut/256
	ld a,(hl)
	or a
	jp z,dft_exit
	dec a
	add a,FG_TILES_BASE/256
	ld h,a
	ld l,0
	ld (vec_tile_src),hl
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,$80
	ld d,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_tile_src)
	ld sp,hl
    if !DEMO
	ld a,KV_STACK_P1
	out (KV_PORT),a
    endif
	ld a,4
	ld (vec_plane_cnt),a
dft_plane:
	ld h,d
	ld l,e
	ld a,2
	ld (vec_col_cnt),a
dft_col:
	ld a,16
	ld (vec_row_cnt),a
dft_row:
	pop bc			; C=data, B=mask
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dft_row
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
    if !DEMO
	ld a,KV_OFF
	out (KV_PORT),a
    endif
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
dft_exit:
	pop bc
	pop de
	pop hl
	ret

; ---------------------------------------------------------------------------
; drawSprite: как в оригинале — A = направление (0: прямо, 1: зеркало),
; B = X (px, кратно 8), C = Y (px), HL = «адрес спрайта» MSX ($8000 + n*384).
; Высота: (vdpCmdSprite+VDP_NY) строк (клиппинг по низу), выставляется
; DrawSpriteList перед вызовом.
; Кадр 384 Б: for col 0..2: for row 31..0: [p0,p1,p2,p3] (снизу вверх).
; Маска = ~(p0|p1|p2|p3) считается на лету. Вывод снизу вверх (INR L);
; клиппинг: пропустить первые (32-NY) строк каждой колонки (SP += skip*4).
; Источник: DEMO -> DEMO_FRAMES_BASE + (HL-$8000); квазидиск -> страница по банку, HL-$8000.
drawSprite:
	push af
	ld de,-$8000
	add hl,de		; смещение кадра n*384
    if DEMO
	ld de,DEMO_FRAMES_BASE
	add hl,de
    else
	ld a,(vec_sprite_bank)
	sub 2
	and 3
	rlca
	rlca
	or KV_STACK_P0
	ld (vec_spr_port),a
    endif
	; NY, skip*4
	ld a,(vdpCmdSprite+VDP_NY)
	ld (vec_spr_ny),a
	ld e,a
	ld a,32
	sub e
	add a,a
	add a,a
	ld (vec_spr_skip),a
	ld e,a
	ld d,0
	add hl,de		; старт SP = кадр + skip*4
	ld (vec_spr_src),hl
	; L нижней выводимой строки = 223 - (C + NY - 1)
	ld a,(vec_spr_ny)
	add a,c
	dec a
	ld e,a
	ld a,Y_TOP_L
	sub e
	ld (vec_spr_lbot),a
	; H колонки 0 плоскости 0
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,$80
	ld (vec_spr_hcol),a
	pop af
	or a
	jp nz,drawSprite_mirror
; ---- прямой ----
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
	out (KV_PORT),a
    endif
ds_col:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
ds_row:
	pop de			; E=p0, D=p1
	pop bc			; C=p2, B=p3
	ld a,e
	or d
	or c
	or b
	cpl
	ld (vec_spr_mask),a
	and (hl)		; плоскость 0
	or e
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 1
	or d
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 2
	or c
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 3
	or b
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
	inc l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,ds_row
	; следующая колонка: SP += skip*4, H+1
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
	jp ds_done
; ---- зеркальный ----
; Колонки данных 0,1,2 -> экранные колонки x+2, x+1, x+0; байты через rev256.
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
	out (KV_PORT),a
    endif
dsm_col:
	ld a,(vec_spr_hcol)
	ld d,a
	ld a,(vec_spr_lbot)
	ld e,a			; DE = экран
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
dsm_row:
	ld h,rev256/256
	pop bc			; C=p0, B=p1
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ld a,c
	ld (vec_spr_p01),a
	ld a,b
	ld (vec_spr_p01+1),a
	pop bc			; C=p2, B=p3
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ld hl,(vec_spr_p01)	; L=p0, H=p1
	ld a,l
	or h
	or c
	or b
	cpl
	ld (vec_spr_mask),a
	ex de,hl		; HL = экран, E=p0, D=p1
	and (hl)		; плоскость 0
	or e
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 1
	or d
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 2
	or c
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_spr_mask)
	and (hl)		; плоскость 3
	or b
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
	inc l
	ex de,hl		; DE = экран (следующая строка)
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dsm_row
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
ds_done:
    if !DEMO
	ld a,KV_OFF
	out (KV_PORT),a
    endif
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ret
