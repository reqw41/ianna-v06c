; vec_vdp.asm — платформенный слой Вектор-06Ц вместо vdp.asm MSX2.
; Интерфейс тот же, что у VDP-процедур оригинала; реализация — pop-блит
; из квазидиска (DEMO=0) или ROM (DEMO=1).
;
; Экран: MSX y -> строка Вектора y+32 -> L = 223-y; x -> H = база плоскости + (x>>3).
; Плоскости $80,$A0,$C0,$E0; палитра idx = p0<<3|p1<<2|p2<<1|p3.
;
; Порт $10: б0-1 страница окон, б2-3 страница стека, б4 стек, б5 окно $A000-$DFFF,
; б6 окно $8000-$9FFF, б7 окно $E000-$FFFF. В стековом режиме POP читает квазидиск,
; обычные записи идут в ОЗУ/VRAM. Во время стековых блитов — DI, без call/ret.
;
; РЕНДЕР БЕЗ МЕРЦАНИЯ (DEMO=0): RedrawScreen_part1 собирает dirty-супертайлы не в VRAM,
; а в ПУЛ — страница 3 квазидиска $A000-$C7FF через ОКНО (80 слотов по 128 Б, выше музыка; формат
; тайла: [p][col][row]); RedrawScreen_part2 (vec_pool_flush) выбрасывает слоты в VRAM
; стеком, строками сверху вниз. Супертайлы без слота (панель, переполнение) рисуются
; напрямую. Окно открывается только внутри буферных блитов (панель рисуется между ними).

KV_PORT		equ $10
; C8 (из vdp_consts): 1 = 8 цветов, 3 плоскости. Индекс пикселя 0..7 живёт в битах 2..0 -> VRAM
; $A000/$C000/$E000; плоскость 0 ($8000-$9FFF) свободна и НИКОГДА не пишется (палитра зеркалит бит 3).
VEC_P0H		equ $80 + C8*$20	; старший байт первой пишущейся плоскости
VEC_NPL		equ 4 - C8		; плоскостей в данных/блитах
KV_STK_P0	equ $10
KV_STK_P1	equ $14
KV_STK_P2	equ $18
KV_STK_P3	equ $1C
KV_WIN_LEVEL	equ $61		; окна $8000-$DFFF -> страница 1 (карта уровня)
KV_POOL_WIN	equ $23		; окно $A000-$DFFF -> страница 3 (пул)
KV_WIN_MUSIC	equ $23		; окно $A000-$DFFF -> страница 3 (музыка по $C980, эффекты по $D980)
POOL_BASE	equ $A000
; ГРЯЗНОЕ ПО КОЛОНКАМ (2026-10-12). Спрайт шириной 24 точки занимает три колонки по 8, а грязное
; округлялось до стайлов 16x16 — до четырёх: от пятой части до двух пятых заливки слотов и сброса их
; в экран делалось зря (tools/chain_est.py). vec_col_tab[idx] (тот же индекс, что у vec_slot_tab):
; бит 0 — нужна левая колонка стайла, бит 1 — правая; 0 = стайл чист. Ставит раздача слотов (vpb_x)
; по точным границам из InvalidateTiles (бит 7 в xs и nx записи tiles_dirty), снимает сброс пула.
; Читают: заливка слота фоном (dtb), чёрная заливка (dt_blk) и вывод слота в экран (vpf_slot).
; Ненужная колонка слота не заливается и не выводится: спрайты в неё не рисуют (у любого рисуемого
; спрайта прямоугольник инвалидирован точно), а передний тайл пишет туда мусор, который никто не видит.
; Таблица и три ячейки лежат в зазоре ROM перед переменными (сторож границы — в build_vec).
vec_col_tab	equ $6A00
vec_col_f	equ vec_col_tab+255	; флаги текущего стайла — для выбора тела блита
vec_col_l	equ vec_col_tab+254	; xs текущего прямоугольника с битом 7 (левая колонка не нужна)
vec_col_r	equ vec_col_tab+253	; nx с битом 7 (правая колонка последнего стайла не нужна)
POOL_SLOTS	equ 58		; слотов в пуле: $A000-$BCFF. Было 80 (до $C7FF); в обычной игре занято до 46
				; (tools/poolmax.py, 9 уровней), больше — только в тик смены экрана на уровнях 3 и 7,
				; там лишние стайлы идут прямым путём. Хвост $BD00-$C7FF отдан плееру Arkos (ARK_ADDR).
MIRRBUF		equ POOL_BASE + 80*128	; $C800, страница 3: буфер развёрнутой колонки спрайта (192 Б).
				; Это же место — площадка стека vec_pool_flush, но сброс идёт в другой
				; фазе тика, во время рисования спрайтов оно свободно (см. ds_dir4m).
P3_FONT		equ $0000
P3_PANEL	equ $1000
P3_WEAPON	equ $2000
P3_ONOFF	equ $2400
Y_TOP_L		equ 223

; ---------------------------------------------------------------------------
setROM2:
setROM2_DI:
	ld (ROMBank1),a
	cp 1
	jp z,setrom_close
	cp 22
	jp c,setrom_sprite
	cp MUSIC_ROM_PAGE
	jp z,setrom_music
	and 1
	ret nz
    if DEMO
	ret
    else
	ld a,KV_WIN_LEVEL
	ld (vec_kv_shadow),a
	out (KV_PORT),a
	ret
    endif
setrom_music:
    if !DEMO
	ld a,KV_WIN_MUSIC
	ld (vec_kv_shadow),a
	out (KV_PORT),a
    endif
	ret
setrom_close:
    if !DEMO
	xor a
	ld (vec_kv_shadow),a
	out (KV_PORT),a
    endif
	ret
setrom_sprite:
	ld (vec_sprite_bank),a
	ret

setDisplayPage:
CopyTile:
copyPage:
VDPcmd:
VDPcmd_DI:
waitVDP:
VDP_SetPalette:
initVDPBuffers:
unpackVRAM:
fadeMSX2:
fadeinMSX2:
	ret

cls:
	ld hl,$8000
	ld bc,$8000
cls_l:
	ld (hl),0
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,cls_l
    if !DEMO
	jp vec_pc_reset		; панели на экране нет — кэш «неизвестно»
    else
	ret
    endif

; ---------------------------------------------------------------------------
    if DEMO
; Таблица банков MSX -> (порт стека, старший байт базы) для кадров спрайтов.
; банк 2 варвар общий -> стр.0 $0000; 3 прыжки -> стр.1 $0000;
; 7 скелет, 8 орк, 9 мумия, 12 камень -> стр.2 по $4000; остальные -> стр.0 (мусор, но безопасно)
vec_bank_tab:			; кадры по 576 Б (см. build_edd.SPRITE_BANKS)
	db KV_STK_P0,$00, KV_STK_P1,$A2		; 2,3 варвар: стр.0 $0000, стр.1 $A200
	db KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00	; 4,5,6 (оружие — пока нет)
	db KV_STK_P1,$00, KV_STK_P2,$00, KV_STK_P2,$60	; 7 скелет стр.1, 8 орк стр.2, 9 мумия стр.2 $6000
	db KV_STK_P0,$00, KV_STK_P0,$00			; 10,11
	db KV_STK_P3,$28				; 12 камень стр.3 $2800
	db KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00, KV_STK_P0,$00	; 13..21
    endif			; квазидисковая сборка: vec_bank_tab генерирует build_edd.py (gen_data.asm)

; ---------------------------------------------------------------------------
; Слот пула для супертайла: B=x px, C=y px -> A = слот или $FF (панель/нет)
vec_slot_for_bc:
	ld a,c
	cp 160
	jp nc,vsf_none
	and $f0
	ld l,a
	ld a,b
	rrca
	rrca
	rrca
	rrca
	and $0f
	or l
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	ret
vsf_none:
	ld a,$ff
	ret
; A = слот -> HL = адрес в пуле ($A000 + slot*128)
vec_pool_addr:
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ret

; ---------------------------------------------------------------------------
; Общий стековый блит 128 Б «формат тайла» -> VRAM: SP уже установлен, порт выведен,
; D = H колонки 0 плоскости 0, E = L верхней строки. Возврат: jp (vec_blit_ret).
; Развёрнут ПОЛНОСТЬЮ: счётчики колонки и плоскости жили в ПАМЯТИ и стоили 64 такта на колонку
; (ld a,(nn) 16 + dec 8 + ld (nn),a 16 + jp 16) при 352 тактах полезной работы — 8 колонок тайла
; платили 512 тактов ни за что. Регистры все заняты (BC — данные, HL — приёмник, E — верхняя
; строка, SP — источник), поэтому счётчик убран вовсе: переходы колонки и плоскости — арифметика
; над H. Цена: +264 байта ROM, -820 тактов на каждый блит 128 Б.
VBCOL		macro		; колонка 16 Б: L = E .. E-15, на выходе H+1, L = E-15
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	inc h
	endm
DBV8		macro		; 16 нулевых байт в VRAM вниз по L (dt_blk_plain); BC = 0
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	endm
DFTB8		macro		; 8 Б переднего тайла в слот: пары (данные, маска) из стека, «прочитать-и-или»
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	inc hl
	endm
DTB16		macro		; 16 Б в слот пула по возрастанию
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	pop bc
	ld (hl),c
	inc hl
	ld (hl),b
	inc hl
	endm
VBPLANE		macro		; после колонки 1 H = база+2, следующая плоскость = база+$20
	ld a,h
	add a,$1e
	ld h,a
	ld l,e
	endm

vec_blit128_vram:		; C8: 96 Б (3 плоскости)
	ld h,d
	ld l,e
vb_col:				; метка для профиля (tools/blit_model.py): всё развёрнутое тело
	VBCOL			; плоскость 0, колонка 0
	ld l,e
	VBCOL			; плоскость 0, колонка 1 (тело кончается inc h)
	VBPLANE			; H += $1E: следующая плоскость, колонка 0
	VBCOL
	ld l,e
	VBCOL
	VBPLANE
	VBCOL
	ld l,e
	VBCOL
    if !C8
	VBPLANE
	VBCOL
	ld l,e
	VBCOL
    endif
	ld hl,(vec_blit_ret)
	jp (hl)

; Одна колонка слота из двух -> VRAM (грязное по колонкам). Источник — тот же слот [p][col][row]:
; ненужные 16 Б перешагиваются указателем стека. D портится и возвращается.
VBSKIP		macro
	ld hl,16
	add hl,sp
	ld sp,hl
	endm
VBNEXTP		macro		; D += $20: следующая плоскость
	ld a,d
	add a,$20
	ld d,a
	endm
vec_blit64l:
	ld h,d
	ld l,e
	VBCOL
	VBSKIP
	VBNEXTP
	ld h,d
	ld l,e
	VBCOL
	VBSKIP
	VBNEXTP
	ld h,d
	ld l,e
	VBCOL
	VBSKIP
    if !C8
	VBNEXTP
	ld h,d
	ld l,e
	VBCOL
	VBSKIP
	ld a,d
	sub $60
    else
	ld a,d
	sub $40
    endif
	ld d,a
	ld hl,(vec_blit_ret)
	jp (hl)
vec_blit64r:
	VBSKIP
	ld h,d
	inc h
	ld l,e
	VBCOL
	VBSKIP
	VBNEXTP
	ld h,d
	inc h
	ld l,e
	VBCOL
	VBSKIP
	VBNEXTP
	ld h,d
	inc h
	ld l,e
	VBCOL
    if !C8
	VBSKIP
	VBNEXTP
	ld h,d
	inc h
	ld l,e
	VBCOL
	ld a,d
	sub $60
    else
	ld a,d
	sub $40
    endif
	ld d,a
	ld hl,(vec_blit_ret)
	jp (hl)

; Универсальный блит колонок [p][col][row] -> VRAM для панели: SP установлен, порт выведен,
; D/E = dest, vec_bl_cols = колонок, vec_bl_pops = строк/2. Возврат jp (vec_blit_ret).
vec_blit_cols:
	ld a,(vec_bl_planes)
	ld (vec_plane_cnt),a
	ld a,VEC_NPL
	ld (vec_bl_planes),a	; по умолчанию все плоскости (vec_load_panel просит по одной)
vbc_plane:
	ld a,(vec_bl_cols)
	ld (vec_col_cnt),a
	ld h,d
	ld l,e
vbc_col:
	ld a,(vec_bl_pops)	; счётчик строк — в A: в теле цикла A не жив (BC — данные, HL — приёмник),
				; а в памяти он стоил 40 тактов на пару байт при 44 тактах работы
vbc_row:
	pop bc
	ld (hl),c
	dec l
	ld (hl),b
	dec l
	pop bc			; развёрнуто по ДВЕ пары: vec_bl_pops у всех клиентов чётное
	ld (hl),c		; (панель 16, drawScoreOnOff 12, drawWeapon 8, drawChar 4)
	dec l
	ld (hl),b
	dec l
	sub 2
	jp nz,vbc_row
	inc h
	ld l,e
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,vbc_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,vbc_plane
	ld hl,(vec_blit_ret)
	jp (hl)

; Вход в стековый режим: HL = источник (SP), A = байт порта. Сохраняет SP, DI.
; (это обычная процедура: вызывается ДО подмены SP)
vec_stk_enter:
	di
	ex de,hl
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ex de,hl
	ld sp,hl
	out (KV_PORT),a
	ret			; ВНИМАНИЕ: ret по подменённому стеку недопустим — поэтому см. макро-вызов ниже
; Поэтому используем не call, а inline: см. STK_BEGIN в процедурах.

; Выход: закрыть порт, вернуть SP, EI
vec_stk_leave:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	; Сторож стека: игровой SP всегда в $7Dxx (vec_stack_top = $7E00, реальная глубина 130 Б).
	; Если сохранённое значение испорчено, `ld sp,hl` уводил стек в чужую память: push'ы затирали
	; нулевую страницу с зеркальным блитом, и машина умирала намертво (жалоба 2026-09-09, поймано
	; сторожем 2026-09-11: SP оказался $074E). Негодное значение заменяем на верх стека — игра
	; переживёт кадр вместо смерти.
	ld a,h
	cp $7D
	jp z,vsl_ok
	ld hl,vec_stack_top
vsl_ok:
	ld sp,hl
	ei
	ret


; ---------------------------------------------------------------------------
; БЮДЖЕТ DI НА КАДР. На Векторе прерывание от кадра НЕ защёлкивается: если в момент обратного хода
; включён DI, оно теряется (RTL MiSTer, Emu80; vector06js держит запрос — там дефекта не видно).
; Стековые блиты идут под DI, поэтому перед каждым блитом проверяем программный счётчик потраченного
; в кадре (vec_bud_used, ед. 256 тактов): ISR в конце выставляет свою цену (VEC_ISR_COST), вывод тика
; начинается сразу после прерывания (waitforVBlank выходит только после halt, раздача слотов пула —
; до ожидания), так что счётчик = фаза кадра. Если «потрачено + стоимость» не влезает до обратного
; хода — `halt`. Стоимости откалиброваны headless по модели слотов шины Вектора (tools/profile_vec.py,
; cpu_ready: 1 обращение к шине за 4 такта): тайл 16 + 6 накладных цикла RedrawInvTiles, FG 29 + 6,
; слот сброса ~18, спрайт по КОЛОНКАМ: прямой ~1.5 ед./строку, зеркальный ~2.1 (+8 на колонку),
; панель cols*pops/2 + 2. Таймер ВИ53 не трогаем — он нужен под музыку.
; Вход: A = стоимость в единицах 256 тактов. Портит A и флаги.
VEC_BUDGET_LIMIT equ 228	; кадр = 234 ед.; запас 6 на неучтённые накладные (стоимости откалиброваны стендом calib по реальным тактам)
VEC_ISR_COST	equ 24		; ISR с музыкой: ур.2 медиана 20 / p90 24, ур.1 медиана 22 / макс 29 (calib)
vec_budget:
    if VI53
	; фаза кадра — РЕАЛЬНАЯ, из счётчика 0 ВИ53 (перезаряжается в начале ISR): точность 2 ед.
	; (читаем только старший байт: 255-H = фаза в ед. 512 тактов). Модель цен нужна только на сам блит.
	push hl
	ld l,a
vbg_again:
	xor a
	out ($08),a		; латч счётчика 0
	in a,($0B)		; младший байт — отбросить
	in a,($0B)
	cpl			; фаза в ед. 512 тактов
	add a,a			; в ед. 256 тактов
	jp c,vbg_wait
	add a,l			; + цена блита
	jp c,vbg_wait
	cp VEC_BUDGET_LIMIT
	jp c,vbg_ok
vbg_wait:			; статистику ожиданий стенд снимает по этому адресу (measure_vec), в ROM её нет
	halt			; следующий VBlank (вне блита, EI); счётчик перезарядится в ISR
	jp vbg_again
vbg_ok:
	ld (vec_bud_used),a	; фаза+цена — для читателей фазы (сброс пула)
	pop hl
	ret

; A = реальная фаза кадра (ед. 256 тактов), обновляет vec_bud_used. Портит флаги.
vec_phase:
	xor a
	out ($08),a
	in a,($0B)
	in a,($0B)
	cpl
	add a,a
	jp nc,vph_ok
	ld a,255
vph_ok:
	ld (vec_bud_used),a
	ret
    else
	push hl
	ld l,a
	ld a,(vec_bud_used)
	add a,l
	jp c,vbg_wait
	cp VEC_BUDGET_LIMIT
	jp c,vbg_ok
vbg_wait:
	push hl			; L = стоимость, нужна после halt
	ld hl,(vec_bud_halts)	; статистика: сколько раз ждали кадр
	inc hl
	ld (vec_bud_halts),hl
	pop hl
	halt			; следующий VBlank (вне блита, EI); ISR выставит свою цену
	ld a,(vec_bud_used)
	add a,l
vbg_ok:
	ld (vec_bud_used),a
	pop hl
	ret
vec_phase:			; программный вариант: фаза = накопленная модель
	ld a,(vec_bud_used)
	ret
    endif
; Бюджет колонки спрайта ИЗНУТРИ стекового режима (SP подменён — call нельзя, вход jp, возврат
; jp (vec_blit_ret)). Выходим из стекового режима, проверяем бюджет с EI, входим обратно.
; Портит A, флаги и HL.
vec_spr_colbud:
	ld hl,0
	add hl,sp
	ld (vec_spr_src),hl	; текущая позиция источника
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ld a,(vec_spr_colcost)
	call vec_budget
	di
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_curport)
	out (KV_PORT),a
	ld hl,(vec_blit_ret)	; HL в головах колоночных циклов не жив
	jp (hl)

; ---------------------------------------------------------------------------
    if C8
; Палитра экрана: VEC_SCRPAL + (levely*width+levelx)*8 -> vec_palette (0..7 и зеркало 8..15), флаг ISR.
; Зовётся из DrawScreen (патч build_vec). Окно уровня открывается через setROM2 (тень для ISR согласована).
vec_scr_palette:
	push hl
	push de
	push bc
	ld a,(ROMBank1)
	push af
	ld a,22
	call setROM2
	ld a,(current_levely)
	ld b,a
	ld a,(level_width)
	ld c,a
	xor a
vsp_mul:
	dec b
	jp m,vsp_muld
	add a,c
	jp vsp_mul
vsp_muld:
	ld c,a
	ld a,(current_levelx)
	add a,c
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,VEC_SCRPAL
	add hl,de
	ld de,vec_palette
	ld b,8
vsp_cp:
	ld a,(hl)
	ld (de),a
	push hl
	ld hl,8
	add hl,de
	ld (hl),a
	pop hl
	inc hl
	inc de
	dec b
	jp nz,vsp_cp
	pop af
	call setROM2
	ld a,1
	ld (vec_pal_dirty),a
	pop bc
	pop de
	pop hl
	ret
    endif
; ---------------------------------------------------------------------------
; drawTile: A = тайл, B = X px, C = Y px. Обёртка с сохранением регистров — для панели инвентаря и
; DrawTile из DrawScreen; горячий путь (обход RedrawInvTiles) идёт через dt_rit -> drawTile_nosave.
drawTile:
	push hl
	push de
	push bc
	call drawTile_nosave
	pop bc
	pop de
	pop hl
	ret
; dt_rit / dft_rit — вход из обхода грязных прямоугольников (overlap_hot.asm): HL = &CURRENT_SCREEN_MAP[y*16+x],
; B = X px, C = Y px; ряды >= 10 обход не даёт (InvalidateSTiles режет высоту). Регистры не сохраняются.
dt_rit:
	ld a,(hl)
	jp drawTile_nosave
dft_rit:
	ld de,160		; CURRENT_SCREEN_MAP_FG = CURRENT_SCREEN_MAP + 160
	add hl,de
	ld a,(hl)
	or a
	ret z
	jp drawFGTile
drawTile_nosave:
    if DEMO
	ld l,a
	ld h,demo_tile_lut/256
	ld a,(hl)
	ld l,0
	rrca
	jp nc,dt_a0
	ld l,$80
dt_a0:
	and $7f
	ld h,a
	ld de,DEMO_TILES_BASE
	add hl,de
    else
	ld d,a
	; ЧЁРНЫЙ фоновый тайл (все плоскости нули): в слот пула его кладут 64 push нуля — 1.2 тыс.
	; тактов против 2.9 тыс. на блит 128 Б из квазидиска. Таких тайлов у уровня один-три, а
	; занимают они треть карты: на сцене голема 14 из 21 стайла за тик. Номера приходят из набора
	; уровня (build_edd), частый — первым, поэтому список короткий и проверяется сверху вниз.
	; cp l/cp h флаги ставят, A не портят — номер тайла доживает до dt_norm.
	ld hl,(vec_blk_tab)
	cp l
	jp z,dt_black
	cp h
	jp z,dt_black
	ld hl,(vec_blk_tab+2)
	cp l
	jp z,dt_black
	cp h
	jp z,dt_black
dt_norm:
	rrca
	and $7f
	add a,BG_TILES_BASE/256
	ld h,a
	ld a,d
	and 1
	rrca
	ld l,a
    endif
	ld (vec_blit_src),hl
dt_blit:				; вход с готовым vec_blit_src (drawFGTile: непрозрачный передний тайл)
    if !DEMO
	ld a,(vec_pool_on)
	or a
	jp z,dt_direct
	call vec_slot_for_bc
	cp POOL_SLOTS
	jp nc,dt_direct		; $FE (грязный без слота) и $FF — прямо в VRAM
	ld d,a
	ld h,vec_col_tab/256	; L — индекс стайла (vec_slot_for_bc)
	ld a,(hl)
	ld (vec_col_f),a	; какие колонки слота заливать
	ld a,d
	call vec_pool_addr
	ld a,16 - C8*2		; бюджет DI: тайл в слот. calib по ОКНУ DI (blitcalib): было 14.0 ед. при
				; цене 18, стало 12.4 — цена 16 держит тот же запас 3.6 ед.
	call vec_budget
	ex de,hl		; DE = слот в окне
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_POOL_WIN|KV_STK_P0
	out (KV_PORT),a
	ex de,hl		; HL = dest
	ld a,(vec_col_f)
	dec a
	jp z,dtb_left		; 1 — только левая колонка
	dec a
	jp z,dtb_right		; 2 — только правая
	ld a,8 - C8*2		; C8: 96 Б = 6 порций по 16 Б; счётчик — в A
dtb_loop:
	DTB16			; развёрнуто вдвое: счётчик в памяти стоил 56 тактов на 16 байт при 352
	DTB16			; тактах работы; A в теле не жив, счётчик переехал в него. Четыре копии
	sub 2			; стоили ещё 80 Б ROM ради 40 тактов на тайл — они ушли под заливку
	jp nz,dtb_loop		; чёрного тайла (dt_black), которая экономит 1.7 тыс. на стайл
	jp dt_end
; Одна колонка из двух: слот — [плоскость][колонка][16 строк], порции по 16 Б чередуются
; левая/правая. Ненужную пропускаем и в источнике (SP), и в слоте (HL): +16 к обоим.
dtb_left:
	ld a,4 - C8
dtbl_loop:
	DTB16
	ex de,hl
	ld hl,16
	add hl,sp
	ld sp,hl
	ld hl,16
	add hl,de
	dec a
	jp nz,dtbl_loop
	jp dt_end
dtb_right:
	ld a,4 - C8
dtbr_loop:
	ex de,hl
	ld hl,16
	add hl,sp
	ld sp,hl
	ld hl,16
	add hl,de
	DTB16
	dec a
	jp nz,dtbr_loop
	jp dt_end
    endif
dt_direct:
	; бюджет DI: тайл прямо в VRAM, цена 19 (calib по ОКНУ DI, blitcalib: 13.3 ед. + запас 5.5).
	; Проверка вписана сюда: call/ret и push/pop hl в vec_budget стоили 48 тактов на каждый стайл
    if VI53
	ld l,19 - C8*3
dtd_bud:
	xor a
	out ($08),a		; латч счётчика 0 ВИ53
	in a,($0B)
	in a,($0B)
	cpl
	add a,a			; фаза в ед. 256 тактов
	jp c,dtd_wait
	add a,l
	jp c,dtd_wait
	cp VEC_BUDGET_LIMIT
	jp c,dtd_ok
dtd_wait:			; стенд (measure_vec) считает ожидания и по этой метке
	halt
	jp dtd_bud
dtd_ok:
	ld (vec_bud_used),a
    else
	ld a,19 - C8*3
	call vec_budget
    endif
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
    if !DEMO
	ld a,KV_STK_P0
	out (KV_PORT),a
    endif
	ld hl,dt_end
	ld (vec_blit_ret),hl
	jp vec_blit128_vram
dt_end:
	jp vec_stk_leave	; тот же хвост (порт, SP, ei, ret) — общий со сторожем стека; 6 Б под проверку vec_hr_list
    if !DEMO
; Чёрный тайл в слот пула: 64 push нуля в СТРАНИЦУ 3 (пул лежит в ней по $A000).
; D = номер тайла, B/C = координаты стайла.
;
; ПОЧЕМУ ЗДЕСЬ НЕТ «КОМПОЗИТА» (чёрный стайл + спрайт прямо в VRAM, минуя слот). Замерено
; tools/blkstat.py 2026-09-07 (ур.2 5,6, маршрут proftick): чёрных стайлов с FG=0 под РОВНО
; ОДНИМ спрайтом 5.35/тик, но 3.23 из них — под ГЕРОЕМ (банки 2 и 3, индекс 0). Герой из отбора
; выпадает: его слоты сброс выводит списком позади луча (vpf_hero, дефект «середина меча»
; 2026-09-04), а композит написал бы часть его позы ещё в фазе сборки. Остаётся 2.05/тик
; (голем, банки 14/15 — ДВУХплоскостные, 0.79 из них зеркальные): потолок 2.05 * 4681 = 9.6 тыс.
; тактов/тик (2.7 %), реально ~2 % — вчетверо меньше, чем считалось. Цена: своё тело строки
; в VRAM на каждый из вариантов (4 плоскости / 2 плоскости, прямой / зеркальный), пометка в
; раздаче слотов, пропуск в RedrawInvTiles и в сбросе — ~450 Б, а свободно 32 Б ROM плюс
; ~288 Б хвоста string_area. Не влезает и не окупается; сначала нужен источник места.
; Соседние замеры оттуда же: слотов, оставшихся СПЛОШЬ НУЛЕВЫМИ к сбросу (стайл целиком чёрный,
; спрайт в него не попал), всего 0.0..1.5/тик по шести гейт-сценам — отдельная пометка под них
; тоже не окупается.
dt_black:
	ld a,(vec_pool_on)
	or a
	jp z,dt_blk_plain
	call vec_slot_for_bc
	cp POOL_SLOTS
	jp c,dt_blk_go
dt_blk_plain:
	; Слота нет (пул выключен, переполнение, панель): раньше отсюда уходили в dt_norm и блитили
	; из квазидиска 128 НУЛЕВЫХ байт (vb_col, 2848 тактов). Пишем нули прямо в экран тем же
	; стеком: стековый режим ВЫКЛЮЧЕН, поэтому push кладёт байты в VRAM — 64 push вместо
	; 64 pop + 128 ld (hl). Байты те же и каждый пишется один раз, фаза тика та же.
	; Стайл = 2 колонки x 16 строк x VEC_NPL плоскостей; колонки соседние (H и H+1), плоскости
	; через $20. Конец — по переносу из старшего байта: последняя плоскость $E0+col, +$20 = за $FF.
	ld a,6			; бюджет DI: окно 64 push + пролог ≈ 1.2 тыс. тактов (как у слота)
	call vec_budget
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld d,a			; D = старший байт левой колонки стайла
	ld a,Y_TOP_L+1
	sub c
	ld e,a			; E = L за верхней строкой стайла (push идёт вниз, на 16 строк)
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	xor a
	out (KV_PORT),a		; ни окон, ни стекового режима: push пишет в экран
	ld bc,0
dt_blk_v:
	ld h,d
	ld l,e
	ld sp,hl
	DBV8			; левая колонка стайла, 16 строк
	inc h			; правая колонка — тот же L
	ld sp,hl
	DBV8
	ld a,d
	add a,$20		; следующая плоскость (перенос = плоскости кончились)
	ld d,a
	jp nc,dt_blk_v
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	ret
dt_blk_go:
	ld d,a
	ld h,vec_col_tab/256	; L — индекс стайла (vec_slot_for_bc)
	ld a,(hl)
	ld (vec_col_f),a
	ld a,d
	call vec_pool_addr	; HL = POOL_BASE + слот*128
	ld de,128
	add hl,de		; push идёт вниз — начинаем с конца слота
	ex de,hl
	ld a,6			; бюджет DI: окно 64 push + пролог ≈ 1.2 тыс. тактов = 4.7 ед.
	call vec_budget
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ex de,hl
	ld sp,hl
	ld a,KV_STK_P3
	out (KV_PORT),a
	ld bc,0
	ld a,(vec_col_f)
	dec a
	jp z,dt_blk_left
	dec a
	jp z,dt_blk_right
	ld a,8
dt_blk_l:
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	dec a
	jp nz,dt_blk_l
	jp vec_stk_leave
; Одна колонка: push идёт с конца слота, порции по 16 Б — правая, левая, правая... Ненужную
; перешагиваем указателем стека.
dt_blk_left:
	ld a,4
dt_blkl_l:
	ld hl,-16
	add hl,sp
	ld sp,hl
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	dec a
	jp nz,dt_blkl_l
	jp vec_stk_leave
dt_blk_right:
	ld a,4
dt_blkr_l:
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	push bc
	ld hl,-16
	add hl,sp
	ld sp,hl
	dec a
	jp nz,dt_blkr_l
	jp vec_stk_leave
    endif

; ---------------------------------------------------------------------------
; drawFGTile: A = тайл (≠0), B, C. Передний тайл [p][col][row]:[data,mask], 256 Б
drawFGTile:
	push hl
	push de
	push bc
	; Перебор пар (номер тайла, индекс) идёт ДО бюджета DI: пока не найден индекс, неизвестно,
	; маскированный это тайл (35 ед.) или непрозрачный (тайловые 16/19 ед. считает сам dt_blit).
	ld hl,fg_tile_pairs	; передних тайлов дюжина — ищем перебором пар, таблица на 256 Б не окупалась
	ld b,a
	ld a,(fg_lut_n)		; число пар приходит из набора уровня
	or a
	jp z,dft_exit_b
	ld c,a
	ld a,b
	ld b,c
dft_find:
	cp (hl)
	inc hl
	jp z,dft_found
	inc hl
	dec b
	jp nz,dft_find
	jp dft_exit
dft_exit_b:
	jp dft_exit
dft_found:
	ld a,(hl)
	ld c,a			; индекс с флагом
	and $7f
	add a,FG_TILES_BASE/256
	ld h,a
	ld l,0
	ld (vec_blit_src),hl
	; НЕПРОЗРАЧНЫЙ передний тайл (бит 7 индекса; build_edd: маска нулевая во всех строках — вода
	; уровней 2/4/8) лежит в наборе форматом фонового, 128 Б без маски. Его кладёт обычный блит
	; тайла: 2.9 тыс. тактов вместо 6.5 тыс. на «прочитать-и-или» 256 Б. Спрайт под ним такой тайл
	; закрывал и раньше — маска нулевая, содержимое кадра то же.
	ld a,c
	rlca
	jp c,dft_opaque
	ld a,35 - C8*10		; FG: окно DI 16ц медиана 30.9 / макс 34.7 (blitcalib 2026-09-03, ур.3 1,0);
				; цена 31 была занижена ещё до пула, а с пулом FG-тайлов на тик стало больше
	call vec_budget
	pop bc			; координаты B, C: перебор пар их портил (B — счётчик, C — число пар),
	push bc			; и тайл ложился в верхний левый угол вместо своего места (вода на уровне 2)
    if !DEMO
	ld a,(vec_pool_on)
	or a
	jp z,dft_direct
	call vec_slot_for_bc
	cp POOL_SLOTS
	jp nc,dft_direct
	ld d,a
	ld h,vec_col_tab/256	; L — индекс стайла (vec_slot_for_bc)
	ld a,(hl)
	ld (vec_col_f),a
	ld a,d
	call vec_pool_addr
	ex de,hl
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_POOL_WIN|KV_STK_P0	; FG-тайлы — страница 0 ($5D00)
	out (KV_PORT),a
	ex de,hl
	ld a,16 - C8*4		; C8: 192 Б = 12 итераций
	ld (vec_row_cnt),a
	ld a,(vec_col_f)	; грязное по колонкам: маскированный передний тайл — самый дорогой блит в слот
	dec a			; (6,5 тыс. тактов), а половина его колонок под спрайтом не нужна
	jp z,dftb_left
	dec a
	jp z,dftb_right
dftb_loop:
	DFTB8
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dftb_loop
	jp dft_end
dftb_left:
	ld a,4 - C8
	ld (vec_row_cnt),a
dftbl_loop:
	DFTB8
	DFTB8
	ex de,hl		; ненужная колонка: 16 Б слота и 32 Б источника (данные+маска) перешагиваем
	ld hl,32
	add hl,sp
	ld sp,hl
	ld hl,16
	add hl,de
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dftbl_loop
	jp dft_end
dftb_right:
	ld a,4 - C8
	ld (vec_row_cnt),a
dftbr_loop:
	ex de,hl		; ненужная колонка: 16 Б слота и 32 Б источника (данные+маска) перешагиваем
	ld hl,32
	add hl,sp
	ld sp,hl
	ld hl,16
	add hl,de
	DFTB8
	DFTB8
	ld a,(vec_row_cnt)
	dec a
	ld (vec_row_cnt),a
	jp nz,dftbr_loop
	jp dft_end
    endif
dft_direct:
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
    if !DEMO
	ld a,KV_STK_P0		; FG-тайлы — страница 0
	out (KV_PORT),a
    endif
	ld a,VEC_NPL
	ld (vec_plane_cnt),a
dft_plane:
	ld h,d
	ld l,e
	ld a,2
	ld (vec_col_cnt),a
dft_col:
	; 16 строк развёрнуто (счётчик в памяти стоил ~52 такта на байт)
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	pop bc
	ld a,(hl)
	and b
	or c
	ld (hl),a
	dec l
	inc h
	ld l,e
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dft_col
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,dft_plane
dft_end:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
dft_exit:
	pop bc
	pop de
	pop hl
	ret
dft_opaque:
	pop bc			; координаты; блит тайла считает свой бюджет и возвращается по ret
	push bc
	call dt_blit
	jp dft_exit

; ---------------------------------------------------------------------------
; drawSprite: A = направление (0 прямо / 1 зеркало), B = X px (кратно 8), C = Y px,
; HL = адрес MSX ($8000 + n*384). Высота NY = (vdpCmdSprite+VDP_NY).
; Кадр 384 Б: for col 0..2: for row 31..0: [p0,p1,p2,p3]; маска на лету.
drawSprite:
	push af
	ld a,17 + C8*2		; накладные DrawSpriteList/пролога спрайта: окно DI медиана 9.5, макс 16.8
				; (blitcalib 2026-09-03, ур.1 4,5 — там пул был и до правки; цена 13 занижена)
	call vec_budget
	pop af
	push af
	ld de,-$8000
	add hl,de		; n*384 (MSX) -> n*576: + половина
	ld a,h
	or a
	rra
	ld d,a
	ld a,l
	rra
	ld e,a
	add hl,de
    if DEMO
	ld de,DEMO_FRAMES_BASE
	add hl,de
    else
	push hl
	ld a,(vec_sprite_bank)
	sub 2
	and $1f
	add a,a
	ld l,a
	ld h,0
	ld de,vec_bank_tab
	add hl,de
	ld a,(hl)
	ld (vec_spr_port),a
	inc hl
	ld d,(hl)
	ld e,0
	pop hl
	; ВЕКТОР: бит 0 порта = банк лежит в ДВУХ плоскостях, кадр вдвое короче (288 Б вместо 576)
	ld a,(vec_spr_port)
	rrca
	jp nc,ds_full
	ld a,h
	or a
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
ds_full:
	add hl,de
    endif
	ld a,(vdpCmdSprite+VDP_NY)
	ld (vec_spr_ny),a
	ld e,a
	ld a,32
	sub e
	add a,a
	ld d,a
	add a,a
	add a,d			; (32-NY)*6: строка = 6 байт [p0,маска,p1,p2,p3,пропуск]
	ld (vec_spr_skip),a
	rra			; половина — для 2-плоскостного кадра (строка 3 байта)
	and $7f
	ld (vec_spr_skip2),a
	ld e,a
	ld d,0
	add hl,de
	ld (vec_spr_src),hl
	ld a,(vec_spr_ny)
	add a,c
	dec a
	ld (vec_spr_ybot),a	; нижняя строка (MSX y)
	ld e,a
	ld a,Y_TOP_L
	sub e
	ld (vec_spr_lbot),a	; L нижней строки
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	ld (vec_spr_cx),a	; колонка экрана 0..31
	add a,VEC_P0H
	ld (vec_spr_hcol),a
	pop af
	ld (vec_spr_dir),a
	call vec_mirror_src	; ВЕКТОР: готовая зеркальная копия кадра вместо разворота на лету
	; бюджет по колонкам, calib по ОКНУ DI (blitcalib, сцена с големом): прямой 1.25 ед./строку
	; (окно 40.1 ед. на NY=32) -> NY + NY/4 + 8; зеркальный 2.25 (окно 72.2) -> 2*NY + NY/4 + 5
	push de
	ld a,(vec_spr_ny)
	ld e,a
	ld a,(vec_spr_dir)
	or a
	ld a,e
	jp z,ds_cost_fwd
	rrca
	rrca
	and $3f			; NY/4
	add a,e
	add a,e			; зеркало: 2*NY + NY/4
	jp ds_cost
ds_cost_fwd:
	rrca
	rrca
	and $3f			; NY/4
	add a,e			; прямой: NY + NY/4
	add a,3			; (+8 суммарно с общим +5 ниже)
ds_cost:
	add a,5
	ld (vec_spr_colcost),a
	pop de
    if !DEMO
	; буферный путь: пул включён и все супертайлы спрайта имеют слоты
	; (двухплоскостной банк идёт туда же — своим телом строки, см. b2p_row/b2pm_row)
	ld a,(vec_pool_on)
	or a
	jp z,ds_direct
	call vec_spr_slots_ok
	jp nc,ds_direct
	jp drawSprite_pool
    endif
ds_direct:
	ld a,(vec_spr_port)	; банк в двух плоскостях — свой блит (кадр 288 Б, строка 3 байта)
	ld (vec_spr_curport),a	; порт для возврата в стековый режим после бюджета (оба пути)
	rrca
	ld a,3
	ld (vec_col_cnt),a	; три колонки — общее для всех путей ниже
	jp nc,ds_dir4
	ld a,(vec_spr_dir)
	or a
	jp z,vec_blit2
	jp vec_zpm		; зеркальный блит нулевой страницы — с проверкой копии (arkos_hot.asm)
ds_dir4:
	ld a,(vec_spr_dir)
    if NOMIRROR
	xor a			; ЗАМЕР: см. выше
    endif
	or a
	jp nz,ds_dir4m
	ld a,$3c		; ds_col_end: hcol++ и вход колонки ds_col_go — зеркальный путь
	ld (ds_hinc),a		; (ds_dir4m) ставит вместо них dec a и dsm_prep
	ld hl,ds_col_go
	ld (ds_col+1),hl
ds_d4_go:
	; Конец колонки — по L, а не по счётчику в памяти (40 тактов на строку): L растёт на строку,
	; колонка кончается на lbot+NY (постоянно на весь спрайт, переполнения нет: = 224-y <= 224).
	; Свободных регистров в теле нет, поэтому предел вшит в сам `cp` (самомодификация — как
	; rit_call в обходе грязных тайлов). Он же даёт «осталось строк» для пропуска: end - L.
	ld a,(vec_spr_lbot)
	ld hl,vec_spr_ny
	add a,(hl)
	ld (ds_end+1),a
	ld (ds_rem+1),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
    if !DEMO
	ld a,(vec_spr_port)
	out (KV_PORT),a
    endif
ds_col:
	ld hl,ds_col_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud	; бюджет DI на колонку
ds_col_go:
	ld a,(vec_spr_hcol)
	ld h,a
	ld a,(vec_spr_lbot)
	ld l,a			; счётчик строк не нужен: колонка кончается по L (ds_end)
ds_row:
	pop bc			; C = p0, B = маска (готовая)
	pop de			; E = p1, D = p2
	ld a,b
	and (hl)
	or c
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
	ld a,b
	and (hl)
	or d
	ld (hl),a
	ld a,h
	add a,$20
	ld h,a
    if C8+SPR3
	pop de			; E = 0, D = пропуск (пустых строк выше)
	ld a,h
	sub $60			; указатель уже шагнул за 3-ю плоскость (+$60)
	ld h,a
    else
	pop de			; E = p3, D = пропуск (пустых строк выше)
	ld a,b
	and (hl)
      if !SPR3CLR
	or e			; SPR3CLR: спрайт трёхплоскостной — плоскость 3 только чистим по маске
      endif
	ld (hl),a
	ld a,h
	sub $60
	ld h,a
    endif
	inc l
	ld a,l
ds_end:
	cp 0			; самомодификация: lbot + NY
	jp z,ds_col_end
	ld a,d			; пропуск: k = min(пропуск, осталось-1)
	or a
	jp z,ds_row
ds_rem:
	ld a,0			; самомодификация: lbot + NY
	sub l			; осталось строк
	dec a
	jp z,ds_row
	cp d
	jp c,ds_k
	ld a,d
ds_k:
	ld d,a
	add a,l
	ld l,a			; k строк вверх
	ld (vec_spr_p01),hl
	ld a,d
	add a,a
	ld e,a
	add a,a
	add a,e		; 6k байт источника
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,(vec_spr_p01)
	jp ds_row
ds_col_end:
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl		; (зеркальный путь: SP стоит в буфере — dsm_prep всё равно ставит его заново)
	ld a,(vec_spr_hcol)
ds_hinc:
	inc a			; самомодификация: зеркальный путь идёт колонками справа налево (dec a)
	ld (vec_spr_hcol),a
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,ds_col
	jp vec_stk_leave
; ---------------------------------------------------------------------------
; ЗЕРКАЛЬНЫЙ прямой блит четырёхплоскостного кадра. Своего тела у него нет: колонка
; разворачивается через rev256 в буфер MIRRBUF, а в VRAM её кладёт обычное прямое тело ds_row.
; Путь достижим только когда пул выключен (или под спрайтом нет слотов) И готовой зеркальной
; копии кадра нет — за шесть гейт-сцен по 60 тиков (poolstat) ни разу; отдельные 206 Б ROM
; под него не окупались. Развёрнутая колонка стоит ~0.9 ед./строку сверх прямого блита, то есть
; суммарно дешевле снятого тела (2.25 ед./строку), поэтому цена колонки из ds_cost годится.
;
; Буфер — $C800 в СТРАНИЦЕ 3 квазидиска: это площадка стека сброса пула (vec_pool_flush), а сброс
; идёт в другой фазе тика, во время рисования спрайтов она свободна. Пишем туда через ОКНО
; $A000-$DFFF (KV_POOL_WIN — как пул), читаем обратно стеком (KV_STK_P3 — как сброс).
; Колонки идут справа налево: hcol стартует с cx+2 и уменьшается (ds_hinc).
ds_dir4m:
	ld a,(vec_spr_hcol)
	add a,2
	ld (vec_spr_hcol),a
	ld a,$3d		; ds_col_end: hcol--
	ld (ds_hinc),a
	ld hl,dsm_prep		; ds_col: после бюджета — разворот колонки, а не сразу тело
	ld (ds_col+1),hl
	ld a,(vec_spr_ny)
	add a,a
	ld l,a
	add a,a
	add a,l			; NY*6 = длина колонки в буфере (MIRRBUF выровнен на страницу, L с нуля)
	ld (dsm_bend+1),a
	ld a,(vec_spr_port)
	or KV_POOL_WIN		; окно $A000-$DFFF -> страница 3: туда пишется развёрнутая колонка
	ld (vec_spr_curport),a
	ld hl,(vec_spr_src)
	ld (vec_spr_dst),hl	; бегунок по кадру: начало текущей колонки источника
	jp ds_d4_go
dsm_prep:			; бюджет колонки уже взят (ds_col -> vec_spr_colbud), порт = банк + окно
	ld hl,(vec_spr_dst)
	ld sp,hl
	ld hl,MIRRBUF
	ld d,rev256/256		; таблица разворота выровнена на страницу: индекс в E, байт `ld a,(de)`
dsm_prow:
	pop bc			; C = p0, B = маска
	ld e,c
	ld a,(de)
	ld (hl),a
	inc l
	ld e,b
	ld a,(de)
	ld (hl),a
	inc l
	pop bc			; C = p1, B = p2
	ld e,c
	ld a,(de)
	ld (hl),a
	inc l
	ld e,b
	ld a,(de)
	ld (hl),a
	inc l
	pop bc			; C = p3, B = пропуск пустых строк
	ld e,c
	ld a,(de)
	ld (hl),a
	inc l
	ld (hl),b		; пропуск — как есть: строка буфера того же формата, что строка кадра
	inc l
	ld a,l
dsm_bend:
	cp 0			; самомодификация (ds_dir4m): NY*6
	jp nz,dsm_prow
	ld hl,0
	add hl,sp
	ld a,(vec_spr_skip)
	ld e,a
	ld d,0
	add hl,de
	ld (vec_spr_dst),hl	; следующая колонка кадра
	ld hl,MIRRBUF
	ld sp,hl
	ld a,KV_STK_P3
	out (KV_PORT),a
	jp ds_col_go

    if !DEMO
; ---- проверка слотов под спрайт: CY=1 если все супертайлы (cx..cx+2, ybot-ny+1..ybot) имеют слот
vec_spr_slots_ok:
	ld a,(vec_spr_ybot)
	cp 160
	jp nc,vss_no
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld (vec_tmp_sx),a	; sx0
	ld a,(vec_spr_cx)
	add a,2
	rrca
	and $0f
	ld (vec_tmp_sx1),a	; sx1
	ld a,(vec_spr_ybot)
	and $f0
	ld c,a			; sy1*16
	ld a,(vec_spr_ny)
	ld b,a
	ld a,(vec_spr_ybot)
	sub b
	inc a
	and $f0
	ld b,a			; sy0*16
vss_y:
	ld a,(vec_tmp_sx)
vss_x:
	or b
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	cp POOL_SLOTS
	jp nc,vss_no
	ld a,l
	and $0f
	ld l,a
	ld a,(vec_tmp_sx1)
	cp l
	jp z,vss_ynext
	ld a,l
	inc a
	jp vss_x
vss_ynext:
	ld a,b
	cp c
	jp z,vss_yes
	add a,16
	ld b,a
	jp vss_y
vss_yes:
	scf
	ret
vss_no:
	or a
	ret

; ---- спрайт в пул. Колонка экрана cx (0..31); слот супертайла (cx>>1, row>>4);
; адрес = $A000 + slot*128 + (cx&1)*16 + (row&15); плоскости +32 (в пределах страницы).
drawSprite_pool:
	; Тело строки выбирается флагом «банк в двух плоскостях» (бит 0 порта): пролог сегмента,
	; цикл колонок, бюджет DI и разбор cx — общие, различается только разбор данных строки
	; (четыре плоскости — 6 Б на строку, две — 3 Б на строку, читаются парами).
	ld hl,dsp_row
	ld de,dspm_row
	ld a,(vec_spr_port)
	rrca
	jp nc,dsp_body
	ld hl,b2p_row
	ld de,b2pm_row
	ld a,(vec_spr_skip2)	; хвост колонки короче вдвое: (32-NY)*3
	ld (vec_spr_skip),a
dsp_body:
	ld (dsp_go+1),hl
	ex de,hl		; на i8080 нет ld (nn),de
	ld (dspm_go+1),hl
	ld a,(vec_spr_dir)
    if NOMIRROR
	xor a			; ЗАМЕР: зеркало отключено — оценка потолка для кеша развёрнутых кадров
    endif
	or a
	jp nz,dsp_mirror
	ld a,3
	ld (vec_col_cnt),a
	; Колонка спрайта меняется трижды, а сегментов на неё два: разбор vec_spr_cx (слот по x и
	; смещение колонки внутри слота) вынесен из пролога сегмента в самомодифицируемые константы.
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld (dsp_sx+1),a
	ld a,(vec_spr_cx)
	and 1
	rrca
	rrca
	rrca
	rrca
	ld (dsp_coff+1),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	or KV_POOL_WIN
	ld (vec_spr_curport),a
	out (KV_PORT),a
dsp_col:			; бюджет DI — на колонку целиком (как у прямого пути ds_col), а не на сегмент:
	ld hl,dsp_col_go	; окно DI то же (сегменты идут подряд), а проверка одна вместо двух и
	ld (vec_blit_ret),hl	; адрес сегмента больше не надо прятать в память через vec_spr_dst
	jp vec_spr_colbud
dsp_col_go:
	ld a,(vec_spr_ny)
	ld (vec_rows_left),a
	ld a,(vec_spr_ybot)
	ld (vec_spr_row),a
dsp_seg:
	; слот и адрес сегмента (vec_spr_row читаем один раз в D, разбор cx — в константах ниже)
	ld a,(vec_spr_row)
	ld d,a
	and $f0
dsp_sx:
	or 0			; самомодификация (dsp_col_go/dsp_seg_end): (cx>>1)&15
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
dsp_coff:
	add a,0			; самомодификация: (cx&1)*16
	ld e,a
	ld a,d
	and 15
	ld c,a
	add a,e
	ld l,a			; HL = адрес плоскости 0 нижней строки сегмента
	; n = min(rows_left, (row&15)+1)
	ld a,c
	inc a
	ld b,a
	ld a,(vec_rows_left)
	cp b
	jp nc,dsp_n_ok
	ld b,a
dsp_n_ok:
	ld a,l			; конец сегмента по L (в пуле строка = -1): счётчик строк в памяти
	sub b			; стоил 40 тактов на строку, свободных регистров в теле нет — предел
	ld (dsp_end+1),a	; вшит в сам `cp` (самомодификация, как rit_call в обходе тайлов)
	ld (dsp_rem+1),a
	ld (b2p_endA+1),a	; двухплоскостное тело держит предел в двух `cp` (пара строк);
	ld (b2p_endB+1),a	; писать всегда дешевле, чем самомодифицировать адреса записи
	ld a,(vec_rows_left)
	sub b
	ld (vec_rows_left),a
	ld a,(vec_spr_row)
	sub b
	ld (vec_spr_row),a	; бюджет колонки взят в dsp_col (vec_spr_colcost = NY + NY/4 + 8 из drawSprite)
dsp_go:
	jp dsp_row		; самомодификация (drawSprite_pool): dsp_row — четыре плоскости,
				; b2p_row/b2p_rowb — две (пара строк может разорваться сегментом)
dsp_row:
	pop bc			; C = p0, B = маска
	pop de			; E = p1, D = p2
	ld a,b
	and (hl)
	or c
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or e
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or d
	ld (hl),a
	ld a,l
	add a,32
	ld l,a
    if C8+SPR3
	pop de			; E = 0 (заполнитель), D = пропуск
	ld a,l
	sub 96+1		; указатель уже шагнул за 3-ю плоскость (+96) — назад на плоскость 0 и строкой выше
    else
	pop de			; E = p3, D = пропуск
	ld a,b
	and (hl)
      if !SPR3CLR
	or e			; SPR3CLR: плоскость 3 только чистим
      endif
	ld (hl),a
	ld a,l
	sub 96+1		; назад на плоскость 0 и строкой выше
    endif
	ld l,a			; A уже равен новому L
dsp_end:
	cp 0			; самомодификация: L конца сегмента
	jp z,dsp_seg_end
	ld a,d
	or a
	jp z,dsp_row
	ld a,l			; осталось строк = L - конец
dsp_rem:
	sub 0			; самомодификация: L конца сегмента
	dec a
	jp z,dsp_row
	cp d
	jp c,dsp_k
	ld a,d
dsp_k:
	ld d,a
	ld a,l
	sub d
	ld l,a			; k строк вверх (в пуле строка = -1)
	ld (vec_spr_p01),hl
	ld a,d
	add a,a
	ld e,a
	add a,a
	add a,e
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,(vec_spr_p01)
	jp dsp_row
dsp_seg_end:
	ld a,(vec_rows_left)
	or a
	jp nz,dsp_seg
	; следующая колонка
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(dsp_coff+1)	; cx+1: смещение колонки переключается, слот по x растёт на нечётной cx
	xor 16
	ld (dsp_coff+1),a
	jp nz,dsp_col_next
	ld a,(dsp_sx+1)
	inc a
	ld (dsp_sx+1),a
dsp_col_next:
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dsp_col
	jp vec_stk_leave
dsp_mirror:
	; Цена колонки в пуле СВОЯ: зеркальная строка пула стоит 381 такт (было 490), окно DI на NY=32
	; — медиана 53.3 / p90 58.7 ед. (blitcalib, сцена 4,5), а ds_cost дал бы 2*NY + NY/4 + 5 = 77.
	ld a,(vec_spr_ny)
	add a,a
	add a,8			; 2*NY + 8 (запас 22 % над p90)
	ld (vec_spr_colcost),a
	ld a,(vec_spr_cx)
	add a,2
	ld (vec_spr_cx),a
	ld a,3
	ld (vec_col_cnt),a
	; разбор cx — в самомодифицируемые константы пролога сегмента (см. drawSprite_pool)
	ld a,(vec_spr_cx)
	rrca
	and $0f
	ld (dspm_sx+1),a
	ld a,(vec_spr_cx)
	and 1
	rrca
	rrca
	rrca
	rrca
	ld (dspm_coff+1),a
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_spr_src)
	ld sp,hl
	ld a,(vec_spr_port)
	or KV_POOL_WIN
	ld (vec_spr_curport),a
	out (KV_PORT),a
dspm_col:			; бюджет DI — на колонку целиком (см. dsp_col)
	ld hl,dspm_col_go
	ld (vec_blit_ret),hl
	jp vec_spr_colbud
dspm_col_go:
	ld a,(vec_spr_ny)
	ld (vec_rows_left),a
	ld a,(vec_spr_ybot)
	ld (vec_spr_row),a
dspm_seg:
	ld a,(vec_spr_row)
	ld d,a
	and $f0
dspm_sx:
	or 0			; самомодификация (dsp_mirror/dspm_seg_end): (cx>>1)&15
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	ld l,a
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
dspm_coff:
	add a,0			; самомодификация: (cx&1)*16
	ld e,a
	ld a,d
	and 15
	ld c,a
	add a,e
	ld l,a			; HL = адрес плоскости 0 нижней строки сегмента
	ld a,c
	inc a
	ld b,a
	ld a,(vec_rows_left)
	cp b
	jp nc,dspm_n_ok
	ld b,a
dspm_n_ok:
	ld a,l			; конец сегмента по L (в пуле строка = -1), см. dsp_n_ok
	sub b
	ld (dspm_end+1),a
	ld (dspm_rem+1),a
	ld (b2pm_endA+1),a	; двухплоскостное тело: два `cp` на пару строк
	ld (b2pm_endB+1),a
	ld a,(vec_rows_left)
	sub b
	ld (vec_rows_left),a
	ld a,(vec_spr_row)
	sub b
	ld (vec_spr_row),a	; бюджет колонки взят в dspm_col (vec_spr_colcost из ds_cost + 3)
dspm_go:
	jp dspm_row		; самомодификация (drawSprite_pool): dspm_row / b2pm_row / b2pm_rowb
dspm_row:			; HL = адрес плоскости 0 текущей строки в пуле; таблица разворота — через DE
	; Указатель НЕ прячется в память на время просмотра rev256 (было ld (vec_spr_dst),hl + ld hl,(nn)
	; = 40 тактов на строку): rev256 выровнена на страницу, поэтому индекс кладём в E, страницу в D,
	; и байт берём `ld a,(de)` — HL всё время держит приёмник. Маска и p0 остаются в регистрах
	; (было 4 обращения к vec_spr_mask/vec_spr_p01 по 16 тактов), пропуск переезжает в C.
	ld d,rev256/256
	pop bc			; C = p0, B = маска
	ld e,c
	ld a,(de)
	ld c,a			; C = p0 развёрнутый
	ld e,b
	ld a,(de)
	ld b,a			; B = маска развёрнутая (A уже равен ей)
	and (hl)		; плоскость 0 — сразу, пока маска в A
	or c
	ld (hl),a
	pop de			; E = p1, D = p2
	ld c,d			; C = p2 (сырой)
	ld d,rev256/256
	ld a,(de)		; E уже = p1
	ld e,a			; E = p1 развёрнутый
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)		; плоскость 1
	or e
	ld (hl),a
	ld e,c
	ld a,(de)
	ld e,a			; E = p2 развёрнутый
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)		; плоскость 2
	or e
	ld (hl),a
    if C8+SPR3
	pop de			; E = 0 (заполнитель), D = пропуск
	ld c,d			; C = пропуск
	ld a,l
	sub 64+1		; указатель стоит на 3-й плоскости (+64) — назад на плоскость 0 и строкой выше
    else
	pop de			; E = p3, D = пропуск
	ld c,d			; C = пропуск
	ld d,rev256/256
	ld a,(de)
	ld e,a			; E = p3 развёрнутый
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)		; плоскость 3
      if !SPR3CLR
	or e			; SPR3CLR: плоскость 3 только чистим
      endif
	ld (hl),a
	ld a,l
	sub 96+1		; назад на плоскость 0 и строкой выше
    endif
	ld l,a			; A уже равен новому L
dspm_end:
	cp 0			; самомодификация: L конца сегмента
	jp z,dspm_seg_end
	ld a,c			; пропуск
	or a
	jp z,dspm_row
	ld a,l			; осталось строк = L - конец
dspm_rem:
	sub 0			; самомодификация: L конца сегмента
	dec a
	jp z,dspm_row
	cp c
	jp c,dspm_k
	ld a,c
dspm_k:
	ld c,a
	ld a,l
	sub c
	ld l,a			; k строк вверх (в пуле строка = -1)
	ld (vec_spr_p01),hl
	ld a,c
	add a,a
	ld e,a
	add a,a
	add a,e			; 6k байт источника
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld hl,(vec_spr_p01)
	jp dspm_row
dspm_seg_end:
	ld a,(vec_rows_left)
	or a
	jp nz,dspm_seg
	ld a,(vec_spr_skip)
	ld l,a
	ld h,0
	add hl,sp
	ld sp,hl
	ld a,(dspm_coff+1)	; cx-1: смещение переключается, слот по x падает на чётной cx
	xor 16
	ld (dspm_coff+1),a
	jp z,dspm_col_next
	ld a,(dspm_sx+1)
	dec a
	ld (dspm_sx+1),a
dspm_col_next:
	ld a,(vec_col_cnt)
	dec a
	ld (vec_col_cnt),a
	jp nz,dspm_col
	jp vec_stk_leave

; ---------------------------------------------------------------------------
; ДВУХПЛОСКОСТНОЙ (четырёхцветный) спрайт в слот пула. Кадр 288 Б, строка — три байта
; [старший бит цвета, маска, младший бит]; значения 0..3 живут в двух младших битах, поэтому данные
; идут в плоскости 2 и 3, а плоскости 0 и 1 спрайт только ГАСИТ маской (фон уровня их использует).
; Пролог сегмента, цикл колонок, разбор cx и бюджет DI — общие с четырёхплоскостным путём
; (dsp_seg/dspm_seg, вход через самомодифицируемый dsp_go/dspm_go).
;
; Три байта на строку читаются стеком по два, поэтому строки идут ПАРАМИ: тройка pop даёт строку A
; целиком плюс первый байт строки B. Сегмент (кусок колонки внутри одного супертайла) может кончиться
; МЕЖДУ строками пары — тогда первый байт строки B уезжает в vec_b2_carry, пролог сегмента отрабатывает
; как обычно, и новый сегмент начинается сразу со строки B (b2p_cont -> b2p_rowb).
; Разрыв пары на границе КОЛОНКИ невозможен: NY у двухплоскостных кадров чётное (нечётное разъехалось
; бы и в прямом блите — там на строку A тратится четыре байта источника вместо трёх).
b2p_row:
	pop bc			; C = плоскость 2 строки A, B = её маска
	pop de			; E = плоскость 3 строки A, D = плоскость 2 строки B
	ld a,b
	and (hl)
	ld (hl),a		; плоскость 0 — только гасим
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	ld (hl),a		; плоскость 1 — только гасим
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or c
	ld (hl),a		; плоскость 2 — старший бит цвета
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or e
	ld (hl),a		; плоскость 3 — младший бит
	ld a,l
	sub 96+1		; назад на плоскость 0 и строкой выше (в пуле строка = -1)
	ld l,a
b2p_endA:
	cp 0			; самомодификация (dsp_n_ok): L конца сегмента
	jp z,b2p_split
b2p_rowb:			; D = плоскость 2 строки B
	pop bc			; C = маска строки B, B = её плоскость 3
	ld a,c
	and (hl)
	ld (hl),a		; плоскость 0
	ld a,l
	add a,32
	ld l,a
	ld a,c
	and (hl)
	ld (hl),a		; плоскость 1
	ld a,l
	add a,32
	ld l,a
	ld a,c
	and (hl)
	or d
	ld (hl),a		; плоскость 2
	ld a,l
	add a,32
	ld l,a
	ld a,c
	and (hl)
	or b
	ld (hl),a		; плоскость 3
	ld a,l
	sub 96+1
	ld l,a
b2p_endB:
	cp 0			; самомодификация (dsp_n_ok): L конца сегмента
	jp nz,b2p_row
	ld hl,b2p_row		; сегмент кончился на границе пары
	ld (dsp_go+1),hl
	jp dsp_seg_end
b2p_split:			; сегмент кончился МЕЖДУ строками пары
	ld a,d
	ld (vec_b2_carry),a
	ld hl,b2p_cont
	ld (dsp_go+1),hl
	jp dsp_seg_end
b2p_cont:
	ld a,(vec_b2_carry)
	ld d,a
	jp b2p_rowb

; ---- зеркальный вариант: те же три байта, но каждый разворачивается через rev256 (страница
; выровнена, индекс в E, страница в D — как в dspm_row).
b2pm_row:
	ld d,rev256/256
	pop bc			; C = плоскость 2 строки A, B = её маска (сырые)
	ld e,c
	ld a,(de)
	ld c,a			; C = плоскость 2 развёрнутая
	ld e,b
	ld a,(de)
	ld b,a			; B = маска развёрнутая (A уже равен ей)
	and (hl)
	ld (hl),a		; плоскость 0 — только гасим
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	ld (hl),a		; плоскость 1 — только гасим
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or c
	ld (hl),a		; плоскость 2
	pop de			; E = плоскость 3 строки A, D = плоскость 2 строки B (сырые)
	ld c,d			; C = плоскость 2 строки B (сырая) — переживёт остаток строки A
	ld d,rev256/256
	ld a,(de)
	ld e,a			; E = плоскость 3 строки A развёрнутая
	ld a,l
	add a,32
	ld l,a
	ld a,b
	and (hl)
	or e
	ld (hl),a		; плоскость 3
	ld a,l
	sub 96+1
	ld l,a
b2pm_endA:
	cp 0			; самомодификация (dspm_n_ok): L конца сегмента
	jp z,b2pm_split
b2pm_rowb:			; C = плоскость 2 строки B (сырая), D = страница rev256
	ld e,c
	ld a,(de)
	ld c,a			; C = плоскость 2 строки B развёрнутая
	pop de			; E = маска строки B, D = её плоскость 3 (сырые)
	ld b,d			; B = плоскость 3 (сырая)
	ld d,rev256/256
	ld a,(de)
	ld e,a			; E = маска развёрнутая (A уже равен ей)
	and (hl)
	ld (hl),a		; плоскость 0
	ld a,l
	add a,32
	ld l,a
	ld a,e
	and (hl)
	ld (hl),a		; плоскость 1
	ld a,l
	add a,32
	ld l,a
	ld a,e
	and (hl)
	or c
	ld (hl),a		; плоскость 2
	ld c,e			; маску — в C, E освобождаем под плоскость 3
	ld e,b
	ld a,(de)
	ld e,a			; E = плоскость 3 развёрнутая
	ld a,l
	add a,32
	ld l,a
	ld a,c
	and (hl)
	or e
	ld (hl),a		; плоскость 3
	ld a,l
	sub 96+1
	ld l,a
b2pm_endB:
	cp 0			; самомодификация (dspm_n_ok): L конца сегмента
	jp nz,b2pm_row
	ld hl,b2pm_row		; сегмент кончился на границе пары
	ld (dspm_go+1),hl
	jp dspm_seg_end
b2pm_split:			; сегмент кончился МЕЖДУ строками пары
	ld a,c
	ld (vec_b2_carry),a
	ld hl,b2pm_cont
	ld (dspm_go+1),hl
	jp dspm_seg_end
b2pm_cont:
	ld a,(vec_b2_carry)
	ld c,a
	ld d,rev256/256
	jp b2pm_rowb

; ---------------------------------------------------------------------------
; vec_pool_begin — вызывается в начале RedrawScreen_part1 / RedrawScreen:
; раздать слоты пула dirty-супертайлам (строки 0..9). Переполнение (>128) -> прямой режим.
; vec_slot_init: карта грязных стайлов = $FF (чисто), метки строк ($A0..$A9 и выше) = 0.
; Зовётся при старте и из сброса, когда пул был выключен (переполнение / стендовый прямой режим).
vec_slot_init:
	ld hl,vec_col_tab
	ld b,160
	xor a
vpb_clrc:
	ld (hl),a
	inc l
	dec b
	jp nz,vpb_clrc
	ld hl,vec_slot_tab
	ld b,160
	ld a,$ff
vpb_clr:
	ld (hl),a
	inc l
	dec b
	jp nz,vpb_clr
	xor a
vpb_clr2:
	ld (hl),a
	inc l
	jp nz,vpb_clr2
	ret
vec_pool_begin:
	; таблицу слотов НЕ чистим (256 байт = 40 ед. каждый тик): все помеченные $FE/слот записи
	; проходит сброс пула и возвращает $FF
	xor a
	ld (vec_pool_on),a
	ld a,(vec_pool_ban)	; стендовый прямой режим (build_edd POOL_OFF=1) — для сравнения
	or a			; «пул против прямого». Карту грязных стайлов строим и в нём (по ней
	ld a,0			; идёт RedrawInvTiles), а слотов не раздаём: vec_slot_next = 80 сразу,
	jp z,vpb_ban_no		; каждому стайлу достаётся $FE
	ld a,POOL_SLOTS
vpb_ban_no:
	ld (vec_slot_next),a
	ld a,(ndirtyrects)
	or a
	ret z
	ld c,a
	ld de,tiles_dirty
vpb_rect:
	ld a,(de)		; xs; бит 7 — левая колонка первого стайла не нужна
	ld (vec_col_l),a
	and $7f
	ld (vec_tmp_sx),a
	inc de
	ld a,(de)		; ys
	ld (vec_tmp_sy),a
	inc de
	ld a,(de)		; nx; бит 7 — правая колонка последнего стайла не нужна
	ld (vec_col_r),a
	and $7f
	ld (vec_tmp_nx),a
	inc de
	ld a,(de)		; ny
	ld (vec_tmp_ny),a
	inc de
	push de
	push bc
vpb_y:
	ld a,(vec_tmp_sy)
	cp 10
	jp nc,vpb_rect_done	; панель — без слотов
	; ПОЛОСА ГРЯЗНОГО В СТРОКЕ: vec_slot_tab[160+y] = xmin+1 (0 = строка чиста),
	; vec_slot_tab[176+y] = xmax+1. По ней идут оба прохода RedrawInvTiles и сброс пула: без неё
	; сброс перечитывал ВСЕ прямоугольники на каждой из 10 строк, а проходы перебирали все 16
	; колонок строки. Хвост таблицы слотов свободен: индексов >= 160 у неё нет (vec_slot_for_bc
	; режет y >= 160), метки снимает сам сброс.
	ld e,a
	add a,160
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(vec_tmp_sx)
	inc a
	ld c,a			; C = xmin+1 этого прямоугольника
	ld a,(hl)
	or a
	jp z,vpb_mn_set		; строка была чиста
	cp c
	jp c,vpb_mn_keep	; старый xmin меньше
vpb_mn_set:
	ld (hl),c
vpb_mn_keep:
	ld a,(vec_tmp_sx)
	ld b,a
	ld a,(vec_tmp_nx)
	add a,b			; sx+nx = xmax+1
	cp 17
	jp c,vpb_mx_ok
	ld a,16
vpb_mx_ok:
	ld c,a
	ld a,l
	add a,16
	ld l,a
	ld a,(hl)
	cp c
	jp nc,vpb_mx_keep
	ld (hl),c
vpb_mx_keep:
	ld a,e
	rlca
	rlca
	rlca
	rlca
	ld e,a			; E = sy*16 (в ячейке держать незачем — регистр свободен)
	ld a,(vec_tmp_nx)
	ld b,a
	ld a,(vec_tmp_sx)
	ld c,a
vpb_x:
	ld a,e			; H уже стоит на таблице слотов (метка строки выше)
	or c
	ld l,a
	; нужные колонки этого стайла: обе, кроме краёв прямоугольника с битом 7
	ld d,3
	ld a,(vec_tmp_sx)
	cp c
	jp nz,vpb_cl_ok
	ld a,(vec_col_l)
	rlca
	jp nc,vpb_cl_ok
	ld d,2			; первый стайл, левая колонка не нужна
vpb_cl_ok:
	ld a,b
	dec a
	jp nz,vpb_cr_ok
	ld a,(vec_col_r)
	rlca
	jp nc,vpb_cr_ok
	ld a,d
	and 1			; последний стайл, правая колонка не нужна
	ld d,a
vpb_cr_ok:
	ld h,vec_col_tab/256
	ld a,(hl)
	or d
	ld (hl),a
	ld h,vec_slot_tab/256
	; Под стайлом есть передний тайл? Тогда слот: прямой путь клал бы фон и FG в VRAM порознь, и луч
	; между ними видел фон без воды/тумана (мерцание воды под мечом у голема, Emu80 2026-09-04).
	; Индекс L = sy*16+sx — тот же, что у карты переднего слоя.
	push hl
	ld a,l
	add a,CURRENT_SCREEN_MAP_FG & $FF
	ld l,a
	ld a,0
	adc a,CURRENT_SCREEN_MAP_FG >> 8
	ld h,a
	ld a,(hl)
	pop hl
	or a
	jp z,vpb_fe
	ld a,(vec_slot_next)
	cp POOL_SLOTS
	jp nc,vpb_fe
	ld (hl),a
	inc a
	ld (vec_slot_next),a
	jp vpb_x_next
vpb_fe:
	ld (hl),$fe		; грязный супертайл без слота: рисуется прямо в VRAM (и BG, и FG)
vpb_x_next:
	inc c
	dec b
	jp nz,vpb_x
	ld a,(vec_tmp_sy)
	inc a
	ld (vec_tmp_sy),a
	ld a,(vec_tmp_ny)
	dec a
	ld (vec_tmp_ny),a
	jp nz,vpb_y
vpb_rect_done:
	pop bc
	pop de
	dec c
	jp nz,vpb_rect
	; Слоты — только грязным супертайлам под спрайтами, которые рисуются в этом тике: и под текущей,
	; и под ПРОШЛОЙ позицией (иначе старое место стирается прямым путём в фазе сборки, а спрайт на новом
	; появляется лишь при сбросе — на кадр герой пропадает/режется). Остальное — в VRAM одним проходом.
	xor a
	ld (vec_tmp_ovf),a
	ld a,(vec_slot_next)	; слоты героя — с этого номера (он первый в списке) до конца его раздачи
	ld (vec_hr_s0),a
	ld (vec_hr_s1),a
	ld a,1
	ld (vec_hr_want),a
	ld hl,vec_hr_list
	ld (vec_hr_lp),hl
	ld de,SPDATA
	ld c,MAX_SPRITES
	ld hl,vec_spr_prev
	ld (vec_tmp_rp),hl
vpb_spr:
	ld a,(de)		; включён?
	inc de
	ld l,a
	ld a,(de)
	dec de
	or l
	jp z,vpb_spr_off
	ld hl,7
	add hl,de
	ld a,(hl)		; перерисовывается?
	or a
	jp z,vpb_spr_copy
	push de
	push bc
	ld hl,3
	add hl,de
	call vpb_rect_assign	; текущий прямоугольник
	ld hl,(vec_tmp_rp)
	call vpb_rect_assign	; прошлый
	pop bc
	pop de
	ld a,(vec_hr_want)	; первый перерисованный спрайт (герой) закрывает диапазон [s0,s1)
	or a
	jp z,vpb_spr_copy
	xor a
	ld (vec_hr_want),a
	ld a,(vec_slot_next)
	ld (vec_hr_s1),a
	call vpb_hr_calc	; цена и дедлайны луча для слотов героя (arkos_hot.asm, зазор)
vpb_spr_copy:
	ld hl,3			; prev := текущий (x,y,nx,ny)
	add hl,de
	push de
	ex de,hl
	ld hl,(vec_tmp_rp)
	ld b,4
vpb_cp:
	ld a,(de)
	ld (hl),a
	inc hl
	inc de
	dec b
	jp nz,vpb_cp
	pop de
	jp vpb_spr_adv
vpb_spr_off:
	ld hl,(vec_tmp_rp)	; выключен: prev.nx = 0
	inc hl
	inc hl
	ld (hl),0
vpb_spr_adv:
	ld hl,(vec_tmp_rp)
	inc hl
	inc hl
	inc hl
	inc hl
	ld (vec_tmp_rp),hl
	ld hl,8
	add hl,de
	ex de,hl
	dec c
	jp nz,vpb_spr
	ld a,(vec_tmp_ovf)
	or a
	jp nz,vpb_overflow2
	ld a,1
	ld (vec_pool_on),a
	ret
vpb_overflow2:
	ld a,1			; чистить карту грязных стайлов сейчас НЕЛЬЗЯ: по ней идёт RedrawInvTiles
	ld (vec_pool_clr),a	; (раньше карта была отдельной битовой) — снимет сброс, в самом конце тика
	xor a
	ld (vec_pool_on),a
	ret
; vpb_rect_assign: HL -> [x px, y px, nx, ny (символы по 8)]; грязным ($FE) супертайлам под ним — слоты.
; nx = 0 — пропуск. Переполнение слотов -> vec_tmp_ovf = 1.
vpb_rect_assign:
	; Регистры вместо ячеек: C = sx0, E = sx1, B = текущая строка (sy*16), D = L конца строки,
	; HL = указатель в таблицу слотов (по строке идём inc l — sx0 <= sx1 <= 15, за строку не выходим).
	; Ширина/высота умножаются сдвигом вместо цикла «прибавить 8 nx раз» (nx, ny — размер спрайта
	; в символах, <= 31: сдвиг даёт то же по модулю 256, а перенос — то же условие обрезки).
	inc hl
	inc hl
	ld a,(hl)		; nx
	or a
	ret z
	add a,a
	add a,a
	add a,a			; nx*8
	ld b,a
	dec hl
	dec hl
	ld a,(hl)		; x
	rrca
	rrca
	rrca
	rrca
	and $0f
	ld c,a			; C = sx0
	ld a,(hl)
	dec a
	add a,b			; x - 1 + nx*8
	jp c,vpb_sx1_clip
	rrca
	rrca
	rrca
	rrca
	and $0f
	jp vpb_sx1_ok
vpb_sx1_clip:
	ld a,15
vpb_sx1_ok:
	ld e,a			; E = sx1
	ld a,(vec_hr_want)	; герой: ±2 колонки под росчерк меча (arkos_hot.asm, зазор)
	or a
	call nz,vpb_hr_widen
	inc hl
	ld a,(hl)		; y px
	cp 160
	ret nc			; панель
	ld d,a
	and $f0
	ld b,a			; B = sy0*16
	inc hl
	inc hl
	ld a,(hl)		; ny
	add a,a
	add a,a
	add a,a			; ny*8
	add a,d
	dec a			; y - 1 + ny*8 (по модулю 256 — как старый цикл)
	cp 160
	jp c,vpb_sy_ok
	ld a,159
vpb_sy_ok:
	and $f0
	ld (vec_tmp_ny),a	; sy1*16
vpb_sy:
	ld a,b
	or e
	ld d,a			; D = L конца строки
	ld a,b
	or c
	ld l,a
	ld h,vec_slot_tab/256
vpb_sxl:
	ld a,(hl)
	cp $fe
	jp nz,vpb_sx_next	; не грязный (или уже со слотом)
	ld a,(vec_slot_next)
	cp POOL_SLOTS			; слоты 0..79 = $A000-$C7FF; выше $C980 — музыка
	jp nc,vpb_ovf
	ld (hl),a
	inc a
	ld (vec_slot_next),a
	ld a,(vec_hr_want)	; слот героя — в список (сброс выводит их отдельно, позади луча)
	or a
	jp z,vpb_sx_next
	; Список — 20 Б, а граница не проверялась: при смене экрана под героем (текущее и прошлое место
	; на разных краях, грязно всё поле) слотов набиралось до 30, и запись шла дальше списка — по
	; vec_hr_dl0..vec_tmp_ny и в vec_tmp_rp. Тот становился адресом из номеров слотов ($2324, $7Bxx,
	; $00xx), и vpb_cp клал туда прямоугольники спрайтов: в код, в vec_sp_save, в нулевую страницу
	; («смерть машины» 2026-09-09; пойман tools/spwatch.py: ур.4 5,5 seed 11). Полный список = как
	; переполнение пула: этот тик рисуется прямым путём.
	ld a,(vec_hr_lp)
	cp $ff & (vec_hr_list+20)
	jp z,vpb_ovf
	push hl
	ld a,l
	ld hl,(vec_hr_lp)
	ld (hl),a
	inc hl
	ld (vec_hr_lp),hl
	pop hl
vpb_sx_next:
	ld a,l
	cp d
	jp z,vpb_sy_next
	inc l
	jp vpb_sxl
vpb_sy_next:
	ld a,(vec_tmp_ny)
	cp b
	ret z
	ld a,b
	add a,16
	ld b,a
	jp vpb_sy
vpb_ovf:
	ld a,1
	ld (vec_tmp_ovf),a
	ret

; vec_pool_flush — вместо TransferDirtyTiles в RedrawScreen_part2: слоты -> VRAM,
; строками супертайлов сверху вниз (0..9), затем ndirtyrects=0.
vec_pool_flush:
	; Сброс идёт С РАЗРЕШЁННЫМИ прерываниями и БЕЗ единого обращения к настоящему стеку: порт весь
	; сброс держится в стековом режиме (страница 3 = пул), цикл — на ячейках, адрес слота считается
	; inline, блит возвращается через jp (vec_blit_ret). RST/push прерывания ложатся в страницу 3 под
	; SP — это уже вытолкнутые байты пула или свободная область. ISR держит стековые биты порта
	; (vec_kv_shadow = KV_STK_P3). Переходы режима (2 на сброс) — под коротким DI и только не у края
	; кадра (по счётчику бюджета), чтобы не потерять прерывание.
	ld a,(vec_kv_shadow)
	ld (vec_kv_prev),a	; окно главного кода — вернуть в конце (и когда пула нет)
	ld a,(vec_pool_on)
	or a
	jp z,vpf_done
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl	; настоящий SP
	call vec_phase		; у края кадра (> 205 ед.) — дождаться прерывания: переход режима не должен
	cp 206			; совпасть с обратным ходом
	jp c,vpf_go
	halt
vpf_go:
	ld a,KV_STK_P3
	di
	ld (vec_kv_shadow),a
	out (KV_PORT),a
	ei
	ld hl,vpf_x_next	; адрес возврата блита на весь сброс один — не на каждый слот
	ld (vec_blit_ret),hl
	ld sp,POOL_BASE+80*128+$180	; $C980 (страница 3, под музыкой, выше маркера $C800): стек для
				; call/ISR в сбросе — настоящий стек в стековом режиме портил бы квазидиск
	xor a
	ld (vec_tmp_sy),a	; текущая строка
	dec a
	ld (vec_hr_phase),a	; $FF: первый же слот — «новый круг»: герой вперёд, если влезает (или луч уже ниже)
vpf_yloop:
	ld a,(vec_tmp_sy)	; полоса грязного в строке: [xmin..xmax] из vec_slot_tab[160+y]/[176+y]
	add a,160		; (vpb_y). Строка без грязного (xmin+1 = 0) целиком пропускается.
	ld l,a
	ld h,vec_slot_tab/256
	ld a,(hl)
	or a
	jp z,vpf_ynext
	ld (hl),0
	ld c,a			; C = xmin+1
	ld a,l
	add a,16
	ld l,a
	ld a,(hl)		; xmax+1
	ld (hl),0
	sub c
	inc a
	ld (vec_tmp_bx),a	; колонок в полосе
	ld a,(vec_tmp_sy)
	rlca
	rlca
	rlca
	rlca
	add a,c
	dec a
	ld (vec_tmp_cx),a	; индекс карты = y*16 + xmin
vpf_x:
	ld a,(vec_tmp_cx)
	ld l,a
	ld h,vec_slot_tab/256
	and $f0
	ld b,a			; B = y*16
	ld a,l
	and $0f
	ld c,a			; C = колонка — vpf_slot берёт её оттуда
	ld a,(hl)
	cp POOL_SLOTS
	jp c,vpf_slot_chk
	ld (hl),$ff		; прямой ($FE) или уже выведен — вернуть «пусто» (таблица не чистится)
	ld h,vec_col_tab/256
	ld (hl),0
	jp vpf_x_next
vpf_slot_chk:
	; ГЕРОЙ — ПОЗАДИ ЛУЧА. Сброс дольше кадра, луч обгоняет его раз за круг и показывал героя
	; половиной старой позы («середина меча», tools/beam_vec.py 2026-09-04). Слоты героя [s0,s1)
	; в общем обходе пропускаются и выводятся списком (vpf_hero), когда луч прошёл его нижнюю
	; полосу либо они успевают до его прихода: кадр показывает героя целиком старым или новым.
	ld d,a
	ld a,(vec_hr_s0)	; выведенные слоты героя уже $FF — сюда не доходят
	cp d
	jp z,vpf_ge0
	jp nc,vpf_slot_go	; slot < s0
vpf_ge0:
	ld a,(vec_hr_s1)
	cp d
	jp z,vpf_slot_go	; slot >= s1
	jp c,vpf_slot_go
	jp vpf_x_next		; слот героя — позже
vpf_slot_go:
	ld a,d
vpf_slot:
	ld (hl),$ff		; слот выведен — больше не выводить (пересечения прямоугольников)
	ld e,a
	ld h,vec_col_tab/256
	ld a,(hl)
	ld (hl),0		; карта колонок чистится здесь же
	ld (vec_col_f),a
	ld a,e
	ld l,a			; адрес слота: $A000 + slot*128 (inline vec_pool_addr)
	rrca
	and $7f
	add a,POOL_BASE/256
	ld h,a
	ld a,l
	and 1
	rrca
	ld l,a
	ld sp,hl
	ld a,c			; колонка взята в vpf_x
	add a,a
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub b
	ld e,a
    if !VI53
	ld hl,(vec_bud_used)	; фаза кадра: считать и сброс (ISR обнулит при прерывании)
	ld a,l
	add a,20 - C8*4		; слот сброса: 96 Б при C8
	jp nc,vpf_bud_ok
	ld a,255
vpf_bud_ok:
	ld (vec_bud_used),a
    endif			; ВИ53: фаза всегда реальная, самоучёт сброса не нужен
	ld a,(vec_col_f)
	dec a
	jp z,vec_blit64l	; 1 — только левая колонка
	dec a
	jp z,vec_blit64r	; 2 — только правая
	jp vec_blit128_vram
vpf_x_next:
	ld a,(vec_hr_lp)	; герой не выведен: новый круг луча — герой вперёд, пока влезает, потом обратно сюда
	cp vec_hr_list & $ff
	jp z,vpf_x_adv
	call vec_hr_lap
	or a
	jp z,vpf_x_adv
	ld hl,vpf_x_adv
	ld (vec_hr_ret),hl
	jp vpf_hero
vpf_x_adv:
	ld a,(vec_tmp_cx)
	inc a
	ld (vec_tmp_cx),a
	ld a,(vec_tmp_bx)
	dec a
	ld (vec_tmp_bx),a
	jp nz,vpf_x
vpf_ynext:
	ld a,(vec_tmp_sy)
	inc a
	ld (vec_tmp_sy),a
	cp 10
	jp nz,vpf_yloop
vpf_hr_wait:			; чужие кончились, герой ждёт луча: позади него, либо впереди, если влезает
	ld a,(vec_hr_lp)	; список пуст — герой выведен (или его не было)
	cp vec_hr_list & $ff
	jp z,vpf_fin
	call vec_phase
	call vec_hr_fits
	or a
	jp z,vpf_hr_wait
	ld hl,vpf_fin
	ld (vec_hr_ret),hl
	jp vpf_hero
vpf_fin:
	ld hl,(vec_sp_save)
	ld sp,hl		; настоящий SP
	; Порт — ДО call/halt. Раньше стековый режим держался до vpf_done, и call vec_phase вместе с ISR
	; клали адреса возврата и регистры в СТРАНИЦУ 3 по адресам игрового стека ($7Dxx): симметрично
	; и потому «безопасно», но квазидиск там портился (2026-09-04: копии кадров героя 37..40 на
	; уровне 1 получали байты адреса возврата — один неверный пиксель при падении).
	ld a,(vec_kv_prev)
	di
	ld (vec_kv_shadow),a
	out (KV_PORT),a		; вернуть окно, каким его держит главный код
	ei
	call vec_phase
	cp 206
	jp c,vpf_done
	halt
vpf_done:
	xor a
	ld (ndirtyrects),a
	ld (vec_pool_on),a
	ld hl,vec_pool_clr	; пул был выключен — записи $FE/слот в карте никто не снял
	or (hl)			; A = 0 (xor a выше)
	ret z
	ld (hl),0
	jp vec_slot_init
    endif

; ---------------------------------------------------------------------------
; ПАНЕЛЬ (страница 3 квазидиска; в DEMO панели нет)
; drawChar: A = символ, B = X (символы), C = Y (символы)
drawChar:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	sub 32
	and 127
	ld e,a			; E = код символа 0..127 (64..95 кириллица, 96 стрелка)
	; кэш по ячейкам (ряды 20..23): тот же символ уже в VRAM — не рисуем.
	; Оригинал перерисовывает панель в каждом кадре ожидания (waitforVBlank), для VDP это
	; дёшево, для нас — стековый блит 4x8x4 на символ.
	ld a,c
	sub 20
	cp 4
	jp nc,dc_draw
	rrca
	rrca
	rrca			; ряд*32
	add a,b
	ld l,a
	ld h,0
	push de
	ld de,vec_pc_char
	add hl,de
	pop de
	ld a,(hl)
	cp e
	jp z,dc_skip
	ld (hl),e
dc_draw:
	ld a,e
	; src = P3_FONT + A*32
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld (vec_blit_src),hl
	ld a,b
	add a,VEC_P0H
	ld d,a
	ld a,c
	rlca
	rlca
	rlca
	ld c,a
	ld a,Y_TOP_L
	sub c
	ld e,a
	ld a,1
	ld (vec_bl_cols),a
	ld a,4
	ld (vec_bl_pops),a
	jp vec_panel_blit
dc_skip:
	pop bc
	pop de
	pop hl
	ret
    endif
; drawWeapon: A = X источника (оружие*32), B = X px, C = Y px; 24x16
drawWeapon:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	push af			; vec_pc_inv3 портит A, а в нём номер оружия*32 (иначе панель
	call vec_pc_inv3	; рисует чужой слот: выбранное оружие в HUD не менялось, 2026-09-08)
	pop af
	rrca
	rrca
	rrca
	rrca
	rrca
	and 3			; номер оружия
	ld l,a
	ld h,0
	ld d,h
	ld e,l
	add hl,hl		; *2
	add hl,de		; *3
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl		; *192
	ld de,P3_WEAPON
	add hl,de
	ld (vec_blit_src),hl
	ld a,8
	ld (vec_bl_pops),a
	jp vec_panel_blit3
    endif
; drawScoreOnOff: A = 0 выкл / 1 вкл, B = X px, C = Y px; 24x24
drawScoreOnOff:
    if DEMO
	ret
    else
	push hl
	push de
	push bc
	inc a			; 1 = выкл, 2 = вкл (0/$FF = неизвестно)
	ld e,a
	ld a,b
	rrca
	rrca
	rrca
	and $1f			; колонка
	ld l,a
	ld h,0
	push de
	ld de,vec_pc_onoff
	add hl,de
	pop de
	ld a,(hl)
	cp e
	jp z,dc_skip		; та же картинка уже в VRAM
	ld (hl),e
	call vec_pc_inv3	; 24x24 накрывает ячейки цифр — их кэш сбросить
	ld a,e
	dec a
	ld hl,P3_ONOFF
	or a
	jp z,dso_0
	ld hl,P3_ONOFF+288
dso_0:
	ld (vec_blit_src),hl
	ld a,12
	ld (vec_bl_pops),a
vec_panel_blit3:
	ld a,3
	ld (vec_bl_cols),a
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld d,a
	ld a,Y_TOP_L
	sub c
	ld e,a
; Цена блита панели. РАНЬШЕ считалось cols*pops в ОДНОМ байте и умножалось на 3/4 «за четыре
; плоскости» — у картинки панели (vec_load_panel: cols=32, pops=16, ОДНА плоскость за вызов)
; произведение 512 переполняло байт в 0, и цена выходила 32 ед. вместо реальных ~146: DI-окно
; блита накрывало обратный ход, и прерывание терялось (measure_vec: все потери на ур.6 и ур.3
; приходились на vbc_row). Теперь произведение считается в HL и в него входит ЧИСЛО ПЛОСКОСТЕЙ,
; а множитель 1/4 отвечает новой цене пары байт (68 тактов = 0.266 ед.).
vec_panel_blit:
	push bc
	ld a,(vec_bl_cols)
	ld c,a
	ld a,(vec_bl_planes)
	ld b,a
	xor a
vpn_ncol:
	add a,c			; A = cols * планостей (<= 128)
	dec b
	jp nz,vpn_ncol
	ld b,a
	ld a,(vec_bl_pops)
	ld c,a
	ld hl,0
vpn_cost:
	ld a,l			; HL = pops * cols * плоскостей (до 512 — байта не хватает)
	add a,c
	ld l,a
	jp nc,vpn_nc
	inc h
vpn_nc:
	dec b
	jp nz,vpn_cost
	ld a,h			; HL / 4
	or a
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	ld a,h
	or a
	rra
	ld h,a
	ld a,l
	rra
	add a,32		; + логика куска панели (draw_*_state, Div16_8) перед блитом — EI, но время кадра
	jp c,vpn_cap
	cp 190			; цена > предела бюджета = вечный halt: держим потолок
	jp c,vpn_ok
vpn_cap:
	ld a,190
vpn_ok:
	call vec_budget
	pop bc
	di
	ld hl,0
	add hl,sp
	ld (vec_sp_save),hl
	ld hl,(vec_blit_src)
	ld sp,hl
	ld a,KV_STK_P3
	out (KV_PORT),a
	ld hl,vpn_ret
	ld (vec_blit_ret),hl
	jp vec_blit_cols
vpn_ret:
	xor a
	out (KV_PORT),a
	ld hl,(vec_sp_save)
	ld sp,hl
	ei
	pop bc
	pop de
	pop hl
	ret
    endif
; vec_panel_blit_call: вызов vec_panel_blit как процедуры (сам он снимает hl/de/bc со стека и делает ret)
vec_panel_blit_call:
	push hl
	push de
	push bc
	jp vec_panel_blit
; vec_load_panel: картинка панели 256x32 -> строки 160..191
vec_load_panel:
    if DEMO
	ret
    else
	call vec_pc_reset
	push hl
	push de
	push bc
	ld a,VEC_NPL
	ld (vec_tmp_sx),a	; счётчик плоскостей
	ld hl,P3_PANEL
	ld d,VEC_P0H
vlp_plane:
	ld (vec_blit_src),hl
	ld a,32
	ld (vec_bl_cols),a
	ld a,16
	ld (vec_bl_pops),a
	ld a,1
	ld (vec_bl_planes),a	; одна плоскость за блит (512 pop, ~0.4 кадра) — влезает в бюджет DI
	ld e,Y_TOP_L-160
	push de
	call vec_panel_blit_call
	pop de
	ld hl,(vec_blit_src)
	ld bc,32*32
	add hl,bc		; следующая плоскость источника
	ld a,d
	add a,$20
	ld d,a
	ld a,(vec_tmp_sx)
	dec a
	ld (vec_tmp_sx),a
	jp nz,vlp_plane
	pop bc
	pop de
	pop hl
	ret
    endif
; vec_pc_reset: весь кэш панели = $FF («неизвестно»). Портит A, HL, B.
vec_pc_reset:
    if !DEMO
	ld hl,vec_pc_char
	ld b,128+32+64
vpr_l:
	ld (hl),$ff
	inc hl
	dec b
	jp nz,vpr_l
    endif
	ret
; vec_pc_inv3: сбросить кэш символов под картинкой 3x3 ячейки: B = X px, C = Y px.
; Бережёт все регистры, кроме A.
vec_pc_inv3:
	push bc
	push de
	push hl
	ld a,c
	rrca
	rrca
	rrca
	and $1f
	sub 20
	ld c,a			; ряд относительно 20 (вне 0..3 — пропуск)
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	ld b,a			; колонка
	ld d,3
vpi_r:
	ld a,c
	cp 4
	jp nc,vpi_next
	rrca
	rrca
	rrca			; ряд*32
	add a,b
	ld l,a
	ld h,0
	ld e,d
	ld de,vec_pc_char
	add hl,de
	ld d,3
	ld (hl),$ff
	inc hl
	ld (hl),$ff
	inc hl
	ld (hl),$ff
vpi_next:
	inc c
	dec d
	jp nz,vpi_r
	pop hl
	pop de
	pop bc
	ret
; fillArea / fillArea_slow: A = цвет, B = X px, C = Y px, D = ширина px, E = высота px
; Единственный клиент в игре — draw_meter (шкалы панели): цветная часть (цвет != $11) со строки
; 190-n высотой n и пустая ($11) со строки 169 высотой 21-n. Кэш по колонке: цветная — ключ Y,
; пустая — ключ высота. Полная пустая (21) или полная цветная (Y=169) накрывает соседа — его ключ
; сбрасываем, иначе после «энергия 0 -> прежняя» цветная часть посчиталась бы уже нарисованной.
fillArea:
fillArea_slow:
	push hl
	push de
	push bc
	push af
	ld (vec_fill_color),a
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,a
	ld l,a
	ld h,0
	push de			; E (высота) нужен ниже как ключ пустой части
	ld de,vec_pc_meter
	add hl,de		; HL -> [Y цветной], [высота пустой]
	pop de
	ld a,(vec_fill_color)
	cp $11
	jp z,fa_blank
	ld a,c			; цветная: ключ Y
	cp (hl)
	jp z,fa_skip
	ld (hl),a
	cp 169			; полная — пустой части не будет, её ключ сбросить
	jp nz,fa_go
	inc hl
	ld (hl),$ff
	jp fa_go
fa_blank:
	inc hl
	ld a,e			; пустая: ключ высота
	cp (hl)
	jp z,fa_skip
	ld (hl),a
	cp 21
	jp nz,fa_go
	dec hl
	ld (hl),$ff
fa_go:
	pop af
	pop bc
	pop de
	pop hl
	push hl
	push de
	push bc
    if C8
	cp $11			; «пустая» часть шкалы -> слот 0 (чёрный)
	jp nz,fa_c8map
	xor a
	jp fa_c8ok
fa_c8map:
	push hl
	ld hl,vec_color_map	; выровнена (сразу за fg_tile_lut)
	add a,l
	ld l,a
	ld a,(hl)
	pop hl
fa_c8ok:
    endif
	ld (vec_fill_color),a
	ld a,e
	ld (vec_fill_hgt),a
	or a
	jp z,fa_exit
	ld a,d
	or a
	jp z,fa_exit
	add a,b
	dec a
	ld (vec_fill_xr),a	; правый край
fa_col:
	; c0 = B&7; c1 = (xr в той же колонке) ? xr&7 : 7   (C = Y не трогаем!)
	ld a,b
	and 7
	ld e,a			; E = c0
	ld a,(vec_fill_xr)
	ld d,a
	xor b
	and $f8
	ld a,7
	jp nz,fa_c1
	ld a,d
	and 7
fa_c1:
	ld d,a			; D = c1
	; m1 = $FF >> c0
	ld a,$ff
	inc e
fa_m1:
	dec e
	jp z,fa_m1d
	or a
	rra
	jp fa_m1
fa_m1d:
	ld e,a			; E = m1
	; m2 = $FF << (7-c1)
	ld a,7
	sub d
	ld d,a
	ld a,$ff
	inc d
fa_m2:
	dec d
	jp z,fa_m2d
	add a,a
	jp fa_m2
fa_m2d:
	and e
	ld (vec_fill_mask),a
	; адрес: H = $80 + (B>>3), L = 223 - C
	ld a,b
	rrca
	rrca
	rrca
	and $1f
	add a,VEC_P0H
	ld h,a
	ld a,Y_TOP_L
	sub c
	ld l,a
	push bc
	ld a,VEC_NPL
	ld (vec_plane_cnt),a
fa_plane:
	push hl
	ld a,(vec_fill_hgt)
	ld d,a
	; бит плоскости p (p = 4 - plane_cnt) = бит (3-p) цвета = бит (plane_cnt-1)
	ld a,(vec_plane_cnt)
	ld e,a
	ld a,(vec_fill_color)
fa_bit:
	dec e
	jp z,fa_bitd
	rrca
	jp fa_bit
fa_bitd:
	and 1
	jp z,fa_clear
fa_set:
	ld a,(vec_fill_mask)
	or (hl)
	ld (hl),a
	dec l
	dec d
	jp nz,fa_set
	jp fa_plane_next
fa_clear:
	ld a,(vec_fill_mask)
	cpl
	and (hl)
	ld (hl),a
	dec l
	dec d
	jp nz,fa_clear
fa_plane_next:
	pop hl
	ld a,h
	add a,$20
	ld h,a
	ld a,(vec_plane_cnt)
	dec a
	ld (vec_plane_cnt),a
	jp nz,fa_plane
	pop bc
	; следующая байтовая колонка
	ld a,b
	or 7
	inc a
	jp z,fa_exit		; вышли за 255
	ld b,a
	ld a,(vec_fill_xr)
	cp b
	jp nc,fa_col
fa_exit:
	pop bc
	pop de
	pop hl
	ret
fa_skip:
	pop af
	pop bc
	pop de
	pop hl
	ret
