; vec_blit2.asm — блит спрайта из банка в ДВУХ плоскостях (четыре цвета, кадр 288 Б).
; Строка кадра — три байта [плоскость 0, маска, плоскость 1], поэтому за три чтения стеком берём
; сразу ДВЕ строки. Прозрачность несёт маска, значение 0 — полноценный цвет (в палитре уровня он
; чёрный, им закрашен контур). Плоскости 2 и 3 спрайт не пишет, но гасит под собой: фон уровня их
; использует, и без гашения под спрайтом остались бы старшие биты фона.
; Пропуска пустых строк (skip) в этом формате нет — у крупного спрайта он почти не срабатывал.

vec_blit2:			; вход как у ds_direct: vec_spr_src, vec_spr_hcol, vec_spr_lbot, vec_spr_ny
	ld a,38			; цена колонки: 107 ед. на три колонки по 32 строки (blitcost) + запас
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
