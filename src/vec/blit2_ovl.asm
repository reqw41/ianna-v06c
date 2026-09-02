; blit2_ovl.asm — ЗЕРКАЛЬНЫЙ блит банка в двух плоскостях, вынесенный из ROM.
; В образе места нет (мёртвого кода в нём не оказалось, проверено вырезанием), поэтому код лежит в
; наборе уровня и при старте копируется поверх ТАБЛИЦЫ СЛОТОВ ($7F00): на уровне с двухплоскостным
; спрайтом пул выключен, слоты не нужны. Прямой блит остался в ROM (vec_blit2).
;
; ВАЖНО: внутри блита SP подменён на данные спрайта в квазидиске, поэтому здесь НЕЛЬЗЯ пользоваться
; call/ret — адрес возврата лёг бы прямо в читаемые данные. Всё развёрнуто в линию.
	include "menu_syms.asm"
KV_PORT		equ $10
	org $7F00

	jp vec_blit2m		; $7F00 — зеркальный блит четырёхцветного спрайта
	jp vec_scrpal		; $7F03 — палитра экрана (слоты 1..3) из набора уровня

; Палитра, своя для каждого экрана: три байта по адресу SCRPAL + номер экрана * 3. Фон в слоты 1..3
; не заглядывает (перестановка уровня увела его в 0 и 4..15), поэтому смена их цвета его не трогает.
vec_scrpal:
	ld hl,0
	ld a,(level_width)
	ld e,a
	ld d,0
	ld a,(current_levely)
	ld b,a
	or a
	jp z,sp_x
sp_mul:
	add hl,de
	dec b
	jp nz,sp_mul
sp_x:
	ld a,(current_levelx)
	ld e,a
	ld d,0
	add hl,de
	push hl
	add hl,hl
	pop de
	add hl,de		; номер экрана * 3
	ex de,hl		; на i8080 нет ld de,(nn): адрес таблицы читаем через HL
	ld hl,(vec_scrpal_addr)	; он приходит из набора — у каждого уровня свой
	add hl,de
	ld a,LEVELTAB_PORT
	out (KV_PORT),a
	ld de,vec_palette+1
	ld bc,3
	call z_ldir
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ld a,1
	ld (vec_pal_dirty),a
	ret

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
