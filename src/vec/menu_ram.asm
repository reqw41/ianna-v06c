; menu_ram.asm — RAM-блоб фазы меню (org = string_area): порт-небезопасные примитивы.
; Исполняется из ОЗУ, свободно крутит порт квазидиска. Копируется из квазидиска (стр.3 $9C00)
; кодом vec_menu_phase в ROM. Собирается отдельно с импортом символов игры (build/menu_syms.asm).
	include "menu_syms.asm"
KV_PORT		equ $10
KV_WIN_OVL	equ $43
MB_KV_BUF	equ $23		; окно $A000-$DFFF, страница 3: буфер сжатой картинки (пул в игре, в меню свободен)
MB_PICBUF	equ $A000	; 10 КБ — дорожка целиком; музыка ISR лежит выше, с $C980
KV_STK_P3	equ $1C		; стековый режим, страница 3 (чтение шрифта из квазидиска)		; окно b6 ($8000-$9FFF) -> страница 3: там оверлей меню
	org MB_ORG

; --- таблица входов (фиксированные адреса для оверлея) ---
mb_call:	jp mb_call_i	; HL = процедура движка: закрыть окно, вызвать, открыть
mb_screen:	jp mb_screen_w	; экран меню с дискеты -> VRAM (24К, дорожка MB_TRK_MENU)
mb_slide:	jp mb_slide_w	; A = 0..4: слайд с дискеты -> VRAM; NZ = дисковода нет
mb_song:	jp mb_song_w	; A = 0 меню / 1 интро / 2 вернуть уровень: песня -> $C980 (стр.3)
mb_savelvl:	jp mb_savelvl_w	; песню уровня из $C980 -> страница 2 $E000 (перед меню)
mb_key:		jp mb_key_i	; ISR-хук: ASCII нажатой клавиши -> vec_key (0 = ничего)
mb_chr:		jp mb_chr_w	; A = код, B = колонка, C = строка: ПРОЗРАЧНАЯ печать (фон просвечивает)
mb_vsave:	jp mb_vsave_w	; B = кол., C = стр., D = колонок, E = строк, A = слот (0/1): VRAM -> квазидиск
mb_vrest:	jp mb_vrest_w	; те же параметры: квазидиск -> VRAM (вернуть фон)
mb_mchr:	jp mb_mchr_w	; A = код, B = кол., C = строка, D = 1 -> двойная высота: шрифт МЕНЮ
mb_wave:	jp mb_wave_w	; B = первая строка (px), C = сколько строк, A = фаза: волна на воде
mb_stripes:	jp mb_stripes_w	; B = колонка, D = колонок, C = строка, E = строк, HL = таблица полос

; обёртки: после работы ВЕРНУТЬ окно оверлея (возврат идёт в код, живущий в окне!)
mb_chr_w:
	call mb_chr_i
	jp mb_reopen
mb_stripes_w:
	call mb_stripes_i
	jp mb_reopen
mb_wave_w:
	call mb_wave_i
	jp mb_reopen
mb_mchr_w:
	call mb_mchr_i
	jp mb_reopen
mb_vsave_w:
	call mb_vsave_i
	jp mb_reopen
mb_vrest_w:
	call mb_vrest_i
	jp mb_reopen
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
	; песню, лежащую в VRAM $E000 (отскок), пишем в страницу 2 СТЕКОМ: окно $E000 подменило бы сам источник
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
	cp $82			; песня уровня лежит в стр.2 $E000 — только через стек (окно $E000 = та же VRAM)
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

; A = дорожка; читает 32 сектора (полный дамп VRAM 32К) -> VRAM $8000..$FFFF
mb_load24:
	ld (mb_track),a
	call mb_fdc_ok
	ret nz
	; окно оверлея ЗАКРЫТЬ: иначе $8000-$BFFF — страница 3 квазидиска, картинка ляжет поверх оверлея
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	call mb_seek
	ret nz
	ld hl,$8000
	ld b,32
	ld c,1
	jp mb_sectors

; seek на дорожку (mb_track); портит A, B
mb_seek:
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
	xor a
	ret

; HL = приёмник, B = сколько секторов, C = первый сектор; сторона переключается каждые 5
mb_sectors:
	ld a,c
	ld (mb_sec),a
mbl_next:
	push bc
	ld a,(mb_sec)
	ld c,a
	call mb_read
	pop bc
	jp nz,mbl_err
	ei			; отдать кадр прерыванию: иначе плеер молчит всю загрузку (ноты «зависают»)
	halt
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

; Картинка (экран меню = 0, слайды = 1..5) лежит на дискете СЖАТОЙ, по одной дорожке на картинку:
; [4 смещения по 2 байта][сжатые плоскости]. Дамп VRAM — это 32 КБ, вшестером они занимали 24 дорожки
; из 80, и девять наборов уровней на дискету не помещались. Плоскости жмутся отдельно: целиком 32 КБ
; распаковывать некуда — приёмник перекрыл бы буфер источника.
; Читаем дорожку в квазидиск (стр.3 $A000-$C800, окно), оттуда распаковываем в VRAM. Приёмники
; $8000 и $E000 лежат ВНЕ окна, поэтому пишутся в экран; плоскости 1 и 2 распаковываем в $8000 и
; копируем на место при закрытом окне. Порядок такой, чтобы $8000 освободился последним.
mb_screen_i:			; экран меню лежит в хвосте дорожек ROM: там свободно 8 КБ
	ld a,MB_TRK_MENU
	ld (mb_track),a
	ld a,MB_SEC_MENU
	jp mb_pic_go
mb_slide_i:
	add a,MB_TRK_SLIDES
	ld (mb_track),a
	ld a,1
mb_pic_go:
	ld (mb_sec),a
	call mb_fdc_ok
	ret nz
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	call mb_seek
	ret nz
	call mb_kv_on
	ld hl,MB_PICBUF
	ld b,8
	ld a,(mb_sec)
	ld c,a
	call mb_sectors
	push af
	call mb_kv_off
	pop af
	ret nz
	ld a,1			; плоскость 1 -> $8000, копия в $A000
	ld de,$8000
	call mb_pic_pl
	ld hl,$8000
	ld de,$A000
	call mb_pic_cp
	ld a,2			; плоскость 2 -> $8000, копия в $C000
	ld de,$8000
	call mb_pic_pl
	ld hl,$8000
	ld de,$C000
	call mb_pic_cp
	ld a,3			; плоскость 3 — сразу на место (вне окна)
	ld de,$E000
	call mb_pic_pl
	ld a,0			; плоскость 0 — последней: до неё $8000 был буфером
	ld de,$8000
	call mb_pic_pl
	xor a
	ret

; A = плоскость, DE = приёмник в VRAM; окно квазидиска открываем на время распаковки
mb_pic_pl:
	push de
	add a,a
	ld l,a
	ld h,0
	ld de,MB_PICBUF
	add hl,de
	call mb_kv_on
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	ld de,MB_PICBUF
	add hl,de		; HL = сжатая плоскость в окне квазидиска
	pop de
	call depack
	jp mb_kv_off

; HL -> DE, 8К (плоскость VRAM); окно закрыто, обе стороны — экран
mb_pic_cp:
	ld bc,$2000
	jp z_ldir

mb_kv_on:
	di
	ld a,MB_KV_BUF
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	ret
mb_kv_off:
	di
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	xor a
	ret

mb_target:	dw 0
mb_spsave:	dw 0
mb_track:	db 0
mb_sec:		db 1
mb_ctl:		db $34

; --- клавиатура: матрица Вектора (порт $03 = ряд активным нулём, порт $02 = столбцы активным нулём) ---
; ряд 2: цифры 0..7; ряд 3: 8,9 (биты 0,1); ряд 4: A..F (биты 1..6); ряд 0: ВК (бит 2)
mb_key_i:
	ld a,$82		; порт B ППИ -> вход (иначе in($02) отдаёт защёлку)
	out ($00),a
	ld hl,mb_keytab
mbk_row:
	ld a,(hl)		; маска ряда (0 = таблица кончилась)
	or a
	jp z,mbk_none
	out ($03),a
	inc hl
	in a,($02)
	cpl
	ld e,a			; E = нажатые биты ряда
	ld d,(hl)		; D = маска допустимых бит ряда
	inc hl
	ld c,(hl)		; C = код, соответствующий биту 0
	inc hl
	ld a,e
	and d
	jp z,mbk_row
	ld e,a
	ld b,0			; найти младший установленный бит
mbk_bit:
	ld a,e
	rrca
	jp c,mbk_found
	ld e,a
	inc b
	jp mbk_bit
mbk_found:
	ld a,c
	add a,b
	ld (vec_key),a
	jp mb_kbd_restore
mbk_none:
	xor a
	ld (vec_key),a
	jp mb_kbd_restore
mb_kbd_restore:			; вызывается из ISR — прерывания трогать нельзя
	ld a,$80		; порт B -> выход (как держит движок)
	out ($00),a
	xor a
	out ($02),a		; режим 256 точек
	ld a,$FF
	out ($03),a		; вернуть вертикальный скролл!
	ret
mb_keytab:				; маска ряда, маска бит, код бита 0
	db $FB,$FF,'0'			; ряд 2: 0..7
	db $F7,$03,'8'			; ряд 3: 8,9
	db $EF,$7E,'A'-1		; ряд 4: биты 1..6 = A..F
	db $FE,$04,13-2			; ряд 0: бит 2 = ВК
	db 0

; ================= прозрачная печать символа =================
; A = код (0..127+), B = колонка (0..31), C = строка (0..23 при Y_TOP_L=223).
; Глиф в квазидиске стр.3 по A*32: [плоскость][8 строк], плоскость 0 = старший бит цвета.
; Фон шрифта = индекс 1 (только младшая плоскость), поэтому маска тела = p0|p1|p2.
MB_YTOP		equ 223
mb_mchr_i:			; шрифт меню: база $E000, фон = 0 (маска по всем плоскостям), D = 1 -> двойная высота
	ld (mb_dbl),a
	ld a,d
	ld (mb_dblf),a
	ld a,1
	ld (mb_mfont),a
	ld a,(mb_dbl)
	jp mb_chr_go
mb_chr_i:
	ld (mb_dbl),a		; сохранить код ДО того, как A будет затёрт
	xor a
	ld (mb_mfont),a
	ld (mb_dblf),a
	ld a,(mb_dbl)
mb_chr_go:
	ld (mb_dbl),a
	ld a,(mb_dbl)
	sub 32			; как drawChar: код -> позиция в шрифте (0..127)
	and 127
	push bc
	; --- окно закрыть: VRAM $8000-$FFFF должна быть видна как память ---
	di
	push af
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	pop af
	; --- адрес глифа = A*32 ---
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld a,(mb_mfont)
	or a
	jp z,mbc_addr
	ld a,h
	add a,$E0		; шрифт меню лежит по $E000 страницы 3
	ld h,a
mbc_addr:
	; --- 32 байта глифа -> буфер (стековый режим страницы 3) ---
	ld (mb_ctmp),hl
	ld hl,0
	add hl,sp
	ld (mb_spsave),hl
	ld hl,(mb_ctmp)
	ld sp,hl
	ld a,KV_STK_P3
	out (KV_PORT),a
	ld hl,mb_gbuf
	ld b,16
mbc_rd:
	pop de
	ld (hl),e
	inc hl
	ld (hl),d
	inc hl
	dec b
	jp nz,mbc_rd
	xor a
	out (KV_PORT),a
	ld hl,(mb_spsave)
	ld sp,hl
	ei
	; --- маска тела: p0|p1|p2 ---
	ld hl,mb_gbuf
	ld de,mb_mask
	ld b,8
mbc_msk:
	ld a,(hl)		; p0
	push hl
	ld c,a
	ld a,l
	add a,8
	ld l,a
	ld a,h
	adc a,0
	ld h,a
	ld a,(hl)		; p1
	or c
	ld c,a
	ld a,l
	add a,8
	ld l,a
	ld a,h
	adc a,0
	ld h,a
	ld a,(hl)		; p2
	or c
	ld c,a
	push af
	ld a,(mb_mfont)
	or a
	jp z,mbc_m3
	ld a,l			; шрифт меню: фон = 0, значит в маску входит и младшая плоскость
	add a,8
	ld l,a
	ld a,h
	adc a,0
	ld h,a
	ld a,(hl)
	or c
	ld c,a
mbc_m3:
	pop af
	ld a,c
	ld (de),a
	inc de
	pop hl
	inc hl
	dec b
	jp nz,mbc_msk
	; --- запись 4 плоскостей ---
	pop bc			; B = колонка, C = строка
	ld a,c
	rlca
	rlca
	rlca
	ld c,a			; C = строка*8
	ld a,MB_YTOP
	sub c
	ld c,a			; C = L верхней строки символа
	ld a,b
	add a,$80
	ld b,a			; B = старший байт адреса плоскости 0
	ld hl,mb_gbuf
	ld (mb_gp),hl
	ld a,4
	ld (mb_pcnt),a
mbc_plane:
	ld hl,mb_mask
	ld (mb_mp),hl
	ld a,c
	ld (mb_row),a		; текущий L (строка VRAM)
	ld a,8
	ld (mb_rcnt),a
mbc_row:
	ld hl,(mb_gp)
	ld a,(hl)
	ld (mb_gval),a
	inc hl
	ld (mb_gp),hl
	ld hl,(mb_mp)
	ld a,(hl)
	ld (mb_mval),a
	inc hl
	ld (mb_mp),hl
	ld a,(mb_row)
	ld l,a
	ld h,b			; HL = адрес в VRAM (плоскость B, строка L)
	ld a,(mb_mval)
	cpl
	and (hl)		; оставить фон вне тела символа
	ld d,a
	ld a,(mb_mval)
	ld e,a
	ld a,(mb_gval)
	and e			; тело символа
	or d
	ld (hl),a
	ld a,(mb_row)
	dec a
	ld (mb_row),a
	ld a,(mb_dblf)		; двойная высота: та же строка ещё раз
	or a
	jp z,mbc_r1
	ld a,(mb_rep)
	or a
	jp nz,mbc_r1
	ld a,1
	ld (mb_rep),a
	ld hl,(mb_gp)		; вернуть указатели глифа и маски на строку назад
	dec hl
	ld (mb_gp),hl
	ld hl,(mb_mp)
	dec hl
	ld (mb_mp),hl
	jp mbc_row
mbc_r1:
	xor a
	ld (mb_rep),a
	ld a,(mb_rcnt)
	dec a
	ld (mb_rcnt),a
	jp nz,mbc_row
mbc_pnext:
	ld a,b
	add a,$20		; следующая плоскость
	ld b,a
	ld a,(mb_pcnt)
	dec a
	ld (mb_pcnt),a
	jp nz,mbc_plane
	ret

; ================= полосы фона: VRAM <-> квазидиск стр.3 $E000 =================
; B = колонка, C = строка (символьная), D = колонок, E = строк (символьных)
MB_BGBASE	equ $B000	; копия фона в квазидиске стр.3 (окно $A000-$DFFF), 6144 Б
KV_WIN_KV3	equ $23		; окно $A000-$DFFF -> страница 3
mb_vsave_i:
	ld (mb_slot),a
	xor a
	ld (mb_dir),a
	jp mb_vcopy
mb_vrest_i:
	ld (mb_slot),a
	ld a,1
	ld (mb_dir),a
mb_vcopy:
	di
	ld hl,MB_BGBASE		; слот 0 = валик с пунктами, слот 1 = нижняя строка
	ld a,(mb_slot)
	or a
	jp z,mbv_base
	ld hl,MB_BGBASE + $0800
mbv_base:
	ld (mb_bgp),hl
	ld a,e
	rlca
	rlca
	rlca
	ld (mb_nrow),a		; строк в пикселях
	ld a,c
	rlca
	rlca
	rlca
	ld c,a
	ld a,MB_YTOP
	sub c
	ld (mb_l0),a
	ld a,b
	add a,$80
	ld (mb_col0),a
	ld a,d
	ld (mb_ncol),a
	ld a,4
	ld (mb_pcnt),a
mbv_plane:
	ld a,(mb_ncol)
	ld (mb_ccnt),a
	ld a,(mb_col0)
	ld (mb_ccur),a
mbv_col:
	ld a,(mb_l0)
	ld (mb_row),a
	ld a,(mb_nrow)
	ld (mb_rcnt),a
mbv_row:
	ld a,(mb_ccur)
	ld h,a
	ld a,(mb_row)
	ld l,a			; HL = адрес в VRAM (окно закрыто)
	ld a,(mb_dir)
	or a
	jp nz,mbv_rest
	ld a,(hl)		; VRAM -> копия: открыть окно только на запись
	ld hl,(mb_bgp)
	ld c,a
	ld a,KV_WIN_KV3
	out (KV_PORT),a
	ld (hl),c
	xor a
	out (KV_PORT),a
	jp mbv_next
mbv_rest:
	ld c,l
	ld b,h			; BC = адрес VRAM
	ld hl,(mb_bgp)
	ld a,KV_WIN_KV3
	out (KV_PORT),a
	ld a,(hl)		; копия -> VRAM
	ld e,a
	xor a
	out (KV_PORT),a
	ld h,b
	ld l,c
	ld (hl),e
mbv_next:
	ld hl,(mb_bgp)
	inc hl
	ld (mb_bgp),hl
	ld a,(mb_row)
	dec a
	ld (mb_row),a
	ld a,(mb_rcnt)
	dec a
	ld (mb_rcnt),a
	jp nz,mbv_row
	ld a,(mb_ccur)
	inc a
	ld (mb_ccur),a
	ei			; между колонками отдать прерывание: иначе плеер спотыкается
	nop
	di
	ld a,(mb_ccnt)
	dec a
	ld (mb_ccnt),a
	jp nz,mbv_col
	ld a,(mb_col0)
	add a,$20
	ld (mb_col0),a
	ld a,(mb_pcnt)
	dec a
	ld (mb_pcnt),a
	jp nz,mbv_plane
	ei
	ret

mb_ctmp:	dw 0
mb_gp:		dw 0
mb_mp:		dw 0
mb_bgp:		dw 0
mb_gval:	db 0
mb_mval:	db 0
mb_row:		db 0
mb_rcnt:	db 0
mb_pcnt:	db 0
mb_ccnt:	db 0
mb_ccur:	db 0
mb_col0:	db 0
mb_l0:		db 0
mb_nrow:	db 0
mb_ncol:	db 0
mb_dir:		db 0
mb_slot:	db 0
mb_mfont:	db 0
mb_dblf:	db 0
mb_dbl:		db 0
mb_rep:		db 0
mb_gbuf:	ds 32
mb_mask:	ds 8

; ================= волна на отражении (как waveeffect оригинала) =================
; Строки VRAM сдвигаются на -1/0/+1 пикселя по бегущей фазе. Сумма таблицы = 0,
; поэтому картинка не уползает и копия оригинала не нужна.
; Вход: B = первая строка (в пикселях, 0..255), C = число строк, A = фаза (0..15).
mb_wave_i:
	push af
	di
	xor a
	out (KV_PORT),a		; окно закрыть: VRAM видна процессору
	ld (vec_kv_shadow),a
	ei			; дальше порт не трогаем — прерывания (плеер) не задерживаем
	pop af
	ld (mb_wph),a
	ld a,c
	ld (mb_wcnt),a
	ld a,b
	ld (mb_wy),a
mbw_line:
	; delta = mb_wavetab[(y + фаза) & 15]
	ld a,(mb_wy)
	ld hl,mb_wph
	add a,(hl)
	and 15
	ld e,a
	ld d,0
	ld hl,mb_wavetab
	add hl,de
	ld a,(hl)
	or a
	jp z,mbw_next		; сдвига нет
	ld (mb_wdelta),a
	; адрес строки: L = 255 - y, старший байт = $80 + колонка (идём по колонкам 0..31)
	ld a,(mb_wy)
	cpl			; L = 255 - y
	ld (mb_wl),a
	ld a,4
	ld (mb_wpl),a
	ld a,$80
	ld (mb_wph0),a
mbw_plane:
	; Циклический сдвиг строки на 1 пиксель. Адрес держим в HL и двигаемся шагом 256 (inc/dec H),
	; перенос между байтами — через CY (rlca соседа + ral байта): ~45 тактов на байт вместо ~90,
	; иначе 8 строк не укладываются в кадр и луч застаёт полосу недорисованной (мерцание).
	ld a,(mb_wdelta)
	and $80
	jp nz,mbw_right
	; --- влево: справа налево; старший бит левого крайнего байта заворачивается направо ---
	ld a,(mb_wph0)
	ld h,a
	ld a,(mb_wl)
	ld l,a
	ld b,(hl)		; исходный левый крайний байт
	ld a,(mb_wph0)
	add a,31
	ld h,a
	ld c,32
mbw_l1:
	ld a,b
	rlca			; CY = старший бит соседа справа
	ld a,(hl)
	ld b,a			; исходный байт — сосед для следующего слева
	rla			; сдвиг влево, в бит 0 приходит CY
	ld (hl),a
	dec h
	dec c
	jp nz,mbw_l1
	jp mbw_pnext
	; --- вправо: слева направо; младший бит правого крайнего байта заворачивается налево ---
mbw_right:
	ld a,(mb_wph0)
	add a,31
	ld h,a
	ld a,(mb_wl)
	ld l,a
	ld b,(hl)		; исходный правый крайний байт
	ld a,(mb_wph0)
	ld h,a
	ld c,32
mbw_r1:
	ld a,b
	rrca			; CY = младший бит соседа слева
	ld a,(hl)
	ld b,a
	rra			; сдвиг вправо, в бит 7 приходит CY
	ld (hl),a
	inc h
	dec c
	jp nz,mbw_r1
mbw_pnext:
	ld a,(mb_wph0)
	add a,$20
	ld (mb_wph0),a
	ld a,(mb_wpl)
	dec a
	ld (mb_wpl),a
	jp nz,mbw_plane
mbw_next:
	ld a,(mb_wy)
	inc a
	ld (mb_wy),a
	ld a,(mb_wcnt)
	dec a
	ld (mb_wcnt),a
	jp nz,mbw_line
	ret

mb_wavetab:	db 1,1,0,255,255,0,1,1,0,255,255,0,0,0,0,0	; 255 = -1; сумма = 0
mb_wy:		db 0
mb_wcnt:	db 0
mb_wph:		db 0
mb_wdelta:	db 0
mb_wl:		db 0
mb_wpl:		db 0
mb_wph0:	db 0
mb_wcol:	db 0

; ================= заливка полосами (фон валика меню) =================
; Валик — горизонтальные полосы: каждая строка одного цвета, поэтому фон под пунктами
; восстанавливается записью констант. Ни чтения квазидиска, ни DI (порт не трогаем).
; B = колонка, D = колонок, C = строка (символьная), E = строк (символьных), HL = таблица 4x32.
mb_stripes_i:
	; таблица лежит в оверлее (в окне) — скопировать в ОЗУ, пока окно ещё открыто
	push bc
	push de
	ld de,mb_sbuf
	ld b,128
mbs_cp:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec b
	jp nz,mbs_cp
	pop de
	pop bc
	ld hl,mb_sbuf
	ld (mb_stab),hl
	di
	xor a
	out (KV_PORT),a		; окно закрыть — VRAM видна процессору
	ld (vec_kv_shadow),a
	ei			; дальше порт не трогаем: прерывания (плеер) не задерживаем
	ld a,e
	rlca
	rlca
	rlca
	ld (mb_nrow),a		; строк в пикселях
	ld a,d
	ld (mb_ncol),a
	ld a,c
	rlca
	rlca
	rlca
	ld c,a
	ld a,MB_YTOP
	sub c
	ld (mb_l0),a		; L верхней строки
	ld a,b
	add a,$80
	ld (mb_col0),a
	ld a,4
	ld (mb_pcnt),a
mbs_plane:
	ld a,(mb_ncol)
	ld (mb_ccnt),a
	ld a,(mb_col0)
	ld (mb_ccur),a
mbs_col:
	ld hl,(mb_stab)		; таблица текущей плоскости
	ld a,(mb_ccur)
	ld d,a
	ld a,(mb_l0)
	ld e,a			; DE = адрес в VRAM (колонка, верхняя строка)
	ld a,(mb_nrow)
	ld c,a
mbs_row:
	ld a,(hl)
	inc hl
	ld (de),a		; строка одного цвета — просто константа
	dec e
	dec c
	jp nz,mbs_row
	ld a,(mb_ccur)
	inc a
	ld (mb_ccur),a
	ld a,(mb_ccnt)
	dec a
	ld (mb_ccnt),a
	jp nz,mbs_col
	ld a,(mb_col0)
	add a,$20
	ld (mb_col0),a
	ld hl,(mb_stab)
	ld de,32
	add hl,de
	ld (mb_stab),hl		; следующая плоскость таблицы
	ld a,(mb_pcnt)
	dec a
	ld (mb_pcnt),a
	jp nz,mbs_plane
	ret
mb_stab:	dw 0
mb_sbuf:	ds 128
mb_sval:	db 0
