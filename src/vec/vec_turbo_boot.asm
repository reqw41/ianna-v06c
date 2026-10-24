;;; vec_turbo_boot.asm — одноразовый код старта для Вектора Турбо+; подставляется в string_area (build_vec.py).
; ---- Определить Турбо+ один раз при старте и выставить порты ----
; Код лежит в string_area (образ грузится целиком, а string_area до меню не нужна): в резиденте до
; $6A00 места нет. vec_start зовёт его первым делом.
; Порт 45h: б7 = 1 только во время кадрового импульса. На Турбо+ за 16К опросов (4..16 кадров при
; 3..12 МГц) бывает 1..16 фронтов 0 -> 1; на Векторе-06Ц порт 45h отвечает постоянным значением
; (0 фронтов), мусор пустой шины дал бы сотни — тогда порты не трогаем.
; На Турбо+: 40h = 41h = 0 — без подмены памяти (CP/M оставляет 40h = 87h: E000..FFFF уходят в СОЗУ);
; 46h = 0 — запись в ОЗУ без маски и сигналы STACK/RET включены (без них стековый режим квазидиска
; не работает вовсе); 43h = 0Fh — экран 256x256; 42h = 60h — окно квазидиска порта 10h = A000..DFFF (CP/M оставляет F0h,
; окно было бы 8000..FFFF). 44h (частота) не трогаем: её выбирают в загрузчике ПЗУ или ключом CP/M.
; Порты 40h..43h пишутся ДО первой записи в порт 10h: «побеждает последняя запись», дальше режим 10h.
turbo_init:
	ld de,$4000
	in a,($45)
	and $80
	ld b,a			; B — прошлое значение б7
	ld c,0			; C — число фронтов 0 -> 1
ti_lp:
	in a,($45)
	and $80
	cp b
	jp z,ti_0
	ld b,a
	or a
	jp z,ti_0		; фронт 1 -> 0
	inc c
	jp nz,ti_0
	dec c
ti_0:
	dec de
	ld a,d
	or e
	jp nz,ti_lp
	ld a,c
	or a
	ret z			; б7 не меняется — Вектор-06Ц
	cp 33
	ret nc			; слишком часто — мусор шины, не кадровый импульс
	xor a
	out ($40),a
	out ($41),a
	out ($46),a		; маска записи 0 и включить STACK/RET (их выключает запись в 47h — расширенное видео CP/M)
	ld a,$0F
	out ($43),a
	ld a,$60
	out ($42),a
	ld a,$F5		; push af вместо ret: vec_kv42 начинает выставлять маску 42h
	ld (vec_kv42),a
	; Вывод в пул и сброс пула на Турбо+ — под DI (docs/TURBO.md, «Стековый режим»): на Турбо+ адрес
	; возврата прерывания и call/ret в стековом режиме идут в обычную память, а не в квазидиск. Поэтому
	; ei и halt внутри стекового режима -> nop, call vec_phase в стековом режиме -> xor a («успеваем»),
	; а пороги фазы перед входом ниже: DI-участок на 12 МГц должен кончиться до прерывания кадра.
	ld hl,tp_tab
tp_lp:
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld a,d
	or e
	jp z,tp_done
	ld a,(hl)
	inc hl
	ld (de),a
	jp tp_lp
tp_done:
	xor a
	out ($44),a		; 12 МГц (биты 7..6 — замедление), сдвиг строки 0: темп игры держит frames_lock
	ld a,1
	ld (vec_turbo),a
	ret

; ---- Одноразовая часть vec_start: вектор RST7, ППИ, джойстик, обнуление ячеек. Перенесена сюда из
; резидента ради места; turbo_init — первым, до первой записи в порт 10h.
vec_boot_init:
	ld a,$D3		; rst 1 ($0008): out ($10),a / jp vec_kv42 — запись порта 10h с маской 42h для Турбо+
	ld ($0008),a
	ld a,$10
	ld ($0009),a
	ld a,$C3
	ld ($000A),a
	ld hl,vec_kv42
	ld ($000B),hl
	call turbo_init
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
	xor a
	out (KV_PORT),a		; квазидиск выкл
	ld (current_level),a	; уровень 1: загрузчик читает эту ячейку (инициализация ниже — уже поздно)
	ld (vec_cheat),a	; читы выключены (ячейки в зазоре ROM, начальное значение не задано)
	ld (vec_god),a
	ld (vec_ckprev),a
	ld (vec_ckeys),a
	ld (music_playing),a	; в образе здесь $FF (ds): прерывание звало плеер всю загрузку набора, ещё до
				; MUSIC_Init. Пока плеер жил в ROM, он «играл» незагруженную страницу 3 (в эмуляторах
				; там нули, на MiSTer — остатки прошлой игры); плеер-оверлей при этом ещё не загружен
	; Заставка стартовой загрузки (vec_bootload.asm, vec_lscreen.asm) — только если квазидиск пуст (маркер
	; 'IA' ставит загрузчик): иначе грузить нечего (стенды, Emu80 с готовым квазидиском).
	ld a,KV_WIN_MUSIC
	out (KV_PORT),a
	ld hl,(FDD_MARK)
	xor a
	out (KV_PORT),a
	ld a,l
	cp 'I'
	jp nz,vbi_prog
	ld a,h
	cp 'A'
	ret z
vbi_prog:
	; Заставка загрузки: полноцветная обложка, набор грузится мимо экрана (vec_bootload.asm).
	call vfl_ready		; дискеты нет — как раньше
	ret nz
	ld hl,vec_palette	; пока обложка читается — экран чёрный
	ld b,16
vbi_blk:
	ld (hl),0
	inc hl
	dec b
	jp nz,vbi_blk
	ld a,1
	ld (vec_pal_dirty),a
	xor a
	ld (vst_cls),a		; vec_start: call cls -> nop: заставка стоит до «НАЖМИ ПРОБЕЛ» (стирает оверлей)
	ld (vst_cls+1),a
	ld (vst_cls+2),a
	ld (vlt_dirty),a	; vec_load_leveltab: ld (vec_pal_dirty),a -> nop — палитра уровня ложится в
	ld (vlt_dirty+1),a	; vec_palette, но на экран не идёт до меню (оверлей вернёт команду; по нулю
	ld (vlt_dirty+2),a	; здесь он и узнаёт, что заставка была)
	ld hl,bl_load
	ld (vst_load+1),hl	; vec_start: call vec_fdd_load -> call bl_load (набор мимо экрана)
	jp bl_cover		; обложка; буфер сектора — это место нашего же кода, поэтому прыжок, а не вызов

; Заплатки для Турбо+: адрес, новый байт. «Герой позади луча» на Турбо+ выключен: его проверки зовутся
; call в стековом режиме, а на 12 МГц сброс вчетверо короче и разрыв меньше. ei/halt -> nop (00), call vec_phase -> xor a, nop, nop; пороги фазы.
tp_tab:
	dw dtb_ei
	db 0
	dw dbk_ei
	db 0
	dw dfb_ei
	db 0
	dw tp_dsp_ei
	db 0
	dw tp_dsptg_ei
	db 0
	dw dspm_ei
	db 0
	dw dsp_tg_w
	db 0
	dw dsp_lg_w
	db 0
	dw tp_vpf_ei
	db 0
	dw tp_vps_h
	db 0
	dw tp_vpff_h
	db 0
	dw tp_vps_call
	db $AF
	dw tp_vps_call+1
	db 0
	dw tp_vps_call+2
	db 0
	dw tp_vpff_call
	db $AF
	dw tp_vpff_call+1
	db 0
	dw tp_vpff_call+2
	db 0
	dw tp_vee_cp+1
	db 200
	dw tp_vpf_cp+1
	db 150
	dw tp_b128_ei
	db 0
	dw tp_b64l_ei
	db 0
	dw tp_b64r_ei
	db 0
	dw tp_vxn_call
	db $AF
	dw tp_vxn_call+1
	db 0
	dw tp_vxn_call+2
	db 0
	dw tp_hrw_ph
	db 0
	dw tp_hrw_ph+1
	db 0
	dw tp_hrw_ph+2
	db 0
	dw tp_hrw_fit
	db $3E
	dw tp_hrw_fit+1
	db 1
	dw tp_hrw_fit+2
	db 0
	dw tp_sr_lvl
	db $CF
	dw tp_sr_lvl+1
	db 0
	dw tp_sr_mus
	db $CF
	dw tp_sr_mus+1
	db 0
	dw tp_sr_cls
	db $CF
	dw tp_sr_cls+1
	db 0
	dw 0
