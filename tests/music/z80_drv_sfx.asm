; Эталон: оригинальный Z80-плеер Arkos (org $DDCC как в игре) + драйвер после него.
; Песня по $C980, эффекты по $D980. Кадр = call atPlay; out (#ff),a — маркер.
include "../../ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm"
start:
	di
	ld sp,$F000
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
	jr nz,loop
	ld a,l
	cp 6200 & 255
	jr nz,loop
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
