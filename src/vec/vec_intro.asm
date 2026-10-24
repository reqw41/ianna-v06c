; vec_intro.asm — показ картинок меню и интро: плавное гашение/зажигание палитрой и смена
; середины слайда без перерисовки рамки и подложки текста. Живёт в ROM (в блоке меню места нет),
; зовётся из оверлея меню через MB_CALL: окно квазидиска закрыто, прерывания разрешены.
;
; Слайды интро 1 и 2 отличаются от нулевого только серединой (колонки 8..23, строки экрана 32..159),
; поэтому на дискете от них лежит одна середина: [4 смещения][4 сжатые плоскости по 2048 Б],
; плоскость — по колонкам, в колонке сверху вниз (tools/build_fdd.py pack_center).
VI_PICBUF	equ $A000	; дорожка, прочитанная mb_slrd (стр.3, окно $23)
VI_SCR		equ $B800	; распакованная плоскость середины, 2048 Б (хвост того же буфера)
VI_COL0		equ 8
VI_NCOL		equ 16
VI_L0		equ 223		; строка экрана 32
VI_NROW		equ 128
vec_palsave	equ vec_col_tab+160	; 16 Б: палитра, к которой возвращает vec_fade_in

; Плавно погасить: палитра запоминается и за 7 шагов по 3 кадра уходит в чёрный.
vec_fade_out:
	ld hl,vec_palette
	ld de,vec_palsave
	ld bc,16
	call z_ldir
	ld c,7
vfo_step:
	ld hl,vec_palette
	ld b,16
vfo_col:
	ld d,(hl)
	ld a,d
	and $07			; красный
	jp z,vfo_g
	dec d
vfo_g:
	ld a,d
	and $38			; зелёный
	jp z,vfo_b
	ld a,d
	sub $08
	ld d,a
vfo_b:
	ld a,c			; синий двухбитный — через шаг
	rra
	jp c,vfo_st
	ld a,d
	and $C0
	jp z,vfo_st
	ld a,d
	sub $40
	ld d,a
vfo_st:
	ld (hl),d
	inc hl
	dec b
	jp nz,vfo_col
	call vfd_show
	dec c
	jp nz,vfo_step
	ret
vfd_show:
	ld a,1
	ld (vec_pal_dirty),a	; прерывание перепишет палитру в ближайшем кадре
	halt
	halt
	halt
	ret

; Плавно показать: от чёрного к палитре из vec_palsave, обратным ходом vec_fade_out
; (на шаге s каждый канал = цель - s, не ниже нуля).
vec_fade_in:
	ld c,6
vfi_step:
	ld a,c
	add a,a
	add a,a
	add a,a
	ld (vfi_g+1),a		; s << 3
	ld a,c
	inc a
	rra			; (s+1)/2 — шаг синего
	and 3
	rrca
	rrca
	ld (vfi_b+1),a		; << 6
	ld hl,vec_palette
	ld de,vec_palsave
	ld b,16
vfi_col:
	push bc
	ld a,(de)
	and $07
	sub c
	jp nc,vfi_r
	xor a
vfi_r:
	ld b,a
	ld a,(de)
	and $38
vfi_g:
	sub 0
	jp nc,vfi_g1
	xor a
vfi_g1:
	or b
	ld b,a
	ld a,(de)
	and $C0
vfi_b:
	sub 0
	jp nc,vfi_b1
	xor a
vfi_b1:
	or b
	ld (hl),a
	pop bc
	inc hl
	inc de
	dec b
	jp nz,vfi_col
	call vfd_show
	dec c
	jp p,vfi_step
	ret

; Заливка прямоугольника в четырёх плоскостях. HL -> 4 значения (по плоскости), D = колонка,
; E = верхняя L, B = колонок, C = строк.
vec_frect4:
	ld a,d
	add a,$80
	ld d,a
	ld a,4
vfr_p:
	push af
	push de
	push bc
	ld a,(hl)
	inc hl
	push hl
vfr_c:
	ld h,d
	ld l,e
	push bc
vfr_r:
	ld (hl),a
	dec l
	dec c
	jp nz,vfr_r
	pop bc
	inc d
	dec b
	jp nz,vfr_c
	pop hl
	pop bc
	pop de
	ld a,d
	add a,$20
	ld d,a
	pop af
	dec a
	jp nz,vfr_p
	ret

; Стирание середины слайда и подложки текста (обёртки над vec_frect4) — в блобе меню (menu_ram.asm).

; Вывести середину слайда из прочитанной дорожки: плоскость распаковывается в буфер в квазидиске, оттуда
; переносится в экран СТЕКОМ: порт $1C (стек -> стр.3, окно закрыто), pop читает буфер, (hl) пишет в экран.
; Прерывания разрешены: ISR сохраняет стековые биты порта (vec_kv_shadow) и кладёт свои байты ниже SP —
; в $B400-$B7FF (дорожка 5 КБ кончается на $B3FF). Раньше байт шёл под коротким DI, и кадровое прерывание,
; попавшее в DI, терялось (ядро ставит запрос только при разрешённых): ~7 пропусков музыки на слайд (24.10).
; На Турбо+ подтверждение прерывания снимает стековый режим — там перенос под DI.
vec_slc_unp:
	xor a
vsu_p:
	ld (vsu_pl+1),a
	add a,a
	ld l,a
	ld h,VI_PICBUF/256
	ld a,$23
	call vsu_port
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	ld de,VI_PICBUF
	add hl,de		; сжатая плоскость
	ld de,VI_SCR
	call depack
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl	; в меню isr_spr не работает — ячейка свободна
vsu_pl:
	ld a,0			; плоскость -> старший байт первой колонки
	rrca
	rrca
	rrca
	add a,$80+VI_COL0
	ld b,a
	di
	ld a,$1C
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ld sp,VI_SCR
	ld a,(vec_turbo)
	or a
	jp nz,vsu_c
	ei
vsu_c:
	ld h,b
	ld l,VI_L0
	ld c,VI_NROW/2
vsu_r:
	pop de
	ld (hl),e
	dec l
	ld (hl),d
	dec l
	dec c
	jp nz,vsu_r
	inc b
	ld a,b
	and $1F
	cp VI_COL0+VI_NCOL
	jp nz,vsu_c
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ld a,(vsu_pl+1)
	inc a
	cp 4
	jp nz,vsu_p
	ret
; vsu_port — в окне vec_hi.asm (резидент полон)
