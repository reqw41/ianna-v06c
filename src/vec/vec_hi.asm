; vec_hi.asm — окно $6AB0-$6AF8 в середине vec_col_tab: таблица колонок занимает $6A00-$6A9F, за ней
; vec_palsave ($6AA0, 16 Б) и с $6AF9 ячейки читов и флагов колонок (vec_vdp.asm). Середина свободна, а
; код до $6A00 исчерпан — сюда ложатся данные и код, которым всё равно, где жить. Образ ROM грузится
; целиком, поэтому код здесь есть с самого старта; vec_slot_init чистит только первые 160 Б.
; Границу окна проверяет build_vec.py (vec_hi_end <= $6AF9). В демо (vars с $7400) — просто подряд.
    if !DEMO
	org $6AB0
    endif
; Список слотов врагов для сброса ГРУППОЙ (vpb_gr_add -> vpf_grp): все слоты после героя, по порядку
; раздачи. Слоты спрайта выводятся подряд, а не вперемешку с полосами поля: окно, пока спрайт на экране
; наполовину новый, у голема 165-250 ед. -> 80-100 (tools/teartest.py --sprites). Не влезло в список —
; тик идёт прямым путём, как при переполнении списка героя (обход пропускает слоты группы, пока она
; ждёт героя, — им нельзя потеряться). Сам список — в vec_palsave: палитра для гашения нужна только меню и заставке,
; а список живёт от раздачи слотов до сброса внутри одного тика.
VEC_GR_N	equ 16
vec_gr_list	equ vec_palsave
vec_gr_lp:	dw 0		; конец списка (выводится с конца к началу)
; Раздача (vpb_sxl): слот не героя — в список. HL — указатель в таблицу слотов, цел.
vpb_gr_add:
	ld a,(vec_gr_lp)
	cp $ff & (vec_gr_list+VEC_GR_N)
	jp z,vpb_ovf
	push hl
	ld a,l
	ld hl,(vec_gr_lp)
	ld (hl),a
	inc hl
	ld (vec_gr_lp),hl
	pop hl
	jp vpb_sx_next
; A = код источника (биты 0-1 регистр, бит 2 — развёрнут) -> A = байт пары. Портит HL.
isrs_byte:
	ld h,a
	and 3
	ld l,b
	jp z,isb_r
	ld l,c
	dec a
	jp z,isb_r
	ld l,d
	dec a
	jp z,isb_r
	ld l,e
isb_r:
	ld a,h
	and 8
	jp z,isb_r4
	ld a,(isr_a)
	ld l,a
isb_r4:
	ld a,h
	and 4
	ld a,l
	ret z
	push de
	ld e,l
	ld d,rev256/256
	ld a,(de)
	pop de
	ret

vec_hi_end:
