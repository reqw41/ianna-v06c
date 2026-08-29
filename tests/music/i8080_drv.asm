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
	ld a,$FF
	out ($FF),a
	inc hl
	ld a,h
	cp 600/256
	jp nz,loop
	ld a,l
	cp 600 & 255
	jp nz,loop
	halt
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
