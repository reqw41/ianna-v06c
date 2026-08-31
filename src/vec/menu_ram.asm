; menu_ram.asm — RAM-блоб фазы меню (org = string_area): порт-небезопасные примитивы.
; Исполняется из ОЗУ, свободно крутит порт квазидиска. Копируется из квазидиска (стр.3 $9C00)
; кодом vec_menu_phase в ROM. Собирается отдельно с импортом символов игры (build/menu_syms.asm).
	include "menu_syms.asm"
KV_PORT		equ $10
KV_WIN_OVL	equ $43		; окно b6 ($8000-$9FFF) -> страница 3: там оверлей меню
	org MB_ORG

; --- таблица входов (фиксированные адреса для оверлея) ---
mb_call:	jp mb_call_i	; HL = процедура движка: закрыть окно, вызвать, открыть
mb_screen:	jp mb_screen_w	; экран меню с дискеты -> VRAM (24К, дорожка MB_TRK_MENU)
mb_slide:	jp mb_slide_w	; A = 0..4: слайд с дискеты -> VRAM; NZ = дисковода нет
mb_song:	jp mb_song_w	; A = 0 меню / 1 интро / 2 вернуть уровень: песня -> $C980 (стр.3)
mb_savelvl:	jp mb_savelvl_w	; песню уровня из $C980 -> страница 2 $E000 (перед меню)

; обёртки: после работы ВЕРНУТЬ окно оверлея (возврат идёт в код, живущий в окне!)
mb_screen_w:
	call mb_screen_i
	jp mb_reopen
mb_slide_w:
	call mb_slide_i
	jp mb_reopen
mb_song_w:
	call mb_song_i
	jp mb_reopen
mb_savelvl_w:
	call mb_savelvl_i
	jp mb_reopen
mb_reopen:			; сохранить флаги результата (Z у mb_slide)
	push af
	di
	ld a,KV_WIN_OVL
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	pop af
	ret

; --- переходник: движок с закрытым окном ---
mb_call_i:
	ld (mb_target),hl
	push af
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	pop af
	call mb_go
	push af
	di
	ld a,KV_WIN_OVL
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	pop af
	ret

mb_go:
	ld hl,(mb_target)
	jp (hl)

; --- копия блока квазидиск(окно) <-> VRAM/квазидиск через отскок ---
; вход: A = порт окна источника, HL = src, DE = dst (ОЗУ/VRAM вне окна), BC = длина
mb_copy:
	di
	out (KV_PORT),a
mbc_l:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	ld a,b
	or c
	jp nz,mbc_l
	xor a
	out (KV_PORT),a
	ei
	ret

; --- песня уровня: стр.3 $C980-$D97F -> отскок VRAM $E000 -> стр.1 $E000 ---
mb_savelvl_i:
	ld a,$23		; окно $A000-$DFFF стр.3
	ld hl,$C980
	ld de,$E000
	ld bc,$1000
	call mb_copy
	ld a,$81		; окно $E000-$FFFF стр.1: пишем туда из VRAM? нет — читаем VRAM нельзя при окне!
	; порядок: источник VRAM $E000 виден только при ЗАКРЫТОМ b7 -> копируем через ОЗУ-буфер страницы?
	; проще: пишем в стр.1 СТЕКОМ (push), читая VRAM $E000 при закрытых окнах
	di
	ld hl,0
	add hl,sp
	ld (mb_spsave),hl
	ld a,$18		; стек -> страница 2 (у 16ц-набора $BC40+ свободна)
	out (KV_PORT),a
	ld sp,$F000		; push вниз от $F000 до $E000 страницы 2
	ld hl,$EFFF
mbs_l:
	ld d,(hl)
	dec hl
	ld e,(hl)
	dec hl
	push de
	ld a,h
	cp $DF
	jp nz,mbs_l
	xor a
	out (KV_PORT),a
	ld hl,(mb_spsave)
	ld sp,hl
	ei
	ret

; --- песня в $C980: A=0 меню (стр.2 $C000), 1 интро (стр.2 $D000), 2 уровень (стр.1 $E000) ---
mb_song_i:
	or a
	jp nz,mbg_1
	ld a,$22
	ld hl,$C000
	jp mbg_go
mbg_1:
	dec a
	jp nz,mbg_2
	ld a,$22
	ld hl,$D000
	jp mbg_go
mbg_2:
	ld a,$82		; окно $E000-$FFFF -> страница 2 (сохранённая песня уровня)
	ld hl,$E000
mbg_go:
	; источник -> отскок VRAM $E000 (при окне источника; если источник сам в $E000 (порт $81) —
	; отскок в VRAM невозможен, копируем стеком: чтение POP из стр.1)
	cp $81
	jp z,mbg_stack
	ld de,$E000
	ld bc,$1000
	call mb_copy
	jp mbg_put
mbg_stack:
	di
	ld hl,0
	add hl,sp
	ld (mb_spsave),hl
	ld a,$18
	out (KV_PORT),a
	ld sp,$E000		; pop вверх от $E000 страницы 2
	ld hl,$E000		; dst VRAM
mbgs_l:
	pop de
	xor a
	out (KV_PORT),a		; окно закрыть на время записи в VRAM $E000
	ld (hl),e
	inc hl
	ld (hl),d
	inc hl
	ld a,$18
	out (KV_PORT),a
	ld a,h
	cp $F0
	jp nz,mbgs_l
	xor a
	out (KV_PORT),a
	ld hl,(mb_spsave)
	ld sp,hl
	ei
mbg_put:
	; отскок VRAM $E000 -> стр.3 $C980 (окно $23; чтение VRAM $E000 при открытом b5 — можно, b7 закрыт)
	di
	ld a,$23
	out (KV_PORT),a
	ld hl,$E000
	ld de,$C980
	ld bc,$1000
mbp_l:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	ld a,b
	or c
	jp nz,mbp_l
	xor a
	out (KV_PORT),a
	ei
	ret

; --- дискета: наличие, поиск дорожки, чтение N секторов в VRAM ---
mb_fdc_ok:			; Z = дисковод отвечает (эхо регистра сектора)
	ld a,$0B
	out ($19),a
	ld c,a
	ex (sp),hl
	ex (sp),hl
	in a,($19)
	cp c
	ret

; A = дорожка; читает 24 сектора (24К) -> VRAM $8000+
mb_load24:			; 32 сектора (полный дамп VRAM 32К) с дорожки A -> $8000..$FFFF
	ld (mb_track),a
	call mb_fdc_ok
	ret nz
	; окно оверлея ЗАКРЫТЬ: иначе $8000-$BFFF — страница 3 квазидиска, картинка ляжет поверх оверлея
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	ld a,$34
	ld (mb_ctl),a
	call mb_ctl_w
	xor a
	out ($1B),a		; RESTORE
	call mb_wait
	ld a,(mb_track)
	ld b,a
mbl_seek:
	ld a,$58
	out ($1B),a		; STEP-IN
	call mb_wait
	dec b
	jp nz,mbl_seek
	ld hl,$8000
	ld a,1
	ld (mb_sec),a
	ld b,32
mbl_next:
	push bc
	ld a,(mb_sec)
	ld c,a
	call mb_read
	pop bc
	jp nz,mbl_err
	ld a,(mb_sec)
	inc a
	ld (mb_sec),a
	cp 6
	jp nz,mbl_cont
	ld a,1
	ld (mb_sec),a
	ld a,(mb_ctl)
	xor 4
	ld (mb_ctl),a
	call mb_ctl_w
	and 4
	jp z,mbl_cont
	ld a,$58
	out ($1B),a
	call mb_wait
mbl_cont:
	dec b
	jp nz,mbl_next
	xor a
	ret
mbl_err:
	ld a,1
	or a
	ret

mb_read:			; сектор C -> (HL), Z = успех; DI на время сектора (DRQ-петля не терпит ISR)
	di
	call mb_ctl_w
	ld a,c
	out ($19),a
	ld de,$0103
	ld a,$80
	out ($1B),a
mbr_b:
	in a,($1B)
	rrca
	jp nc,mbr_b
mbr_d:
	in a,($1B)
	and e
	sub d
	jp z,mbr_d
	in a,($18)
	ld (hl),a
	inc hl
	jp p,mbr_d
	dec hl
	in a,($1B)
	and $9C
	ei
	ret
mb_ctl_w:
	ld a,(mb_ctl)
	out ($1C),a
	in a,($1B)
	rrca
	jp c,mb_ctl_w
	ld a,(mb_ctl)
	ret
mb_wait:
	in a,($1B)
	rrca
	jp c,mb_wait
	ret

mb_screen_i:
	ld a,MB_TRK_MENU
	jp mb_load24
mb_slide_i:
	add a,a
	add a,a			; *4 дорожки на слайд (32К = 3.2 дорожки)
	add a,MB_TRK_SLIDES
	jp mb_load24

mb_target:	dw 0
mb_spsave:	dw 0
mb_track:	db 0
mb_sec:		db 1
mb_ctl:		db $34
