; Загрузка банков спрайтов из библиотеки на дискете.
; Раньше набор уровня был готовым слепком квазидиска вместе с банками, и один и тот же тролль
; лежал на дискете пять раз — в каждом наборе по своему адресу. Теперь банки хранятся по одному
; разу, а набор несёт РЕЦЕПТ: для каждого банка дорожка, сектор, порт страницы и адрес.
;
; Этот код живёт в наборе уровня (страница 3), при загрузке копируется в string_area и работает
; ПОВЕРХ примитивов ROM-загрузчика ($7E00): к моменту вызова они ещё целы — таблицы rev256 и
; слотов строятся позже. Строки уровня в string_area тоже кладутся позже, так что место свободно.
;
; Формат банка в библиотеке: [N кусков][по 4 байта на кусок: сжатая длина, распакованная длина]
; [сжатые куски]. Кусок — 8 КБ квазидиска, распаковывается через тот же буфер, что и блоки набора.
	include "menu_syms.asm"
KV_PORT		equ $10
FDD_REC		equ FDD_TAB + 64	; рецепт банков: [M][M x 5 байт]
FDD_BSRC	equ $8000		; сжатый кусок (VRAM, вне окна квазидиска)
FDD_BDST	equ $C000		; распакованный кусок (VRAM)

	org FB_ORG
fb_go:
	ld a,(FDD_REC)
	or a
	ret z
	ld (fb_cnt),a
	ld hl,FDD_REC+1
	ld (fb_ptr),hl
fb_next:
	ld hl,(fb_ptr)
	ld a,(hl)		; дорожка банка
	ld (fb_trk),a
	inc hl
	ld a,(hl)		; сектор
	ld (vec_fdd_sec),a
	inc hl
	ld a,(hl)		; порт квазидиска (страница + бит «две плоскости» игнорируется здесь)
	and $1C
	or $10
	ld (fb_port),a
	inc hl
	ld a,(hl)
	ld (fb_dst),a
	inc hl
	ld a,(hl)
	ld (fb_dst+1),a
	inc hl
	ld (fb_ptr),hl
	ld a,$34
	ld (vec_fdd_ctl),a
	call vfl_restore
	ld a,(fb_trk)
	ld b,a
	call vfl_seek
	call vfl_fill
	ld hl,fb_tab		; заголовок банка: сперва число кусков, потом по 4 байта на кусок —
	ld bc,1			; читать фиксированной длиной нельзя, поток съедет
	call vfl_stream
	ld a,(fb_tab)
	ld (fb_np),a
	add a,a
	add a,a			; 4 байта на кусок: сжатая и распакованная длины
	ld c,a
	ld b,0
	ld hl,fb_tab+1
	call vfl_stream
	ld hl,fb_tab+1
	ld (fb_lp),hl
fb_part:
	ld hl,(fb_lp)
	ld c,(hl)
	inc hl
	ld b,(hl)		; BC = сжатая длина куска
	inc hl
	ld e,(hl)
	inc hl
	ld d,(hl)		; DE = распакованная длина
	inc hl
	ld (fb_lp),hl
	ld a,e
	ld (fb_ulen),a
	ld a,d
	ld (fb_ulen+1),a
	ld hl,FDD_BSRC
	call vfl_stream
	ld hl,FDD_BSRC
	ld de,FDD_BDST
	call depack
	call fb_store
	ld hl,(fb_ulen)		; следующий кусок ложится за предыдущим
	ex de,hl
	ld hl,(fb_dst)
	add hl,de
	ld (fb_dst),hl
	ld a,(fb_np)
	dec a
	ld (fb_np),a
	jp nz,fb_part
	ld a,(fb_cnt)
	dec a
	ld (fb_cnt),a
	jp nz,fb_next
	ret

; Кусок из FDD_BDST -> квазидиск по (fb_port, fb_dst), длина fb_ulen (чётная).
; Пишем стековым режимом, как ROM-загрузчик: push кладёт два байта за раз и идёт ВНИЗ.
fb_store:
	di
	ld hl,(fb_ulen)
	ex de,hl
	ld hl,(fb_dst)
	add hl,de
	ld (vec_fdd_dst),hl	; конец куска
	ld hl,0
	add hl,sp
	ld (vec_fdd_sp),hl
	ld hl,(vec_fdd_dst)
	ld sp,hl
	ld a,(fb_port)
	out (KV_PORT),a
	ld hl,(fb_ulen)
	ld de,FDD_BDST-1
	add hl,de		; HL = последний байт распакованного
	push hl
	ld hl,(fb_ulen)		; DE = сколько ПАР байт писать
	ld a,h
	or a
	rra
	ld d,a
	ld a,l
	rra
	ld e,a
	pop hl
	ld a,d
	or e
	jp z,fb_st_end		; нечего писать
fb_push:
	ld b,(hl)
	dec hl
	ld c,(hl)
	dec hl
	push bc
	dec de
	ld a,d
	or e
	jp nz,fb_push
fb_st_end:
	xor a
	out (KV_PORT),a
	ld hl,(vec_fdd_sp)
	ld sp,hl
	ei
	ret

fb_ptr:		dw 0
fb_cnt:		db 0
fb_trk:		db 0
fb_port:	db 0
fb_dst:		dw 0
fb_np:		db 0
fb_lp:		dw 0
fb_ulen:	dw 0
fb_tab:		ds 25		; [N][4 байта на кусок] — банк не длиннее шести кусков
