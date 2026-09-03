;;; overlap_hot.asm — ВЕКТОР: AnimStile_CheckSprites / MarkOverlappingSprites / check_sprite_overlap на i8080
;;; вручную (оригинал: tiles.asm AnimStile_CheckSprites, drawsprite.asm CheckSprOverlap..check_sprite_overlap).
;;; Цепочка вызывается из каждого InvalidateTiles (движение спрайта, анимация воды) и рекурсивна.
;;; Указатели IX/IY -> HL/DE, simulatedsprite — по абсолютным адресам. Гейт: tests/render/tick_oracle.py.
; AnimStile_CheckSprites: B = X супертайла, C = Y супертайла, D/E = размер в символах (8 px).
; Реентерабельна: сохраняет simulatedsprite (8 байт, как оригинал) на стеке.
AnimStile_CheckSprites:
	ld hl,(simulatedsprite)
	push hl
	ld hl,(simulatedsprite+2)
	push hl
	ld hl,(simulatedsprite+4)
	push hl
	ld hl,(simulatedsprite+6)
	push hl
	ld a,b
	rlca
	rlca
	rlca
	rlca
	and $f8
	ld (simulatedsprite+3),a	; xmin
	ld a,c
	rlca
	rlca
	rlca
	rlca
	and $f8
	ld (simulatedsprite+4),a	; ymin
	ld a,d
	ld (simulatedsprite+5),a	; символов по X
	ld a,e
	ld (simulatedsprite+6),a	; символов по Y
	call MarkOverlappingSprites
	pop hl
	ld (simulatedsprite+6),hl
	pop hl
	ld (simulatedsprite+4),hl
	pop hl
	ld (simulatedsprite+2),hl
	pop hl
	ld (simulatedsprite),hl
	ret

; AnimateSTiles — ВЕКТОР, нативно: как оригинал (tiles.asm), но проверка пересечения со спрайтами
; (AnimStile_CheckSprites: 16 проверок + инвалидация) — не на каждый тайл, а на горизонтальную СЕРИЮ
; соседних анимированных тайлов одной строки (полоса воды = одна проверка вместо семи). Карта и
; InvalidateSTiles — по-прежнему на каждый тайл. Список curscreen_animtiles идёт в порядке карты.
AnimateSTiles:
	ld a,(curscreen_numanimtiles)
	or a
	ret z
	ld (vec_an_cnt),a
	xor a
	ld (vec_an_run),a
	ld hl,curscreen_animtiles
an_loop:
	ld b,(hl)		; X супертайла
	inc hl
	ld c,(hl)		; Y
	inc hl
	push hl
	ld a,c
	rrca
	rrca
	rrca
	rrca
	and $f0
	or b
	ld e,a			; индекс Y*16+X
	ld d,0
	ld hl,CURRENT_SCREEN_MAP
	add hl,de
	ld a,(hl)
	cp 240
	jp nc,an_do		; фоновый супертайл >= 240 — анимируем его
	ld hl,CURRENT_SCREEN_MAP_FG
	add hl,de
	ld a,(hl)
	cp 240
	jp c,an_skip		; и FG < 240 — нечего анимировать
an_do:
	and $fc			; старшие 6 бит + следующий кадр анимации
	ld e,a
	ld a,(hl)
	inc a
	and 3
	or e
	ld (hl),a
	push bc
	ld de,$0101
	call InvalidateSTiles	; как UpdateSuperTile: тайл — в грязные
	pop bc
	ld a,(vec_an_run)	; серия: продолжается, если та же строка и X = x0 + длина
	or a
	jp z,an_new
	ld a,(vec_an_y)
	cp c
	jp nz,an_flush
	ld a,(vec_an_x)
	ld d,a
	ld a,(vec_an_run)
	add a,d
	cp b
	jp nz,an_flush
	ld a,(vec_an_run)
	inc a
	ld (vec_an_run),a
	jp an_skip
an_flush:
	push bc
	call an_check
	pop bc
an_new:
	ld a,b
	ld (vec_an_x),a
	ld a,c
	ld (vec_an_y),a
	ld a,1
	ld (vec_an_run),a
an_skip:
	pop hl
	ld a,(vec_an_cnt)
	dec a
	ld (vec_an_cnt),a
	jp nz,an_loop
	ld a,(vec_an_run)
	or a
	ret z
an_check:			; AnimStile_CheckSprites(B = x0, C = y, D = 2*длина символов, E = 2)
	ld a,(vec_an_x)
	ld b,a
	ld a,(vec_an_y)
	ld c,a
	ld a,(vec_an_run)
	add a,a
	ld d,a
	ld e,2
	xor a
	ld (vec_an_run),a
	jp AnimStile_CheckSprites

; RedrawInvTiles / RedrawInvTiles_FG — ВЕКТОР, нативно: обход грязных прямоугольников без exx
; (в переводе два z_exx ≈ 700 тактов на тайл). DrawTile/DrawFGTile — как в оригинале (B = x+1, C = y+1).
; Дедупликация: грязные прямоугольники старого и нового положения спрайта перекрываются (на сцене
; голема треть супертайлов рисовалась дважды за тик). Битовая карта 16x10 «уже нарисован» на проход:
; RIT_MAP — фон, RIT_MAP+20 — передний слой; обе чистит фоновый проход (FG идёт следом по тому же
; списку). Карты лежат в зазоре между кодом и переменными (сторож build_vec считает зазор до них).
RIT_MAP	equ string_area-40
RIT_MAPFG	equ RIT_MAP+20
RedrawInvTiles:
	ld hl,RIT_MAP
	ld b,40
	xor a
rit_clr:
	ld (hl),a
	inc l			; обе карты в одной странице (сторож build_vec)
	dec b
	jp nz,rit_clr
	ld hl,DrawTile
	ld a,RIT_MAP & $FF
	jp rit_common
RedrawInvTiles_FG:
	ld hl,DrawFGTile
	ld a,RIT_MAPFG & $FF
rit_common:
	ld (rit_call+1),hl	; самомодификация: какой рисовальщик звать
	ld (rit_mapp+1),a	; и какая карта
	ld a,(ndirtyrects)
	or a
	ret z
	ld (rit_cnt),a
	ld hl,tiles_dirty
rit_rect:
	ld a,(hl)		; Xmin
	inc hl
	ld (rit_x0),a
	ld a,(hl)		; Ymin
	inc hl
	ld (rit_y),a
	ld a,(hl)		; Xcount
	inc hl
	ld (rit_nx),a
	ld a,(hl)		; Ycount
	inc hl
	ld (rit_ny),a
	ld (rit_ptr),hl
rit_yl:
	ld a,(rit_nx)
	ld (rit_cx),a
	ld a,(rit_x0)
	ld b,a
rit_xl:
	ld a,(rit_y)
	ld c,a
	; бит (x,y) карты: байт RIT_MAP + y*2 + (x>>3), маска 1<<(x&7)
	add a,a
	ld l,a
	ld a,b
	rrca
	rrca
	rrca
	and 1
	add a,l
rit_mapp:
	add a,0			; самомод: младший байт карты
	ld l,a
	ld h,RIT_MAP >> 8
	ld a,b
	and 7
	inc a
	ld e,a
	ld a,$80
rit_bit:
	rlca
	dec e
	jp nz,rit_bit
	ld e,a
	and (hl)
	jp nz,rit_skip		; уже нарисован в этом проходе
	ld a,e
	or (hl)
	ld (hl),a
	push bc			; B = x, C = y (оригинал: push bc; exx; pop bc; inc b; inc c; call; exx)
	inc b
	inc c
rit_call:
	call 0
	pop bc
rit_skip:
	ld a,(rit_cx)
	dec a
	ld (rit_cx),a
	jp z,rit_ynext
	inc b
	jp rit_xl
rit_ynext:
	ld a,(rit_y)
	inc a
	ld (rit_y),a
	ld a,(rit_ny)
	dec a
	ld (rit_ny),a
	jp nz,rit_yl
	ld hl,(rit_ptr)
	ld a,(rit_cnt)
	dec a
	ld (rit_cnt),a
	jp nz,rit_rect
	ret

;;;SPLIT;;;
;;; overlap_hot.asm, часть drawsprite — MarkOverlappingSprites / check_sprite_overlap
; MarkOverlappingSprites: все спрайты, пересекающиеся с simulatedsprite и ещё не помеченные,
; помечаются на перерисовку, их тайлы инвалидируются (InvalidateTiles -> рекурсия в AnimStile_CheckSprites).
MarkOverlappingSprites:
	ld de,SPDATA
	ld c,MAX_SPRITES
mos_loop:
	ld a,(de)			; спрайт включён? (адрес != 0)
	inc de
	ld l,a
	ld a,(de)
	dec de
	or l
	jp z,mos_next
	ld hl,7
	add hl,de
	ld a,(hl)			; уже помечен на перерисовку — пропуск
	or a
	jp nz,mos_next
	push hl				; &redraw
	ld hl,simulatedsprite
	call vec_spr_overlap		; CY=1: не пересекаются
	pop hl
	jp c,mos_next
	ld (hl),1			; пометить
	push de
	push bc
	ld hl,3
	add hl,de
	ld a,(hl)			; X px -> символ
	rra
	rra
	rra
	and $1f
	ld b,a
	inc hl
	ld a,(hl)			; Y px -> символ
	rra
	rra
	rra
	and $1f
	ld c,a
	inc hl
	ld d,(hl)			; символов по X
	inc hl
	ld e,(hl)			; символов по Y
	call InvalidateTiles
	pop bc
	pop de
mos_next:
	ld hl,8
	add hl,de
	ex de,hl
	dec c
	jp nz,mos_loop
	ret
; vec_spr_overlap: HL = спрайт 1, DE = спрайт 2 (+3 X, +4 Y, +5 NX, +6 NY в символах по 8 px).
; CY=1 — не пересекаются, CY=0 — пересекаются (как check_sprite_overlap оригинала). Портит только A.
vec_spr_overlap:
	push hl
	push de
	push bc
	inc hl
	inc hl
	inc hl				; HL -> s1.x
	ld b,(hl)
	inc de
	inc de
	inc de
	inc de
	inc de				; DE -> s2.nx
	ld a,(de)
	add a,a
	add a,a
	add a,a
	ld c,a
	dec de
	dec de				; DE -> s2.x
	ld a,(de)
	add a,c
	dec a				; правый край s2
	cp b				; < левого края s1 ?
	jp c,vso_no
	ld a,(de)
	ld b,a				; левый край s2
	inc hl
	inc hl				; HL -> s1.nx
	ld a,(hl)
	add a,a
	add a,a
	add a,a
	ld c,a
	dec hl
	dec hl				; HL -> s1.x
	ld a,(hl)
	add a,c
	dec a				; правый край s1
	cp b
	jp c,vso_no
	inc hl				; HL -> s1.y
	ld b,(hl)
	inc de
	inc de
	inc de				; DE -> s2.ny
	ld a,(de)
	add a,a
	add a,a
	add a,a
	ld c,a
	dec de
	dec de				; DE -> s2.y
	ld a,(de)
	add a,c
	dec a				; низ s2
	cp b				; < верха s1 ?
	jp c,vso_no
	ld a,(de)
	ld b,a				; верх s2
	inc hl
	inc hl				; HL -> s1.ny
	ld a,(hl)
	add a,a
	add a,a
	add a,a
	ld c,a
	dec hl
	dec hl				; HL -> s1.y
	ld a,(hl)
	add a,c
	dec a				; низ s1
	cp b				; CY = результат
vso_no:
	pop bc
	pop de
	pop hl
	ret
; check_sprite_overlap: вход как в оригинале — IX = спрайт 1, IY = спрайт 2 (ячейки транслятора z_ix/z_iy);
; выход CY. Бережёт HL/DE/BC (оригинал портил A, B).
check_sprite_overlap:
	push hl
	push de
	ld hl,(z_iy)
	ex de,hl
	ld hl,(z_ix)
	call vec_spr_overlap
	pop de
	pop hl
	ret
