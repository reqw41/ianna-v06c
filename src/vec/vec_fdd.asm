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
	call vfl_restore
	call vfl_seek		; B шагов внутрь
	call vfl_fill		; первый сектор -> буфер
	ld hl,FDD_TAB		; таблица длин блоков
	ld bc,64
	call vfl_stream
	call vfl_bar_init	; полоса прогресса: шрифта при первой загрузке ещё нет, поэтому просто полоса
	xor a
	ld (vfl_blk),a
vfl_block:
	call vfl_bar		; закрасить колонку, соответствующую номеру блока
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
	ld a,KV_WIN_MUSIC	; маркер: набор загружен
	out (KV_PORT),a
	ld a,'I'
	ld (FDD_MARK),a
	ld a,'A'
	ld (FDD_MARK+1),a
vfl_done:
	xor a
	out (KV_PORT),a
	ret


; --- полоса прогресса загрузки ---
; VRAM на время загрузки — буфер (сжатый блок в $8000, распаковка в $C000), поэтому экран гасим
; палитрой (всё чёрное, кроме цвета 1), а полосу рисуем в плоскости младшего бита ($E000-$FFFF):
; её загрузка не трогает, значит видна только полоса.
VFL_BAR_L	equ 130
vfl_bar_init:
	call vfl_pal		; палитра защёлкивается только в кадровом гасящем, поэтому пишем
	ld hl,$E000		; её ещё и на каждом блоке (см. vfl_bar) — какая-то запись попадёт
	ld b,0
	ld c,32
vfb_clr0:
	ld (hl),0
	inc hl
	dec b
	jp nz,vfb_clr0
	dec c
	jp nz,vfb_clr0
	ret

vfl_pal:
	ld c,0
vfb_pal:
	ld a,c
	out ($02),a
	ld a,c
	dec a
	ld a,0
	jp nz,vfb_p2
	ld a,$FF		; цвет 1 — белый
vfb_p2:
	out ($0C),a
	out ($0C),a
	out ($0C),a
	inc c
	ld a,c
	cp 16
	jp nz,vfb_pal
	ret

vfl_bar:
	call vfl_pal		; повторяем установку палитры: одна из записей попадёт в гасящий
	ld a,(vfl_blk)
	add a,$E0
	ld h,a
	ld l,VFL_BAR_L
	ld c,8
vfb_fill:
	ld (hl),$FF
	dec l
	dec c
	jp nz,vfb_fill
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
	ret

vfl_ctl:
	ld a,(vec_fdd_ctl)
	out ($1C),a
	in a,($1B)
	rrca
	jp c,vfl_ctl
	ld a,(vec_fdd_ctl)
	ret
vfl_wait:
	in a,($1B)
	rrca
	jp c,vfl_wait
	ret

vfl_blk:	db 0
; дорожка начала набора для уровней 1..16 (индекс = current_level); 0 = набора нет.
; Прошивает build_fdd.py по адресу из листинга — дорожку не приходится читать с дискеты.
vfl_dirtab:	ds 16
