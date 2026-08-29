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
	ld a,$FF
	out ($FF),a
	inc hl
	ld a,h
	cp 600/256
	jr nz,loop
	ld a,l
	cp 600 & 255
	jr nz,loop
	halt
