; zp_blit2m.asm — зеркальный прямой блит двухплоскостного спрайта в НУЛЕВОЙ СТРАНИЦЕ ОЗУ.
; Вырезан из vec_blit2.asm 2026-09-04: образ ROM заполнен под ноль, а $003B-$00FF (197 Б) свободны на
; всех уровнях (там только вектор RST7 по $38). Код лежит в наборе каждого уровня по ZPSRC (стр.2 $BF00,
; бывшее место оверлея blit2) и копируется vec_load_leveltab при старте уровня.
	include "menu_syms.asm"
KV_PORT	equ $10
	org ZP_BLIT2M
; ---------------------------------------------------------------------------
; vec_blit2m — ЗЕРКАЛЬНЫЙ прямой блит двухплоскостного банка (переполнение пула / супертайл без
; слота). Жил в наборе уровня поверх таблицы слотов ($7F00), пока пул на таких уровнях был выключен;
; теперь пул работает везде, таблица слотов нужна всегда — код вернулся в образ.
; ВАЖНО: SP подменён на данные спрайта в квазидиске, поэтому здесь НЕЛЬЗЯ call/ret — всё в линию.
vec_blit2m:
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
	ld a,(vec_spr_port)
	ld (vec_spr_curport),a
	out (KV_PORT),a
b2m_col:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
b2m_row:
	pop bc			; C = старший бит строки A, B = её маска
	pop de			; E = младший бит строки A, D = старший бит строки B
	ld (vec_spr_dst),hl
	ld h,rev256/256		; развернуть все четыре байта
	ld l,c
	ld c,(hl)
	ld l,b
	ld b,(hl)
	ld l,e
	ld e,(hl)
	ld l,d
	ld d,(hl)
	ld hl,(vec_spr_dst)
	ld a,b
	and (hl)
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
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
	sub $60
	ld h,a
	inc l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp z,b2m_col_end
	pop bc			; C = маска строки B, B = её младший бит
	ld (vec_spr_dst),hl
	ld h,rev256/256
	ld l,c
	ld a,(hl)
	ld l,b
	ld e,(hl)
	ld hl,(vec_spr_dst)
	ld b,a
	ld c,d			; старший бит строки B развернули выше
	ld a,b
	and (hl)
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
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
	sub $60
	ld h,a
	inc l
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,b2m_row
b2m_col_end:
	ld a,(vec_spr_skip2)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,vec_spr_hcol	; HL здесь свободен — короче, чем через A
	dec (hl)
	ld hl,vec_col_cnt
	dec (hl)
	jp nz,b2m_col
	jp vec_stk_leave

zp_size	equ $ - ZP_BLIT2M
