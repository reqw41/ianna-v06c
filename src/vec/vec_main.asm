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
	ld (current_level),a	; уровень 1: загрузчик читает эту ячейку (инициализация ниже — уже поздно)
	call vec_fdd_load	; загрузка с дискеты, если квазидиск пуст (маркер 'IA' в стр.3 $C800)
	ld hl,vfl_dirtab	; таблицу дорожек уровней прошивает build_fdd прямо в образ ROM, а в
	ld de,vec_dirtab	; копии загрузчика внутри набора она нулевая — сохраняем, пока цела
	ld bc,16
	call z_ldir
	call vec_load_leveltab	; палитра, банки спрайтов и передние тайлы — из набора уровня
    endif
	call cls
	call vec_init_rev256
    if !DEMO
	call vec_slot_init	; таблица слотов пула = $FF (пул работает на всех уровнях)
    endif
	call initROMbanks
	call initVDPBuffers
	call InitTiles
	call MUSIC_Init
	; переменные как в main оригинала
	xor a
	ld (language),a		; РУССКОЕ ИЗДАНИЕ: язык один — русский (слот 0, бывший испанский)
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
	call vec_menu_phase	; меню/интро (оверлей в окне квазидиска; без дисковода — сразу игра) (оверлей в окне квазидиска; без дисковода — сразу игра)
    endif
	; ---- begin_level (ianna.asm), без интро/музыки ----
vec_begin_level:
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
	ld a,1
	ld (vec_in_game),a
	call game
	call MUSIC_Stop		; как internal_loop оригинала: музыку стоп, «нажми огонь» (кроме attract-уровня 8),
	ld a,(current_level)	; и только потом разбор player_dead. Раньше порт перезапускал контрольную
	cp 8			; точку сразу, без паузы и подсказки (2026-09-07).
	jp z,vil_attract
	call draw_gameover_string
vil_attract:
	xor a
	ld (vec_in_game),a
	ld a,(player_dead)
	cp 2			; СТОП или attract -> главное меню (как game_loop оригинала)
	jp z,vec_to_menu
	cp 3			; скрипт «finish level»: current_level уже увеличен
	jp z,vec_next_level
	cp 4
	jp z,vec_to_menu	; игра пройдена — пока в меню (финал ещё не сделан)
	xor a
	ld (player_dead),a
	jp vec_internal_loop

; Переход на следующий уровень: набор читается с дискеты заново. Загрузчик в ROM одноразовый — он
; лежит по $7E00 поверх таблиц rev256/vec_slot_tab и затирается ими при старте, поэтому сначала
; возвращаем его копию из набора (build_edd.FDDCOPY), а после загрузки строим таблицы заново.
vec_next_level:
	xor a
	ld (player_dead),a
	call vec_reload_set
	jp vec_begin_level

; Перечитать набор уровня (номер в current_level) с дискеты: вернуть загрузчик на своё место
; поверх таблиц, отдать ему таблицу дорожек и заново построить всё, что затирается загрузкой.
vec_reload_set:
	di
	ld a,LEVELTAB_PORT
	out (KV_PORT),a
	ld hl,FDDCOPY
	ld de,rev256
	ld bc,512
	call z_ldir
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ei
	ld hl,vec_dirtab	; вернуть таблицу дорожек: в копии из набора она нулевая
	ld de,vfl_dirtab
	ld bc,16
	call z_ldir
	call vfl_go		; загрузка без проверки маркера: набор в квазидиске уже чужой
	call vec_init_rev256
	call vec_slot_init
	call vec_load_leveltab
	jp cls			; VRAM была буфером загрузки — иначе по краям поля остаётся мусор
; Возврат в меню: набор уровня 1 читается заново, потому что оверлей меню, его песни и резной
; шрифт лежат ТОЛЬКО в нём — на уровнях 2+ это место отдано банкам спрайтов.
vec_to_menu:
	xor a
	ld (player_dead),a
	ld (current_level),a
	call vec_reload_set
	call vec_menu_phase
	jp vec_begin_level

; таблица разворота байта (для зеркальных спрайтов), выровнена на страницу
; Таблицы уровня из квазидиска в ОЗУ. Раньше они были константами в ROM, и после смены набора
; движок читал спрайты по адресам ТОГО уровня, при котором собирали образ.
vec_load_leveltab:
	di			; прерывание играет музыку из своего окна и сбило бы наше
	ld a,LEVELTAB_PORT
	out (KV_PORT),a
	ld hl,LEVELTAB
	ld de,vec_palette
	ld bc,LEVELTAB_LEN
	call z_ldir
	ld hl,ZPSRC		; зеркальный двухплоскостной блит -> нулевая страница (zp_blit2m.asm)
	ld de,ZP_BLIT2M
	ld bc,ZP_LEN
	call z_ldir
	xor a
	out (KV_PORT),a
	ld (vec_kv_shadow),a
	ld a,1
	ld (vec_pal_dirty),a
	ei			; двухплоскостной блит и палитра экрана переехали в образ (vec_blit2.asm):
	ret			; $7F00 нужен под таблицу слотов — пул работает на всех уровнях

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
; Фаза паузы (H в игре): оверлей $9000 в окне квазидиска. Блоб в string_area недоступен —
; там строки уровня, поэтому переходник к функциям движка живёт здесь, в ROM.
vec_pause_phase:
	di
	ld a,$43
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	call $9000
	di
	xor a
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	ret

; vec_ovl_call: вызвать функцию движка (адрес в vec_ovl_tgt) при ЗАКРЫТОМ окне и вернуть окно оверлея.
; A/BC/DE/HL проходят насквозь — это параметры вызываемой функции.
vec_ovl_call:
	push af
	di
	xor a
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	pop af
	call vec_ovl_go
	push af
	di
	ld a,$43
	out ($10),a
	ld (vec_kv_shadow),a
	ei
	pop af
	ret
vec_ovl_go:
	push hl
	ld hl,(vec_ovl_tgt)
	ex (sp),hl
	ret

; Фаза меню: блоб порт-примитивов из стр.3 $9800 -> string_area, оверлей $8440 в окне b6 (порт $43)
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
