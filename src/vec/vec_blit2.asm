; vec_blit2.asm — блит спрайта из банка в ДВУХ плоскостях (четыре цвета, кадр 288 Б).
; Строка кадра — три байта [плоскость 0, маска, плоскость 1], поэтому за три чтения стеком берём
; сразу ДВЕ строки. Прозрачность несёт маска, значение 0 — полноценный цвет (в палитре уровня он
; чёрный, им закрашен контур). Плоскости 2 и 3 спрайт не пишет, но гасит под собой: фон уровня их
; использует, и без гашения под спрайтом остались бы старшие биты фона.
; Пропуска пустых строк (skip) в этом формате нет — у крупного спрайта он почти не срабатывал.

vec_blit2:			; вход как у ds_direct: vec_spr_src, vec_spr_hcol, vec_spr_lbot, vec_spr_ny
	ld a,36			; цена колонки: окно DI 33.9 ед. на колонку из 32 строк (blitcalib)
	ld (vec_spr_colcost),a
	; Конец колонки по L, а не по счётчику в памяти: L растёт на строку, колонка кончается на
	; lbot+NY (оба поля постоянны на весь спрайт, L не переполняется: lbot+NY = 224-y <= 224).
	; Счётчик в памяти стоил 40 тактов на строку (ld a,(nn) 16 + dec 8 + ld (nn),a 16), свободных
	; регистров в теле нет (BC/DE — данные двух строк, HL — приёмник, SP — источник), поэтому
	; предел вшивается в сам `cp` — самомодификация, как в rit_call обхода грязных тайлов.
	ld a,(vec_spr_lbot)
	ld hl,vec_spr_ny
	add a,(hl)
	ld (b2_endA+1),a
	ld (b2_endB+1),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)	; vec_spr_curport уже записан в ds_direct
	out (KV_PORT),a
	; Бюджет ПО КОЛОНКАМ, как у шестнадцатицветного пути. Раньше этот блит шёл без бюджета вовсе:
	; 107 ед. кадра (замер blitcost) вслепую — перекрывал VBlank, терял прерывание, и бюджет ждал
	; следующий кадр. Цена колонки — vec_spr_colcost из ds_cost (с запасом).
b2_budget:
	ld hl,b2_col
	ld (vec_blit_ret),hl
	jp vec_spr_colbud
b2_col:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a			; счётчик строк не нужен: колонка кончается по L (b2_endA/b2_endB)
b2_row:
	pop bc			; C = плоскость 0 строки A, B = её маска
	pop de			; E = плоскость 1 строки A, D = плоскость 0 строки B
	ld a,b
	and (hl)		; плоскость 0 — только гасим (цвет 0..3 живёт в младших битах)
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)		; плоскость 1 — только гасим
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or c			; плоскость 2 — старший бит цвета
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or e			; плоскость 3 — младший бит
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
	inc l
	ld a,l
b2_endA:
	cp 0			; самомодификация: lbot + NY
	jp z,b2_col_end
	pop bc			; C = маска строки B, B = её плоскость 1
	ld a,c
	and (hl)		; плоскость 0 — гасим
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,c
	and (hl)		; плоскость 1 — гасим
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,c
	and (hl)
	or d			; плоскость 2 — старший бит
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,c
	and (hl)
	or b			; плоскость 3 — младший бит
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
	inc l
	ld a,l
b2_endB:
	cp 0			; самомодификация: lbot + NY
	jp nz,b2_row
b2_col_end:
	ld a,(vec_spr_skip2)	; хвост колонки: (32-NY)*3 байта
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,vec_spr_hcol	; HL здесь уже свободен — короче, чем через A
	inc (hl)
	ld hl,vec_col_cnt
	dec (hl)
	jp nz,b2_budget
	jp vec_stk_leave

; vec_blit2m — зеркальный прямой блит двухплоскостного банка — живёт в НУЛЕВОЙ СТРАНИЦЕ ($003B..):
; src/vec/zp_blit2m.asm собирается отдельно (build/zp.bin), лежит в наборе уровня по ZPSRC (стр.2 $BF00)
; и копируется vec_load_leveltab. В образе места нет (зазор 0), а $003B-$00FF свободны всегда.

; vec_scrpal — палитра экрана: три байта (слоты 1..3) по адресу vec_scrpal_addr + номер экрана * 3.
; Их занимает четырёхцветный спрайт этого экрана, фон в них не заглядывает (перестановка уровня
; увела его в 0 и 4..15). Зовётся из LoadScreen (патч build_vec). Адрес 0 = у уровня такой таблицы
; нет (нет четырёхцветных банков) — выходим сразу.
vec_scrpal:
	ld hl,(vec_scrpal_addr)
	ld a,h
	or l
	ret z
	push hl
	ld a,(level_width)	; номер экрана: levely*width + levelx (Mul8x8 оригинала, HL = H*E)
	ld e,a
	ld a,(current_levely)
	ld h,a
	call Mul8x8
	ld a,(current_levelx)
	ld e,a
	ld d,0
	add hl,de
	push hl
	add hl,hl
	pop de
	add hl,de		; номер экрана * 3
	pop de			; адрес таблицы в наборе — у каждого уровня свой
	add hl,de
	ld a,LEVELTAB_PORT
	out (KV_PORT),a
	ld de,vec_palette+1
	ld bc,3
	call z_ldir
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	inc a			; ISR проверяет флаг на «не ноль» — короче, чем ld a,1
	ld (vec_pal_dirty),a
	ret

; --- позиции страниц героя на дискете --------------------------------------------------------
; По два байта (дорожка, сектор) на вид оружия: 0 меч, 1 топор, 2 клинок, 3 затмение. Прошивает
; build_fdd.py прямо в образ ROM по адресу из листинга — так же, как vfl_dirtab. Дорожка 0 = такой
; страницы на дискете нет (запуск без дискеты, IANNA_SKIP_BANKS): fb_wpn тогда ничего не читает и
; герой остаётся с мечом. Место — В КОДЕ, а не среди переменных: таблица нужна и в игре, и при
; загрузке уровня, а переменные под стеком считаны по байтам.
vec_wpntab:	ds 8
