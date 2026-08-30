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
