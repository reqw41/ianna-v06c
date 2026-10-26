; vec_main.asm — инициализация и главный цикл теста (Вектор-06Ц).
; Вектор прерывания RST7 ($0038) прописываем сами.

vec_start:
	di
	ld sp,vec_stack_top
    if DEMO
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
	ld a,$83		; ВВ55 №2 — джойстик «П» (как в ядре MiSTer, Vector-06C.sv joyP): оба устройства
	out (PPI2_CW),a
	ld a,$9F
	out (PPI2_C),a
	in a,(PPI2_A)		; покой: нажатием дальше считается отклонение от него (без джойстика
	ld (joy_idle),a		; порт читается константой — $FF или мусор шины)
    else
	call vec_boot_init	; одноразовая часть старта — в string_area (vec_turbo_boot.asm)
    endif
    if !DEMO
vst_load:			; при заставке загрузки vec_boot_init ставит сюда bl_load (vec_bootload.asm)
	call vec_fdd_load	; загрузка с дискеты, если квазидиск пуст (маркер 'IA' в стр.3 $C800)
	ld hl,vfl_dirtab	; таблицу дорожек уровней прошивает build_fdd прямо в образ ROM, а в
	ld de,vec_dirtab	; копии загрузчика внутри набора она нулевая — сохраняем, пока цела
	ld bc,10		; уровни 1..8 и секретный (индекс 9)
	call z_ldir
	call vec_load_leveltab	; палитра, банки спрайтов и передние тайлы — из набора уровня
    endif
vst_cls:			; после заставки загрузки здесь nop (vec_boot_init): экран стирает оверлей меню
	call cls
	call vec_init_rev256
    if !DEMO
	call vec_slot_init	; таблица слотов пула = $FF (пул работает на всех уровнях)
	call isr_idx_init
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
	ld (vec_end_flag),a
	ei
    if !DEMO
	call vec_menu_phase	; меню/интро (оверлей в окне квазидиска; без дисковода — сразу игра)
	ld a,(current_level)	; пароль выбрал не первый уровень: в квазидиске набор первого — перечитать
	or a			; набор с дискеты (как при смене уровня)
	call nz,vec_reload_set
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
	cp 2			; X в паузе или attract -> главное меню (как game_loop оригинала)
	jp z,vec_to_menu
	cp 3			; скрипт «finish level»: current_level уже увеличен
	jp z,vec_next_level
	cp 4
	jp z,vec_to_ending	; игра пройдена (end_game оригинала)
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
	call MUSIC_Stop		; плеер и песня лежат в странице 3, которую сейчас перезапишет загрузка:
				; прерывание не должно звать его, пока набор не дочитан (music_playing = 0)
	di
	ld a,LEVELTAB_PORT
	out (KV_PORT),a
	ld hl,FDDCOPY
	ld de,rev256
	ld bc,512
	call z_ldir
	ld a,KV_WIN_BANKS	; полоса загрузки (lbar.asm) — из набора в хвост string_area
	rst 1
	ld hl,LB_SRC
	ld de,string_area+LB_ORG_OFS
	ld bc,LB_LEN
	call z_ldir
	xor a
	rst 1
	ld (vec_kv_shadow),a
	ei
	call string_area+LB_ORG_OFS
	ld hl,vec_dirtab	; вернуть таблицу дорожек: в копии из набора она нулевая
	ld de,vfl_dirtab
	ld bc,10
	call z_ldir
	call vfl_go		; загрузка без проверки маркера: набор в квазидиске уже чужой
	ld hl,0
	ld (vec_key_hook),hl	; снять полосу: string_area скоро займут строки уровня
	call vec_init_rev256
	call vec_slot_init
	call isr_idx_init
	call vec_load_leveltab
	jp cls			; VRAM была буфером загрузки — иначе по краям поля остаётся мусор
; Игра пройдена: та же дорога, что и в меню (набор уровня 1 с оверлеем читается заново), но с
; поднятым флагом — оверлей сперва играет концовку и титры, а потом уже открывает меню.
; Сам финал живёт в оверлее: в ROM для него места нет (до переменных 32 Б зазора).
vec_to_ending:
	ld (vec_end_flag),a	; A = 4 (player_dead)
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
vlt_dirty:			; после заставки загрузки здесь nop до входа в меню (vec_boot_init / ovl_entry)
	ld (vec_pal_dirty),a
	ei			; двухплоскостной блит и палитра экрана переехали в образ (vec_blit2.asm):
	ret			; $7F00 нужен под таблицу слотов — пул работает на всех уровнях

; Индекс таблицы починки (isr_fix_tab): для каждой половины страницы $50..$5B — адрес первой записи,
; конец диапазона которой выше начала половины. Записи идут по адресам, последняя — $FFFF.
isr_idx_init:
	ld hl,isr_fix_tab
	ld de,isr_idx
	ld bc,ISR_IDX_PAGE0*256	; BC = граница половины страницы
iii_next:
	ld a,c			; граница - конец записи: перенос = конец выше границы
	sub (hl)
	inc hl
	ld a,b
	sbc a,(hl)
	dec hl
	jp c,iii_found
	inc hl			; конец не выше — запись не нужна ни этой половине, ни следующим
	inc hl
	inc hl
	jp iii_next
iii_found:
	ld a,l
	ld (de),a
	inc e
	ld a,h
	ld (de),a
	inc e			; isr_idx не пересекает границу страницы (vec_slot_tab+192..+239)
	ld a,c
	xor $80
	ld c,a
	jp nz,iii_next
	inc b
	ld a,b
	cp ISR_IDX_PAGE0+ISR_IDX_PAGES
	jp nz,iii_next
	ret

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
	ld a,$63
	rst 1			; out ($10),a + маска 42h на Турбо+ (vec_kv42)
	ld (vec_kv_shadow),a
	ei
	call $9000
	di
	xor a
	rst 1			; out ($10),a + маска 42h на Турбо+ (vec_kv42)
	ld (vec_kv_shadow),a
	ei
	ret

; vec_ovl_call: вызвать функцию движка (адрес в vec_ovl_tgt) при ЗАКРЫТОМ окне и вернуть окно оверлея.
; A/BC/DE/HL проходят насквозь — это параметры вызываемой функции.
vec_ovl_call:
	push af
	di
	xor a
	rst 1			; out ($10),a + маска 42h на Турбо+ (vec_kv42)
	ld (vec_kv_shadow),a
	ei
	pop af
	call vec_ovl_go
	push af
	di
	ld a,$63
	rst 1			; out ($10),a + маска 42h на Турбо+ (vec_kv42)
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
; Читы: раз в тик из mainloop (build_vec ставит вызов перед проверкой паузы). Клавиши сняты в прерывании.
vec_cheat_tick:
	xor a
	ld (vec_kb_ph),a	; новый тик: ISR опросит клавиатуру на ближайшем кадре
	ld a,(vec_cheat)
	or a
	ret z
	di
	ld a,(vec_ckeys)	; нажатия, защёлкнутые прерыванием
	ld b,a
	xor a
	ld (vec_ckeys),a
	ei
	ld a,b
	rrca			; G: неуязвимость вкл/выкл
	jp nc,vct_god
	ld a,(vec_god)
	xor 1
	ld (vec_god),a
	push bc			; отметка на панели: «G» горит, пока неуязвимость включена
	ld bc,$0716
	ld a,' '
	jp z,vct_gm
	ld a,'G'
vct_gm:
	call drawChar
	pop bc
vct_god:
	ld a,(vec_god)
	or a
	jp z,vct_l
	ld a,(player_level)	; здоровье — к максимуму уровня героя (как InitPlayer)
	ld e,a
	ld d,0
	ld hl,barbarian_max_energy
	add hl,de
	ld a,(hl)
	ld (ENTITY_PLAYER_POINTER+4),a
vct_l:
	ld a,b
	and $10			; L: следующий уровень
	jp z,vct_i
	ld a,(current_level)
	cp 9			; индекс 9 — секретный уровень, дальше некуда
	jp nc,vct_i
	inc a
	cp 8			; индекс 8 — attract-демо оригинала, набора нет: с восьмого уровня — на секретный
	jp nz,vct_l1
	inc a
vct_l1:
	ld (current_level),a
	ld a,3
	ld (player_dead),a	; как скрипт finish_level: vec_main перечитает набор с дискеты
vct_i:
	ld a,b
	and $02			; I: «уровень X,Y» на панели
	ret z
	ld bc,$0116		; колонка 1, строка 22
	ld a,(current_level)
	add a,'1'
	call drawChar
	ld b,3
	ld a,(current_levelx)
	add a,'0'
	call drawChar
	inc b
	ld a,','
	call drawChar
	inc b
	ld a,(current_levely)
	add a,'0'
	jp drawChar
vec_menu_phase:
	di
	ld a,$63
	rst 1			; out ($10),a + маска 42h на Турбо+ (vec_kv42)
	ld (vec_kv_shadow),a
	ei
	call $8440		; оверлей меню (сам копирует блоб из окна в string_area)
	di
	xor a
	rst 1
	ld (vec_kv_shadow),a
	ei
	ret
    endif
