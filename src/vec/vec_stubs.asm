; vec_stubs.asm — заглушки модулей MSX2, которых в тесте движка нет:
; музыка/эффекты, панель счёта, шрифт, меню, пауза.

MUSIC_Init:
MUSIC_Stop:
MUSIC_Load:
MUSIC_Play:
FX_Play:
	ret
; score.asm
load_scorearea:
draw_score_status:
draw_score_inventory:
draw_barbarian_state:
draw_enemy_state:
LoadScoreWeapons:
draw_password:
draw_gameover_string:
update_score_energy:
print_string_notification:
draw_string_area:
	ret
; font.asm
LoadFONT:
LoadFONT_menu:
print_string:
print_string_menu:
	ret
; menu / pause
pause_menu:
mainmenu:
intro:
ending:
	ret
; memory.asm
initROMbanks:
	xor a
	ld (ROMBank0),a
	inc a
	ld (ROMBank1),a
	ret
enableSLOT2:
enableSLOT2_EI:
	ret
clean_scorearea:
drawChar:
force_inv_redraw:
	ret
