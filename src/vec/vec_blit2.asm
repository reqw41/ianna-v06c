; vec_blit2.asm — блит спрайта из банка в ДВУХ плоскостях (четыре цвета, кадр 288 Б).
; Строка кадра — три байта [плоскость 0, маска, плоскость 1], поэтому за три чтения стеком берём
; сразу ДВЕ строки. Прозрачность несёт маска, значение 0 — полноценный цвет (в палитре уровня он
; чёрный, им закрашен контур). Плоскости 2 и 3 спрайт не пишет, но гасит под собой: фон уровня их
; использует, и без гашения под спрайтом остались бы старшие биты фона.
; Пропуска пустых строк (skip) в этом формате нет — у крупного спрайта он почти не срабатывал.

vec_blit2:			; вход как у ds_direct: vec_spr_src, vec_spr_hcol, vec_spr_lbot, vec_spr_ny
	ld a,3
	ld (vec_col_cnt),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	out (KV_PORT),a
b2_col:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a
	ld a,(vec_spr_ny)
	ld (vec_row_cnt),a
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
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
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
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
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
	jp nz,b2_col
	jp vec_stk_leave
