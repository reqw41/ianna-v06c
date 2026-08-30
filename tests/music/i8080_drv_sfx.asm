; Стенд переведённого плеера Arkos на i8080: песня по $C980, эффекты по $D980 (обычная память).
; Каждый кадр: atPlay; out ($FF) = маркер кадра. Через 600 кадров halt.
	org $0100
	jp start
DEMO	equ 0
VDP_NY	equ 10
MUSIC_ROM_PAGE equ 40
start:
	di
	ld sp,$7F00
	ld de,$C980
	call atInit
	ld de,$D980
	call atSfxInit
	ld hl,0
loop:
	push hl
	call atPlay
	pop hl

	; эффекты: таблица (кадр lo, hi, номер); канал 1, громкость 15, нота 36 — как FX_Play
	push hl
	ld de,sfx_tab
trig_l:
	inc de
	inc de
	ld a,(de)
	or a
	jp z,trig_end
	dec de
	dec de
	ld a,(de)
	cp l
	jp nz,trig_n
	inc de
	ld a,(de)
	dec de
	cp h
	jp nz,trig_n
	inc de
	inc de
	ld a,(de)
	dec de
	dec de
	push de
	push hl
	ld l,a
	ld a,1
	ld h,15
	ld e,36
	ld d,0
	ld bc,0
	call atSfxPlay
	pop hl
	pop de
trig_n:
	inc de
	inc de
	inc de
	jp trig_l
trig_end:
	pop hl
	ld a,$FF
	out ($FF),a
	inc hl
	ld a,h
	cp 6200/256
	jp nz,loop
	ld a,l
	cp 6200 & 255
	jp nz,loop
	halt
sfx_tab:
	db 100,0,1
	db 44,1,2
	db 188,2,3
	db 176,4,4
	db 220,5,5
	db 230,5,6
	db 208,7,7
	db 40,10,1
	db 228,12,3
	db 4,16,2
	db 136,19,5
	db 112,23,4
	db 0,0,0
#include "../../build/tr/arkos.asm"
#include "../../src/vec/z80rt.asm"
z_ix:	dw 0
z_iy:	dw 0
z_a:	db 0
z_tmp:	db 0
z_ret:	dw 0
z_af2:	dw 0
z_bc2:	dw 0
z_de2:	dw 0
z_hl2:	dw 0
ply_sd_cnt: db 0
ply_hd_cnt: db 0
ply_sd_loop: db 0
