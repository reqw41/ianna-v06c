;;; vec_bootload.asm — стартовая загрузка набора уровня 1 БЕЗ буферов в экране: на экране всё время
;;; стоит полноцветная заставка-обложка (4 плоскости). Сжатое читается ПОТОКОМ из буфера сектора
;;; (FDD_BUF) прямо в распаковщик aPLib, распакованное ложится в пул (стр.3 $A000-$BFFF, в наборе он
;;; нулевой и до игры не нужен) и оттуда стековым режимом — на место. Примитивы ВГ93 — старого
;;; загрузчика ($7E00: vfl_restore, vfl_seek, vfl_fill). Смена уровней в игре идёт прежним путём.
;;; Лежит в string_area+1024 и дальше (за буфером сектора), ставит vec_boot_init. Таблица длин и рецепт
;;; банков (192 Б) — на месте главного цикла старого загрузчика ($7E00): при старте исполняются только его
;;; примитивы (vfl_fill и дальше), а смена уровня возвращает загрузчик из копии в наборе (FDDCOPY).

BL_POOL		equ $A000	; стр.3, окно $23
BL_TAB		equ vec_fdd_load
BL_WIN		equ $23

; --- байт потока: из буфера сектора, по исчерпании — следующий сектор (vfl_fill) ---
bl_gb:
	push hl
	ld hl,(vec_fdd_ptr)
	ld a,h
	cp 0+((FDD_BUF+1024)>>8)
	jp nz,bl_gb1
	push bc
	push de
	call vfl_fill		; HL не бережёт; vec_fdd_ptr = FDD_BUF
	pop de
	pop bc
	ld hl,FDD_BUF
bl_gb1:
	ld a,(hl)
	inc hl
	ld (vec_fdd_ptr),hl
	pop hl
	ret

; --- распаковщик aPLib (формат apultra), потоковый: DE = приёмник; HL, BC портит ---
ap_bit:				; CY = очередной бит
	ld a,(ap_bits)
	add a,a
	jp nz,ap_bit1
	call bl_gb
	scf
	rla
ap_bit1:
	ld (ap_bits),a
	ret
ap_gamma:			; BC = гамма-код
	ld bc,1
ap_g1:
	call ap_bit
	ld a,c
	rla
	ld c,a
	ld a,b
	rla
	ld b,a
	call ap_bit
	jp c,ap_g1
	ret
ap_depack:
	ld a,$80
	ld (ap_bits),a
ap_lit:
	call bl_gb
ap_put:				; байт A -> приёмник, LWM = 0
	ld (de),a
	inc de
	xor a
	ld (ap_lwm),a
ap_next:
	call ap_bit
	jp nc,ap_lit
	call ap_bit
	jp nc,ap_pair
	call ap_bit
	jp nc,ap_short
	ld c,$10		; 111: 4-битное смещение, байт или ноль
ap_4:
	call ap_bit
	ld a,c
	rla
	ld c,a
	jp nc,ap_4
	or a
	jp z,ap_put
	ld a,e
	sub c
	ld l,a
	ld a,d
	sbc a,0
	ld h,a
	ld a,(hl)
	jp ap_put
ap_short:			; 110: байт = смещение*2 + (длина-2); 0 — конец
	call bl_gb
	or a
	rra
	ld l,a
	ld h,0
	ld a,0
	adc a,2
	ld c,a
	ld b,h
	ld a,l
	or a
	ret z
	ld (ap_r0),hl
	jp ap_copy1
ap_pair:			; 10: гамма-смещение
	call ap_gamma
	ld a,(ap_lwm)
	or a
	jp nz,ap_p2
	ld a,c
	cp 2
	jp nz,ap_p3
	call ap_gamma		; старое смещение R0
	ld hl,(ap_r0)
	jp ap_copy1
ap_p3:
	dec c
ap_p2:
	dec c
	dec c
	ld h,c
	call bl_gb
	ld l,a
	ld (ap_r0),hl
	push hl
	call ap_gamma
	pop hl
	ld a,h
	cp $7D
	jp c,ap_a1
	inc bc
ap_a1:
	cp 5
	jp c,ap_a2
	inc bc
ap_a2:
	or a
	jp nz,ap_copy1
	ld a,l
	cp $80
	jp nc,ap_copy1
	inc bc
	inc bc
ap_copy1:			; HL = смещение, BC = длина
	ld a,1
	ld (ap_lwm),a
	ld a,e
	sub l
	ld l,a
	ld a,d
	sbc a,h
	ld h,a
ap_cl:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	ld a,b
	or c
	jp nz,ap_cl
	jp ap_next

; --- кусок: поток -> пул, затем пул -> квазидиск (A = страница, HL = конец приёмника, BC = длина) ---
bl_chunk:
	ld (bl_page),a
	ld (bl_dst),hl
	push bc
	di
	ld a,BL_WIN
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	ld de,BL_POOL
	call ap_depack
	pop bc
	ld hl,BL_POOL-1
	add hl,bc		; последний байт в пуле
	ld (bl_src),hl
	ld a,b			; BC = пары
	or a
	rra
	ld b,a
	ld a,c
	rra
	ld c,a
	ld a,(bl_page)
	rlca
	rlca
	or BL_WIN|$10		; окно стр.3 (пул) + стек на страницу приёмника
	di
	ld hl,0
	add hl,sp
	ld (vec_fdd_sp),hl
	ld hl,(bl_dst)
	ld sp,hl
	ld hl,(bl_src)
	out (KV_PORT),a
bl_push:
	ld d,(hl)
	dec hl
	ld e,(hl)
	dec hl
	push de
	dec bc
	ld a,b
	or c
	jp nz,bl_push
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ld hl,(vec_fdd_sp)
	ld sp,hl
	ei
	ret

; --- набор уровня (как vec_fdd_load + fdd_banks), зовётся из vec_start вместо vec_fdd_load ---
bl_load:
	ld a,(vfl_dirtab)	; уровень 1
	ld b,a
	call bl_seek1
	ld hl,BL_TAB		; длины блоков (64) и рецепт банков (128)
	ld c,192
bl_h:
	call bl_gb
	ld (hl),a
	inc hl
	dec c
	jp nz,bl_h
	xor a
	ld (vfl_blk),a
bl_blk:
	ld a,(vfl_blk)
	add a,a
	ld l,a
	ld h,0
	ld de,BL_TAB
	add hl,de
	ld a,(hl)
	inc hl
	or (hl)
	jp z,bl_bnext		; нулевой блок — в квазидиске и так нули
	ld a,(vfl_blk)
	ld c,a
	and 7
	rrca
	rrca
	rrca			; (блок%8) * 32 — старший байт начала
	add a,$20		; конец (у последнего блока страницы $0000 — push идёт с $FFFF)
	ld h,a
	ld l,0
	ld a,c
	rrca
	rrca
	rrca
	and 3			; страница
	ld bc,8192
	call bl_chunk
bl_bnext:
	ld a,(vfl_blk)
	inc a
	ld (vfl_blk),a
	cp 32
	jp nz,bl_blk
	; банки спрайтов: рецепт [M][дорожка, сектор, порт, адрес] x M; потом страница героя под оружие
	ld hl,BL_TAB+64
	ld a,(hl)
	inc hl
bl_bank:
	or a
	jp z,bl_wpn
	push af
	call bl_onebank
	pop af
	dec a
	jp bl_bank
bl_wpn:
	ld a,(player_current_weapon)	; кадры 14..36 героя под оружие (как fb_wpn): кусок w0..w3
	and 3
	add a,a
	ld e,a
	ld d,0
	ld hl,vec_wpntab
	add hl,de
	ld a,(hl)
	or a
	jp z,bl_mark
	ld (bl_rec),a
	inc hl
	ld a,(hl)
	ld (bl_rec+1),a
	ld hl,BL_TAB+64+120	; шаблон: порт и адрес кадра 14 в банке 2
	ld a,(hl)
	ld (bl_rec+2),a
	inc hl
	ld a,(hl)
	ld (bl_rec+3),a
	inc hl
	ld a,(hl)
	ld (bl_rec+4),a
	ld hl,bl_rec
	call bl_onebank
bl_mark:
    if VI53
	ld hl,$D3AF		; xor a; out ($0B),a; out ($0B),a — фаза кадра снова идёт (догонялка меню)
	ld (isr_c0),hl
	ld hl,$D30B
	ld (isr_c0+2),hl
	ld a,$0B
	ld (isr_c0+4),a
    endif
	ld a,KV_WIN_MUSIC	; маркер: набор загружен
	out (KV_PORT),a
	ld hl,'I'+256*'A'
	ld (FDD_MARK),hl
	xor a
	out (KV_PORT),a
	ret

; HL -> запись [дорожка][сектор][порт][адрес]; возвращает HL за записью
bl_onebank:
	ld b,(hl)
	inc hl
	ld a,(hl)
	inc hl
	ld c,(hl)		; порт: страница в битах 2-3
	inc hl
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	push hl
	ex de,hl
	ld (bl_dst),hl
	ld (vec_fdd_sec),a
	ld a,c
	rrca
	rrca
	and 3
	ld (bl_bpg),a
	call bl_seek
	call bl_gb		; N кусков
	cp 7
	jp nc,bl_ob_x		; заголовок с мусором — не грузим (как fdd_banks)
	ld (bl_np),a
	ld hl,bl_tab
	add a,a
	add a,a
	ld c,a
bl_ob_h:
	call bl_gb
	ld (hl),a
	inc hl
	dec c
	jp nz,bl_ob_h
	ld hl,bl_tab
bl_ob_p:
	inc hl
	inc hl
	ld c,(hl)		; распакованная длина
	inc hl
	ld b,(hl)
	inc hl
	push hl
	ld hl,(bl_dst)
	add hl,bc
	ld (bl_dst),hl		; конец куска — он же начало следующего
	ld a,(bl_bpg)
	push hl
	call bl_chunk
	pop hl
	ld (bl_dst),hl
	ld hl,vfl_blk		; полоса: правая половина — куски банков
	inc (hl)
	inc (hl)
	pop hl
	ld a,(bl_np)
	dec a
	ld (bl_np),a
	jp nz,bl_ob_p
bl_ob_x:
	pop hl
	ret

; --- заставка: обложка с дорожки COVER_TRACK потоком прямо в экран ($8000-$FFFF, окно закрыто), затем
; её палитра и хук полосы. Зовёт vec_boot_init последним (jp): буфер сектора — это место его кода.
bl_cover:
    if VI53
	ld hl,isr_c0		; счётчик 0 на время загрузки не заряжать (vec_isr.asm): щелчки на секторах
	ld b,5
bl_c0:
	ld (hl),0
	inc hl
	dec b
	jp nz,bl_c0
    endif
	ld b,COVER_TRACK
	call bl_seek1
	ld de,$8000
	call ap_depack
	ld hl,ls_pal
	ld de,vec_palette
	ld bc,16
	call z_ldir
	ld a,1
	ld (vec_pal_dirty),a
	ld hl,ls_hook
	ld (vec_key_hook),hl	; полоса (vec_lscreen.asm), хук снимает себя сам
	ret

bl_seek1:			; B = дорожка, сектор 1
	ld a,1
	ld (vec_fdd_sec),a
bl_seek:			; B = дорожка, сектор — в vec_fdd_sec; первый сектор -> буфер
	ld a,$34
	ld (vec_fdd_ctl),a
	push bc
	call vfl_restore
	pop bc
	call vfl_seek
	jp vfl_fill

ap_bits:	db 0
ap_lwm:		db 0
ap_r0:		dw 0
bl_page:	db 0
bl_bpg:		db 0
bl_np:		db 0
bl_dst:		dw 0
bl_src:		dw 0
bl_rec:		ds 5
bl_tab:		ds 24
