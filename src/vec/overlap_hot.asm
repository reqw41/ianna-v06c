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

; RedrawInvTiles / RedrawInvTiles_FG — ВЕКТОР, нативно: обход НЕ прямоугольников, а КАРТЫ грязных
; стайлов. Карта — та же таблица слотов пула (vec_slot_tab: $FF чист, $FE грязный без слота,
; 0..79 номер слота), её строит vec_pool_begin из тех же прямоугольников и в том же порядке.
; Прямоугольники старого и нового положения спрайта перекрываются (на сцене голема треть стайлов
; попадала в обход дважды), и раньше дедупликацию держали две битовые карты 16x10: на каждый визит
; тайла уходило ~200 тактов на пересчёт байта и маски, а сами визиты были втрое чаще самих тайлов.
; Теперь дедупликация достаётся даром — стайл в карте ровно один. Строки без грязного помечены
; нулём в vec_slot_tab[160+y] (ставит vpb_y, снимает сброс пула) и не перебираются, а в грязной
; строке перебирается только полоса [xmin..xmax] — её границы кладёт туда же vpb_y.
RedrawInvTiles:
	ld hl,dt_rit		; вход с готовыми координатами (vec_vdp.asm)
	jp rit_common
RedrawInvTiles_FG:
	ld hl,dft_rit
rit_common:
	ld (rit_call+1),hl	; самомодификация: какой рисовальщик звать
	ld a,(ndirtyrects)
	or a
	ret z
	xor a
rit_row:
	ld (rit_y),a
	add a,160
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)		; xmin+1 полосы грязного в строке (0 = строка чиста), см. vpb_y
	ld c,a
	or a
	ld a,(rit_y)		; ld a,nn флагов не трогает
	jp z,rit_rownext
	rlca
	rlca
	rlca
	rlca
	add a,c
	dec a			; y*16 + xmin
	ld b,l			; L = 160+y
	ld l,a			; H уже на таблице слотов
	ld a,b
	add a,16
	ld e,a
	ld d,vec_slot_tab/256
	ld a,(de)		; xmax+1
	sub c
	inc a
	ld b,a			; колонок в полосе
rit_x:
	ld a,(hl)
	inc a
	jp z,rit_xnext		; $FF — стайл не грязный
	ld (rit_ptr),hl
	ld a,b
	ld (rit_cx),a
	ld a,l
	and $f0
	ld c,a			; C = Y px (стайл 16x16: y = (idx>>4)*16 = idx & $F0)
	ld a,l
	rlca
	rlca
	rlca
	rlca
	and $f0
	ld b,a			; B = X px
	ld h,0			; HL = &CURRENT_SCREEN_MAP[idx] (L = idx уже стоит)
	ld de,CURRENT_SCREEN_MAP
	add hl,de
rit_call:
	call 0
	ld hl,(rit_ptr)
	ld a,(rit_cx)
	ld b,a
rit_xnext:
	inc l
	dec b
	jp nz,rit_x
	ld a,(rit_y)
rit_rownext:
	inc a
	cp 10
	jp nz,rit_row
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
