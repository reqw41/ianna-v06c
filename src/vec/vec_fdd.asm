; vec_fdd.asm — загрузка набора уровня с дискеты в квазидиск.
; Живёт в ОБРАЗЕ ROM поверх области rev256/vec_slot_tab ($7E00-$7FFF): исполняется при старте,
; ДО того как эти таблицы заполняются, после чего затирается ими.
; Портовая карта Вектора (инверсия адресов ВГ93): $1B=команда/статус, $1A=трек, $19=сектор,
; $18=данные, $1C=управление (бит2 = сторона). Геометрия 80x2x5x1024.
;
; Набор уровня лежит на дискете СЖАТЫМ (aPLib, блоками по 8К): сырых 256К туда влезает ровно один,
; а сжатых (78 и 64 КБ) помещаются все девять. Файл уровня: [32 слова длин блоков][блоки подряд];
; длина 0 = блок целиком нулевой. Блок i идёт в страницу i/8 квазидиска по смещению (i%8)*8192.
; Распаковщик aPLib берём готовый из движка (depack: HL = источник, DE = приёмник).
;
; Дорожку уровня НЕ читаем с дискеты: таблицу vfl_dirtab прошивает в образ build_fdd.py, поэтому
; позиционирование ровно одно (RESTORE + шаги) — как в рабочем чтении экрана меню из блоба.
FDD_MARK	equ $C800	; страница 3: маркер 'IA' — квазидиск уже заполнен стендом/эмулятором
FDD_BUF		equ string_area		; буфер сектора (1К)
FDD_TAB		equ string_area+1024	; таблица длин блоков (64 Б)
FDD_UNPACK	equ $C000	; куда распаковывать блок (VRAM: экран при загрузке не нужен)
FDD_SRC		equ $8000	; куда читать сжатый блок (VRAM, вне окна квазидиска $A000-$DFFF)
KV_WIN_BANKS	equ $63		; окно $8000-$9FFF, страница 3: там лежит загрузчик банков
; FDD_BANKCODE (его адрес в наборе) приходит из gen_data.asm — раскладка страницы 3 задана
; в build_edd (PAUSE_ADDR/FDD_BANKCODE/WPN_SRC), чтобы адрес не расходился с укладчиком набора.

vec_fdd_load:
	ld a,KV_WIN_MUSIC	; маркер уже есть — квазидиск заполнен снаружи, читать нечего
	out (KV_PORT),a
	ld a,(FDD_MARK)
	cp 'I'
	jp nz,vfl_go
	ld a,(FDD_MARK+1)
	cp 'A'
	jp z,vfl_done
vfl_go:
	; Готов ли дисковод? Бит 7 статуса ВГ93 = NOT READY (нет дискеты/привода). Без этой проверки
	; запуск «ПЗУ + квазидиск» без дискеты (Emu80, стенды) на любом перечитывании набора читал
	; $FF вместо данных, распаковывал мусор в квазидиск и вешал машину (жалоба 2026-09-08).
	; Эхо регистра сектора для этого не годится: контроллер отвечает и без дискеты.
	call vfl_ready		; vec_turbo.asm: FORCE INTERRUPT и ожидание READY
	jp nz,vfl_done		; дискеты нет — набор в квазидиске уже загружен, читать нечего
	xor a
	out (KV_PORT),a
	ld a,(current_level)	; 0 = уровень 1 (vec_main обнуляет ячейку до вызова)
	ld e,a
	ld d,0
	ld hl,vfl_dirtab
	add hl,de
	ld a,(hl)
	or a
	jp z,vfl_done		; дорожка 0 = набора на дискете нет
	ld b,a			; B = дорожка уровня
	ld a,$34
	ld (vec_fdd_ctl),a
	ld a,1
	ld (vec_fdd_sec),a
	call vfl_pal		; экран гасим ДО первого чтения: на нём ещё заставка загрузчика или прошлый уровень
	call vfl_restore
	call vfl_seek		; B шагов внутрь
	call vfl_fill		; первый сектор -> буфер
	ld hl,FDD_TAB		; таблица длин блоков, за ней рецепт банков (см. fdd_banks.asm)
	ld bc,64+128
	call vfl_stream
	xor a
	ld (vfl_blk),a
vfl_block:
	ld a,(vfl_blk)
	add a,a
	ld e,a
	ld d,0
	ld hl,FDD_TAB
	add hl,de
	ld c,(hl)
	inc hl
	ld b,(hl)		; BC = длина сжатого блока
	ld a,b
	or c
	jp z,vfl_next		; нулевой блок — в квазидиске и так нули
	ld hl,FDD_SRC
	call vfl_stream		; сжатый блок целиком
	ld hl,FDD_SRC
	ld de,FDD_UNPACK
	call depack		; -> 8К в VRAM $C000
	call vfl_store		; -> квазидиск
vfl_next:
	ld a,(vfl_blk)
	inc a
	ld (vfl_blk),a
	cp 32
	jp nz,vfl_block
	; Банки спрайтов лежат на дискете отдельной библиотекой — по одному разу, а не в каждом
	; наборе. Кладёт их по местам код из набора (стр.3 $9280): копируем его в string_area
	; (строки уровня попадут туда позже) и зовём — примитивы этого загрузчика ему ещё доступны.
	di				; ISR играет музыку из своего окна и вернул бы ТЕНЬ порта,
	ld a,KV_WIN_BANKS		; закрыв наше окно посреди копирования — держим прерывания
	rst 1			; out (KV_PORT),a + маска 42h на Турбо+ (vec_kv42)
	ld hl,FDD_BANKCODE
	ld de,string_area+1216		; за буфером сектора (1К), таблицей длин и рецептом
	ld bc,512
	call z_ldir
	xor a
	rst 1			; out (KV_PORT),a + маска 42h на Турбо+ (vec_kv42)
	ei
	call string_area+1216
	ld a,KV_WIN_MUSIC	; маркер: набор загружен
	rst 1			; out (KV_PORT),a + маска 42h на Турбо+ (vec_kv42)
	ld a,'I'
	ld (FDD_MARK),a
	ld a,'A'
	ld (FDD_MARK+1),a
vfl_done:
	xor a
	rst 1			; out (KV_PORT),a + маска 42h на Турбо+ (vec_kv42)
	ret


; --- экран на время загрузки ---
; VRAM при загрузке — буфер (сжатый блок в $8000, распаковка в $C000), поэтому экран гасим палитрой
; ЦЕЛИКОМ. Раньше цвет 1 оставался белым под полосу прогресса; полосы давно нет, а сжатые данные в
; плоскости $E000 светились белым мусором в левой части экрана (жалоба 2026-10-13).
vfl_pal:			; через прерывание: палитра Вектора пишется верно только на бордюре/гашении,
	ld hl,vec_palette	; а запись посреди кадра попадает в тот цвет, что сейчас под лучом
	ld c,16			; (B занят: в нём дорожка уровня для vfl_seek)
	xor a
vfb_pal:
	ld (hl),a
	inc hl
	dec c
	jp nz,vfb_pal
	inc a
	ld (vec_pal_dirty),a
	ei
	halt
	ret

; --- блок 8К из VRAM $C000 в квазидиск: страница blk/8, смещение (blk%8)*8192 ---
vfl_store:
	ld a,(vfl_blk)
	rrca
	rrca
	rrca
	and 3
	rlca
	rlca			; биты 2-3 порта = страница
	or $10			; стековый режим
	ld (vec_fdd_kv),a
	ld a,(vfl_blk)
	and 7
	rrca
	rrca
	rrca
	and $E0
	add a,$20		; конец блока: push пишет вниз
	ld h,a
	ld l,0
	di
	ld (vec_fdd_dst),hl
	ld hl,0
	add hl,sp
	ld (vec_fdd_sp),hl
	ld hl,(vec_fdd_dst)
	ld sp,hl
	ld a,(vec_fdd_kv)
	out (KV_PORT),a
	ld hl,FDD_UNPACK+8191
	ld b,0
	ld c,16			; 16 x 256 пар = 8192 байта
vfl_push:
	ld d,(hl)
	dec hl
	ld e,(hl)
	dec hl
	push de
	dec b
	jp nz,vfl_push
	dec c
	jp nz,vfl_push
	xor a
	out (KV_PORT),a
	ld hl,(vec_fdd_sp)
	ld sp,hl
	ei
	ret

; --- поток байтов с дискеты ---
vfl_fill:
	ld a,(vec_fdd_sec)
	ld c,a
	ld hl,FDD_BUF
	call vfl_read
	ld hl,FDD_BUF
	ld (vec_fdd_ptr),hl
	ld a,(vec_fdd_sec)	; 1..5 сторона 0, затем 1..5 сторона 1, затем следующая дорожка
	inc a
	ld (vec_fdd_sec),a
	cp 6
	ret nz
	ld a,1
	ld (vec_fdd_sec),a
	ld a,(vec_fdd_ctl)
	xor 4
	ld (vec_fdd_ctl),a
	call vfl_ctl
	and 4
	ret z			; перешли на сторону 1 — дорожка та же
	ld a,$58
	out ($1B),a		; обе стороны прочитаны — шаг на следующую дорожку
	jp vfl_wait

; Поток с дискеты: HL = приёмник, BC = сколько байт. Копируем из буфера сектора напрямую —
; на байт уходит ~25 тактов вместо ~65, а набор уровня это 80 КБ.
vfl_stream:
	push hl
	ld hl,(vec_fdd_ptr)
	ex de,hl		; DE = указатель в буфере сектора
	pop hl
vfl_st1:
	ld a,d
	cp 0+((FDD_BUF+1024)>>8)
	jp nz,vfl_st2
	ld a,e
	cp 0+((FDD_BUF+1024)&255)
	jp nz,vfl_st2
	push hl			; буфер кончился — читаем следующий сектор
	push bc
	call vfl_fill
	pop bc
	pop hl
	push hl
	ld hl,(vec_fdd_ptr)
	ex de,hl
	pop hl
vfl_st2:
	ld a,(de)
	inc de
	ld (hl),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,vfl_st1
	ex de,hl		; вернуть указатель на место
	ld (vec_fdd_ptr),hl
	ret

; --- примитивы ВГ93 (как в рабочем блоб-загрузчике экрана меню) ---
vfl_restore:
	call vfl_ctl
	xor a
	out ($1B),a		; RESTORE (на дорожку 0)
	jp vfl_wait
vfl_seek:			; B = сколько шагов внутрь
	ld a,b
	or a
	ret z
vfl_sk1:
	ld a,$58
	out ($1B),a		; STEP-IN с обновлением трека
	call vfl_wait
	dec b
	jp nz,vfl_sk1
	ret

; чтение сектора C -> (HL), ровно 1024 байта; Z = успех.
; Байты считаем счётчиком, а не «по флагам DRQ» (трюк ПЗУ): при неснятом DRQ такой цикл крутится,
; пока адрес не переполнится, и затирает всю память.
vfl_read:
	; Сектор принимаем под DI: байт стоит в регистре данных ВГ93 32 мкс (~96 тактов), а прерывание
	; кадра с плеером — тысячи тактов; с EI в каждом секторе терялись байты (на MiSTer загрузка
	; уровня висла на чёрном экране, 2026-10-12; эмуляторы отдают байты без срока и этого не видят).
	; Один сектор — 1,6 кадра, так что плеер пропускает одно-два прерывания на сектор.
	di
	call vfl_ctl
	ld a,c
	out ($19),a
	ld a,$80
	out ($1B),a
	ld b,0
	ld c,4			; 4 x 256 = 1024
vfr_busy:
	in a,($1B)
	rrca
	jp nc,vfr_busy		; ждём BUSY
vfr_drq:
	in a,($1B)
	rrca			; бит 0 (BUSY) -> CY
	jp nc,vfr_end		; операция кончилась раньше
	rrca			; бит 1 (DRQ) -> CY
	jp nc,vfr_drq
	in a,($18)
	ld (hl),a
	inc hl
	dec b
	jp nz,vfr_drq
	dec c
	jp nz,vfr_drq
vfr_end:
	in a,($1B)
	rrca
	jp c,vfr_end		; дождаться снятия BUSY
	in a,($1B)
	and $9C			; ошибки чтения
	ei
	ret

; vfl_ctl — в резиденте (vec_turbo.asm)
; Готов ли дисковод: NZ = NOT READY (нет дискеты или привода). FORCE INTERRUPT (D0h) переводит статус
; в тип I, где бит 7 — линия READY привода; готовности ждём (мотор после простоя раскручивается, на
; Турбо+ после CP/M — так же, как у Tony).
vfl_ready:
	call vfl_ctl
	ld a,$D0
	out ($1B),a
	ld a,$80
	call vfl_waitm
	in a,($1B)
	and $80
	ret
; Ожидание конца команды типа I (RESTORE, STEP) со СЧЁТЧИКОМ: без него сбой контроллера или
; отсутствие дискеты вешали машину намертво. Сначала пауза: ВГ93 поднимает BUSY не сразу, и на 12 МГц
; опрос сразу за командой видел «свободен» — следующая команда терялась (ошибка из порта Tony).
; Счётчик 4 x 65536: ~4 с на 3 МГц и ~1 с на 12 МГц (RESTORE с дальней дорожки идёт до 0,5 с).
vfl_wait:
	ld a,1			; бит 0 статуса — BUSY
vfl_waitm:			; A = маска «ещё ждём»
	push bc
	push de
	ld e,a
	ld a,40
vfw_p:
	dec a
	jp nz,vfw_p
	ld d,4
	ld bc,0
vfl_w1:
	in a,($1B)
	and e
	jp z,vfl_w_ok
	dec bc
	ld a,b
	or c
	jp nz,vfl_w1
	dec d
	jp nz,vfl_w1
vfl_w_ok:
	pop de
	pop bc
	ret

vfl_blk:	db 0
; дорожка начала набора для уровней 1..16 (индекс = current_level); 0 = набора нет.
; Прошивает build_fdd.py по адресу из листинга — дорожку не приходится читать с дискеты.
; $7FF0 = vec_kb_ph (vec_slot_tab+240): прерывание прибавляет к ней единицу каждый кадр и во время
; загрузки — байт под ней загрузчику не принадлежит. Таблица дорожек — строго за ним (24.10: при
; таблице на $7FEF её второй элемент рос, и смена уровня читала набор не с той дорожки).
	ds $7FF0 - $		; код загрузчика обязан кончиться до $7FF0 (иначе ассемблер даст ошибку)
vfl_kbpad:	db 0		; $7FF0 — место vec_kb_ph
vfl_dirtab:	ds 10
