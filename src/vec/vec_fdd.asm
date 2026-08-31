; vec_fdd.asm — стадия 2 загрузки с дискеты: EDD (256К, дорожки 4..29) -> квазидиск.
; Портовая карта Вектора (инверсия адресов ВГ93): $1B=команда/статус, $1A=трек, $19=сектор, $18=данные,
; $1C=управление (бит2 = сторона, инвертированная; $34/$30 как в штатном загрузчике).
; Протокол списан со штатного ПЗУ (loader.rom $02DB..): выбор/ожидание, RESTORE, чтение сектора ($80),
; шаг на трек ($58). Геометрия: 5 секторов по 1024 на сторону.
; Вызов: vec_fdd_load — если в квазидиске нет маркера 'IA' (страница 3, $C800) — читает 256 секторов.
FDD_MARK	equ $C800	; страница 3, свободное место перед музыкой
FDD_TRACK0	equ 4		; EDD начинается с дорожки 4 (raw 40960)

vec_fdd_load:
	; маркер уже есть (квазидиск загружен стендом/эмулятором) — выходим
	ld a,KV_WIN_MUSIC	; окно $A000-$DFFF -> страница 3
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
	ld a,$34
	ld (vec_fdd_ctl),a
	call vfl_ctl		; выбрать дисковод/сторону, дождаться готовности
	xor a
	out ($1B),a		; RESTORE (на дорожку 0)
	call vfl_wait
	; дойти до дорожки FDD_TRACK0 шагами
	ld b,FDD_TRACK0
vfl_seek:
	ld a,$58
	out ($1B),a		; STEP-IN с обновлением трека
	call vfl_wait
	dec b
	jp nz,vfl_seek
	; 256 секторов = 256К: страницы квазидиска 0..3
	ld c,0			; страница
vfl_page:
	ld a,c
	rlca
	rlca			; биты 2-3 = страница стека
	or $10			; стековый режим
	ld (vec_fdd_kv),a
	ld hl,0			; адрес внутри страницы
	ld (vec_fdd_dst),hl
	ld b,64			; 64 сектора на страницу
vfl_sec:
	push bc
	; прочитать сектор (номер в vec_fdd_sec) в буфер string_area
	ld a,(vec_fdd_sec)
	ld c,a
	ld hl,string_area
	call vfl_read
	jp nz,vfl_go		; ошибка — начать сначала
	; буфер -> квазидиск стековым режимом (1024 Б = 512 push)
	ld hl,0
	add hl,sp
	ld (vec_fdd_sp),hl
	ld hl,(vec_fdd_dst)
	ld de,1024
	add hl,de
	ld (vec_fdd_dst),hl	; конец блока = стартовый SP (push пишет вниз)
	di
	ld a,(vec_fdd_kv)
	out (KV_PORT),a
	ld sp,hl
	ld hl,string_area+1023
	ld c,0			; счётчик пар (256 x 2 push = 1024 Б? нет: 512 push) — двумя вложенными
	ld b,2
vfl_push:
	ld d,(hl)
	dec hl
	ld e,(hl)
	dec hl
	push de
	dec c
	jp nz,vfl_push
	dec b
	jp nz,vfl_push
	xor a
	out (KV_PORT),a
	ld hl,(vec_fdd_sp)
	ld sp,hl
	ei
	; следующий сектор: 1..5 сторона 0, затем 1..5 сторона 1, затем шаг трека
	ld a,(vec_fdd_sec)
	inc a
	ld (vec_fdd_sec),a
	cp 6
	jp nz,vfl_next
	ld a,1
	ld (vec_fdd_sec),a
	ld a,(vec_fdd_ctl)
	xor 4			; смена стороны
	ld (vec_fdd_ctl),a
	call vfl_ctl
	and 4
	jp z,vfl_next		; перешли на сторону 1 — трек тот же
	ld a,$58
	out ($1B),a		; обе стороны прочитаны — шаг на следующий трек
	call vfl_wait
vfl_next:
	pop bc
	dec b
	jp nz,vfl_sec
	inc c
	ld a,c
	cp 4
	jp nz,vfl_page
vfl_done:
	xor a
	out (KV_PORT),a
	ret

; чтение одного сектора C -> (HL); Z = успех (как sub_0366 ПЗУ)
vfl_read:
	call vfl_ctl
	ld a,c
	out ($19),a
	ld de,$0103
	ld a,$80
	out ($1B),a
vfr_busy:
	in a,($1B)
	rrca
	jp nc,vfr_busy
vfr_drq:
	in a,($1B)
	and e
	sub d
	jp z,vfr_drq
	in a,($18)
	ld (hl),a
	inc hl
	jp p,vfr_drq
	dec hl
	in a,($1B)
	and $9C
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
