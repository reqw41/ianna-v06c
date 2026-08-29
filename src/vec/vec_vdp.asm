; vec_vdp.asm — платформенный слой Вектор-06Ц вместо vdp.asm MSX2.
; Интерфейс тот же, что у VDP-процедур оригинала (drawTile, drawFGTile,
; drawSprite, setROM2, setDisplayPage, TransferDirtyTiles...), реализация —
; прямой вывод в 4 плоскости с pop-блитом из квазидиска.
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
;   прочее   -> ничего
setROM2:
setROM2_DI:
	ld (ROMBank1),a
	cp 1
	jp z,setrom_close
	cp 22
	jp c,setrom_sprite
	; уровень или тайлы: чётные (22,24..) = карта, нечётные = тайлы (в VRAM не нужны)
	and 1
	ret nz			; тайлы: ничего не делаем
	ld a,KV_WIN_LEVEL
	out (KV_PORT),a
	ret
setrom_close:
	xor a
	out (KV_PORT),a
	ret
setrom_sprite:
	ld (vec_sprite_bank),a
	ret

; ---------------------------------------------------------------------------
; Заглушки двойной буферизации: на Векторе рисуем сразу в экран.
setDisplayPage:
	ret
; TransferDirtyTiles остаётся оригинальный (tiles.asm): CopyTile — заглушка,
; а обнуление ndirtyrects в его хвосте нам и нужно.
CopyTile:
	ret
copyPage:
	ret
VDPcmd:
VDPcmd_DI:
	ret
waitVDP:
	ret
fillArea:
	ret
VDP_SetPalette:
	ret
initVDPBuffers:
	ret
unpackVRAM:
	ret
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
; Тайл фона: 128 Б в странице 0 квазидиска по адресу $8000 + A*128:
;   for p in 0..3: for col in 0..1: 16 строк сверху вниз (DCR L).
drawTile:
	push hl
	push de
	push bc
	; SP-адрес тайла: $8000 + A*128 -> старший = $80 + (A>>1), младший = (A&1)*128
	ld d,a
	rrca
	and $7f
	add a,$80
	ld h,a
	ld a,d
	and 1
	rrca			; 1 -> $80
	ld l,a
	ld (vec_tile_src),hl
	; адрес экрана: D = H колонки 0 плоскости 0, E = L верхней строки
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
	; --- стековый блит (DI: ISR пушит в стек) ---
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_tile_src)
	ld sp,hl
	ld a,KV_STACK_P0
	out (KV_PORT),a
	ld a,4
	ld (vec_plane_cnt),a
dt_plane:
	ld h,d
	ld l,e
	; колонка 0: 8 pop = 16 строк (C = верхняя из пары)
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
	; колонка 1
	inc h
	ld l,e
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
	; следующая плоскость: H = D + $20
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dt_plane
	; --- конец стекового блита ---
	ld a,KV_OFF
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	pop de
	pop hl
	ret

; ---------------------------------------------------------------------------
; drawFGTile: A = номер тайла (≠0), B = X, C = Y. Передний тайл с маской:
; 256 Б в странице 1 квазидиска по адресу fg_tile_lut[A] (0 = тайла нет в наборе):
;   for p: for col: 16 строк сверху вниз: [data, mask]
drawFGTile:
	push hl
	push de
	push bc
	ld l,a
	ld h,0
	add hl,hl
	ld de,fg_tile_lut
	add hl,de
	ld e,(hl)
	inc hl
	ld d,(hl)
	ld a,d
	or e
	jp z,dft_exit		; тайла нет в наборе уровня
	ex de,hl
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
	ld a,KV_STACK_P1
	out (KV_PORT),a
	ld a,4
	ld (vec_plane_cnt),a
dft_plane:
	ld h,d
	ld l,e
	; колонка 0, 16 строк: pop bc -> C=data, B=mask
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
	; колонка 1
	inc h
	ld l,e
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
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dft_plane
	ld a,KV_OFF
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
; drawSprite: как в оригинале — A = направление (0: прямо, 1: зеркало),
; B = X (px, кратно 8), C = Y (px), HL = «адрес спрайта» MSX ($8000 + n*384).
; Высота: (vdpCmdSprite+VDP_NY) строк (клиппинг по низу), выставляется
; DrawSpriteList перед вызовом.
; Данные: страница квазидиска по банку (vec_sprite_bank: 2 -> стр.0, 3 -> стр.1),
; адрес = (HL*2) & $FFFF = n*768: for p: for col 0..2: rows 31..0: [data,mask].
; Вывод снизу вверх (INR L); клиппинг = пропустить первые (32-NY) строк
; каждой колонки-плоскости: SP += skip*2, вход в развёрнутый блок со смещением.
drawSprite:
	push af
	; физический адрес данных = HL*2
	add hl,hl
	ld (vec_spr_src),hl
	; порт квазидиска по банку
	ld a,(vec_sprite_bank)
	sub 2
	and 3
	rlca
	rlca
	or KV_STACK_P0
	ld (vec_spr_port),a
	; строки: NY, skip = 32-NY
	ld a,(vdpCmdSprite+VDP_NY)
	ld e,a			; E = NY
	ld a,32
	sub e
	ld (vec_spr_skip),a	; skip
	; L нижней выводимой строки = 223 - (C + NY - 1)
	ld a,c
	add a,e
	dec a
	ld d,a
	ld a,Y_TOP_L
	sub d
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
	; вход в развёрнутый блок: ds_blk + skip*6
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	ld d,h
	ld e,l
	add hl,hl		; *2
	add hl,de		; *3
	add hl,hl		; *6
	ld de,ds_blk
	add hl,de
	ld (ds_jmp+1),hl
	; SP стартовый = src + skip*2
	ld a,(vec_spr_skip)
	add a,a
	ld e,a
	ld d,0
	ld hl,(vec_spr_src)
	add hl,de
	ld (vec_spr_src),hl
	ld a,12
	ld (vec_plane_cnt),a	; 12 колонко-плоскостей
	ld a,3
	ld (vec_col_cnt),a
	ld a,(vec_spr_hcol)
	ld d,a
	ld a,(vec_spr_lbot)
	ld e,a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	out (KV_PORT),a
ds_cp:
	ld h,d
	ld l,e
ds_jmp:
	jp 0			; -> ds_blk + skip*6 (самомодификация)
ds_blk:
	; 32 блока по 6 байт: pop de / ld a,(hl) / and d / or e / ld (hl),a / inc l
	; (DE здесь — данные! D/E экрана восстанавливаются после блока из ячеек)
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	pop de
	ld a,(hl)
	and d
	or e
	ld (hl),a
	inc l
	; конец колонко-плоскости: следующая колонка (H+1) или плоскость (H+$1E)
	ld a,(vec_spr_hcol)
	ld d,a
	ld a,(vec_spr_lbot)
	ld e,a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp z,ds_next_plane
	inc d
	ld a,d
	ld (vec_spr_hcol),a
	jp ds_skipsp
ds_next_plane:
	ld a,3
	ld (vec_col_cnt),a
	ld a,d
	add a,$1e		; -2 колонки + $20 плоскость
	ld d,a
	ld (vec_spr_hcol),a
ds_skipsp:
	; SP += skip*2 (пропуск нижних строк следующей колонко-плоскости)
	ld a,(vec_spr_skip)
	add a,a
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,ds_cp
	jp ds_done
; ---- зеркальный ----
; Колонки данных 0,1,2 выводятся в экранные колонки x+2, x+1, x+0;
; байты данных и маски разворачиваются таблицей rev256 (страница, H=hi(rev256)).
; Регистры в блоке: DE = экранный адрес, HL = таблица (H=hi rev256), BC = data/mask.
drawSprite_mirror:
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	ld d,h
	ld e,l
	add hl,hl		; *2
	add hl,de		; *3
	add hl,hl		; *6
	add hl,hl		; *12
	ld de,dsm_blk
	add hl,de
	ld (dsm_jmp+1),hl
	ld a,(vec_spr_skip)
	add a,a
	ld e,a
	ld d,0
	ld hl,(vec_spr_src)
	add hl,de
	ld (vec_spr_src),hl
	ld a,12
	ld (vec_plane_cnt),a
	ld a,3
	ld (vec_col_cnt),a
	ld a,(vec_spr_hcol)
	add a,2			; зеркало: первая колонка данных -> правая колонка экрана
	ld (vec_spr_hcol),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	out (KV_PORT),a
dsm_cp:
	ld a,(vec_spr_hcol)
	ld d,a
	ld a,(vec_spr_lbot)
	ld e,a
	ld h,rev256/256
dsm_jmp:
	jp 0
dsm_blk:
	; 32 блока по 12 байт:
	; pop bc / ld l,c / ld c,(hl) / ld l,b / ld b,(hl) / ex de,hl / ld a,(hl) / and b / or c / ld (hl),a / inc l / ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	pop bc
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ex de,hl
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc l
	ex de,hl
	; конец колонко-плоскости: экранная колонка влево (H-1) или плоскость (+$20+2)
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp z,dsm_next_plane
	ld a,(vec_spr_hcol)
	dec a
	ld (vec_spr_hcol),a
	jp dsm_skipsp
dsm_next_plane:
	ld a,3
	ld (vec_col_cnt),a
	ld a,(vec_spr_hcol)
	add a,$22
	ld (vec_spr_hcol),a
dsm_skipsp:
	ld a,(vec_spr_skip)
	add a,a
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dsm_cp
ds_done:
	ld a,KV_OFF
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ret
