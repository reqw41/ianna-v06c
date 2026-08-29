; vec_boot.asm — точка входа, инициализация, главный цикл теста (Вектор-06Ц).
; Загрузка ROM по $0100 (vector06js ?ianna.rom, MiSTer .rom).
; Вектор прерывания RST7 ($0038) прописываем сами.

	org $0100
	jp vec_start

VDP_NY		equ 10		; смещение NY в буфере команды (как в vdp.asm)
FRAMES_LOCK	equ 5		; PAL: игровой тик = 5 кадров

vec_start:
	di
	ld sp,vec_stack_top
	; RST7 -> vec_isr
	ld a,$C3
	ld ($0038),a
	ld hl,vec_isr
	ld ($0039),hl
	; ППИ: A,B,C выходы; PB=0 (режим 256), PA=$FF (скролл норма); квазидиск выкл
	ld a,$80
	out ($00),a
	xor a
	out ($02),a
	ld a,$FF
	out ($03),a
	xor a
	out (KV_PORT),a
	; палитра-тень (применяется в ISR)
	call cls
	call vec_init_rev256
	call initROMbanks
	call initVDPBuffers
	call InitTiles
	; переменные как в main оригинала
	xor a
	ld (language),a
	ld (action_ack),a
	ld (wait_alternate),a
	ld (intro_shown),a
	ld (music_playing),a
	ld hl,123
	ld (randData),hl
	ld a,6
	ld (delay60HZ),a
	ld a,FRAMES_LOCK
	ld (frames_lock),a
	ld (frames_noredraw),a
	xor a
	ld (current_level),a		; уровень 1
	ld (player_dead),a
	ei
	; ---- begin_level (ianna.asm), без интро/музыки ----
	call InitVariables
	call InitSprites
	call InitEntities
	call InitObjectTable
	call InitPlayer
	call LoadLevel
	ld a,1
	ld (show_passwd),a
	call SaveCheckpoint
vec_internal_loop:
	call game
	; player_dead: 2 -> меню (у нас: заново уровень), 3 -> новый уровень, 4 -> конец
	xor a
	ld (player_dead),a
	jp vec_internal_loop

; waitforVBlank: ждём, пока с последней перерисовки пройдёт frames_lock кадров.
; (Оригинал в это же время дорисовывает панель счёта — у нас панели пока нет.)
waitforVBlank:
	push af
	push hl
wfv_loop:
	ld a,(frames_noredraw)
	ld hl,frames_lock
	cp (hl)
	jp nc,wfv_done
	halt
	jp wfv_loop
wfv_done:
	xor a
	ld (frames_noredraw),a
	pop hl
	pop af
	ret

; таблица разворота байта (для зеркальных спрайтов), выровнена на страницу
vec_init_rev256:
	ld hl,rev256
	ld c,0
vir_l:
	ld a,c
	ld b,8
	ld e,0
vir_b:
	rra
	ld d,a
	ld a,e
	rla
	ld e,a
	ld a,d
	dec b
	jp nz,vir_b
	ld (hl),e
	inc hl
	inc c
	jp nz,vir_l
	ret
