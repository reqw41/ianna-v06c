; vec_main.asm — инициализация и главный цикл теста (Вектор-06Ц).
; Вектор прерывания RST7 ($0038) прописываем сами.

vec_start:
	di
	ld sp,vec_stack_top
	; RST7 -> vec_isr
	ld a,$C3
	ld ($0038),a
	ld hl,vec_isr
	ld ($0039),hl
	; ППИ: A,B,C выходы; PB=0 (режим 256), PA=$FF (скролл норма)
	ld a,$80
	out ($00),a
	xor a
	out ($02),a
	ld a,$FF
	out ($03),a
    if !DEMO
	xor a
	out (KV_PORT),a		; квазидиск выкл
	call vec_fdd_load	; загрузка с дискеты, если квазидиск пуст (маркер 'IA' в стр.3 $C800)
    endif
	call cls
	call vec_init_rev256
    if !DEMO
	call vec_slot_init	; таблица слотов пула = $FF
    endif
	call initROMbanks
	call initVDPBuffers
	call InitTiles
	call MUSIC_Init
	; переменные как в main оригинала
	ld a,1
	ld (language),a		; 1 = английский (0 = испанский); меню оригинала позже даст выбор
	xor a
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
    if !DEMO
	call vec_menu_phase	; меню/интро (оверлей в окне квазидиска; без дисковода — сразу игра)
    endif
	; ---- begin_level (ianna.asm), без интро/музыки ----
	call InitVariables
	call InitSprites
	call InitEntities
	call InitObjectTable
	call InitPlayer
	call LoadScoreWeapons
	call LoadLevel
	ld a,1
	ld (show_passwd),a
	call SaveCheckpoint
vec_internal_loop:
	call game
	xor a
	ld (player_dead),a
	jp vec_internal_loop

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

    if !DEMO
; Фаза меню: блоб порт-примитивов из стр.3 $9C00 -> string_area, оверлей $8440 в окне b6 (порт $43)
vec_menu_phase:
	di
	ld a,$43
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	call $8440		; оверлей меню (сам копирует блоб из окна в string_area)
	di
	xor a
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	ret
    endif
