; vec_stubs.asm — заглушки модулей MSX2, которых в тесте движка нет:
; музыка/эффекты, панель счёта, шрифт, меню, пауза.

    if DEMO
MUSIC_Init:
MUSIC_Stop:
MUSIC_Load:
MUSIC_Play:
FX_Play:
	ret
    endif
; menu / pause (pause_menu = оверлей квазидиска)
pause_menu:
    if !DEMO
	jp vec_pause_phase
    endif
mainmenu:
intro:
ending:
enableSLOT2:
enableSLOT2_EI:
; font/menu: шрифт меню и прозрачные символы не нужны
FONT:
menu_font:
drawCharFront:
drawCharTrans:
drawCharTrans_Double:
drawCharTrans_front:
	ret
; memory.asm
initROMbanks:
	xor a
	ld (ROMBank0),a
	inc a
	ld (ROMBank1),a
	ret
