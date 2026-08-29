	org $100
	ld sp,$7f00
	ld hl,packed
	ld de,$4000
	call depack
	halt
packed:	incbin "../build/packed5.bin"
#include "../build/tr/depack.asm"
#include "../src/vec/z80rt.asm"
z_ix:	dw 0
z_iy:	dw 0
z_a:	db 0
z_tmp:	db 0
z_ret:	dw 0
z_af2:	dw 0
z_bc2:	dw 0
z_de2:	dw 0
z_hl2:	dw 0
