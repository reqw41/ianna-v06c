; z80rt.asm — рантайм-хелперы для кода, оттранслированного z80to8080.py.
; Только i8080 (проверяется zasm --8080). Контракт: каждый хелпер бережёт
; HL, BC, DE, A и флаги, кроме явно объявленного результата.
;
; Ячейки (в vec_vars.asm): z_ix, z_iy (2 байта), z_a (1), z_tmp (1), z_ret (2),
; z_af2, z_bc2, z_de2, z_hl2 (2).

; ---------------------------------------------------------------------------
; ld a,(ix+d): вход A=d. Выход A=(ix+d). Флаги сохранены.
z_ix_rda:
	push hl
	push af
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ld a,(hl)
	pop hl
	ret
; то же, флаги можно портить (после инструкции они мертвы)
z_ix_rda_nf:
	push hl
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	pop hl
	ret
z_iy_rda:
	push hl
	push af
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ld a,(hl)
	pop hl
	ret
z_iy_rda_nf:
	push hl
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	pop hl
	ret

; ---------------------------------------------------------------------------
; HL := ix+d, d — байт после call. Бережёт A, флаги, BC, DE. HL — результат.
; (вызывающий сам сохраняет HL, если нужно)
z_ix_hl:
	ex (sp),hl		; HL=адрес возврата, (SP)=старый HL (не нужен)
	push af
	ld a,(hl)		; d
	inc hl
	ld (z_ret),hl
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ex (sp),hl		; HL=результат... нет: (SP)=старый HL -> вернём через z_ret
	; сейчас HL=старый HL, (SP)=результат. Нам нужно вернуть результат в HL,
	; а на стек положить адрес возврата.
	pop hl			; HL=результат, стек чист
	push hl
	ld hl,(z_ret)
	ex (sp),hl		; (SP)=адрес возврата, HL=результат
	ret
z_iy_hl:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	ld (z_ret),hl
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ex (sp),hl
	pop hl
	push hl
	ld hl,(z_ret)
	ex (sp),hl
	ret

; ---------------------------------------------------------------------------
; ld r,(ix+d) для r=b,c,d,e,h,l и ld (ix+d),r; d — байт после call.
; Реализованы через общий каркас: HL=ix+d вычисляется, затем действие.
; Макрос-подобная раскладка руками (i8080, без макросов zasm ради простоты).

; --- чтение в регистр (не A, не H/L): бережёт A, флаги, HL
z_ix_rd_b:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld b,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_rd_c:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld c,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_rd_d:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld d,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_rd_e:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld e,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
; --- чтение в H / L: результат кладётся в старый HL
z_ix_rd_h:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	ld (z_tmp),a
	pop hl
	pop af
	ex (sp),hl		; HL=старый HL, (SP)=адрес возврата
	push af
	ld a,(z_tmp)
	ld h,a
	pop af
	ret
z_ix_rd_l:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	ld (z_tmp),a
	pop hl
	pop af
	ex (sp),hl
	push af
	ld a,(z_tmp)
	ld l,a
	pop af
	ret
z_iy_rd_b:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld b,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_rd_c:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld c,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_rd_d:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld d,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_rd_e:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld e,(hl)
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_rd_h:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	ld (z_tmp),a
	pop hl
	pop af
	ex (sp),hl
	push af
	ld a,(z_tmp)
	ld h,a
	pop af
	ret
z_iy_rd_l:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld a,(hl)
	ld (z_tmp),a
	pop hl
	pop af
	ex (sp),hl
	push af
	ld a,(z_tmp)
	ld l,a
	pop af
	ret

; --- запись A / регистра / константы в (ix+d); d (и n) — байты после call
z_ix_sta:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	ld (z_ret),hl
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ld (hl),a
	ld hl,(z_ret)
	ex (sp),hl
	ret
z_iy_sta:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	ld (z_ret),hl
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	pop af
	ld (hl),a
	ld hl,(z_ret)
	ex (sp),hl
	ret
z_ix_st_b:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),b
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_st_c:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),c
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_st_d:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),d
	pop hl
	pop af
	ex (sp),hl
	ret
z_ix_st_e:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),e
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_st_b:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),b
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_st_c:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),c
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_st_d:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),d
	pop hl
	pop af
	ex (sp),hl
	ret
z_iy_st_e:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	push hl		; адрес возврата — на стек: [ret+1][af][старый HL]
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ld (hl),e
	pop hl
	pop af
	ex (sp),hl
	ret
; ld (ix+d),n : после call два байта: d, n
z_ix_stn:
	ex (sp),hl
	push af
	ld a,(hl)		; d
	inc hl
	ld (z_ret),hl
	ld hl,(z_ix)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ex de,hl		; DE=адрес назначения
	ld hl,(z_ret)
	ld a,(hl)		; n
	inc hl
	ld (z_ret),hl
	ld (de),a
	ex de,hl		; DE восстановлен, HL=мусор
	ld hl,(z_ret)
	pop af
	ex (sp),hl
	ret
z_iy_stn:
	ex (sp),hl
	push af
	ld a,(hl)
	inc hl
	ld (z_ret),hl
	ld hl,(z_iy)
	add a,l
	ld l,a
	jp nc,$+4	; перенос в старший байт редок (d мало): 12 тактов вместо 24
	inc h
	ex de,hl
	ld hl,(z_ret)
	ld a,(hl)
	inc hl
	ld (z_ret),hl
	ld (de),a
	ex de,hl
	ld hl,(z_ret)
	pop af
	ex (sp),hl
	ret

; ---------------------------------------------------------------------------
; ldir / ldi: как на Z80 (HL,DE += BC; BC=0). A и флаги сохраняются.
z_ldir:
	push af
z_ldir_l:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	ld a,b
	or c
	jp nz,z_ldir_l
	pop af
	ret
z_ldi:
	push af
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	dec bc
	pop af
	ret

; exx: обмен BC,DE,HL с тенями. A и флаги сохраняются.
z_exx:
	push af
	push hl			; исходный HL — на стек ДО обменов DE/BC (они портят HL как временный)
	push de
	ld hl,(z_de2)
	ex (sp),hl
	ld (z_de2),hl
	pop de
	push bc
	ld hl,(z_bc2)
	ex (sp),hl
	ld (z_bc2),hl
	pop bc
	ld hl,(z_hl2)
	ex (sp),hl		; HL = исходный HL, (SP) = hl2
	ld (z_hl2),hl
	pop hl			; HL = hl2
	pop af
	ret
; ex af,af'
z_exaf:
	push hl
	push af
	ld hl,(z_af2)
	ex (sp),hl
	ld (z_af2),hl
	pop af
	pop hl
	ret
