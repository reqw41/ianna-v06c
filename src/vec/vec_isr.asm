; vec_isr.asm — кадровое прерывание (RST7, VBlank) и опрос клавиатуры.
; Порядок как в рецепте анти-фликера: палитра -> клавиатура -> счётчик кадров.
; Аналог ISR оригинала: get_joystick -> joystick_state, frames_noredraw++, музыка.

vec_isr:
	push af
	push bc
	push de
	push hl
    if VI53
	; счётчик 0 ВИ53 = фаза кадра: режим 0, старт с 0 (=65536), 1.5 МГц (такт счётчика = 2 такта ЦП).
	; Выход канала 0 при счёте низкий — в микшер ничего не подмешивает; каналы 1-2 свободны под музыку.
	ld a,$30
	out ($08),a
	xor a
	out ($0B),a
	out ($0B),a
    endif
	; --- палитра (латч по лучу: пишем в VBlank, сразу после входа в ISR) — только когда изменилась
	; (vec_pal_dirty: 1 при старте и после смены палитры уровня); каждый кадр это ~1.7К тактов зря ---
	ld a,(vec_pal_dirty)
	or a
	jp z,isr_nopal
	xor a
	ld (vec_pal_dirty),a
	ld hl,vec_palette
	ld c,0
isr_pal:
	ld a,c
	out ($02),a
	ld a,(hl)
	out ($0C),a
	out ($0C),a
	out ($0C),a
	inc hl
	inc c
	ld a,c
	cp 16
	jp nz,isr_pal
isr_nopal:
	xor a			; бордюр = слот 0: он в наборе всегда чёрный («только прозрачный»,
	out ($02),a		; build_edd), а слоты 1..3 vec_scrpal меняет НА КАЖДОМ ЭКРАНЕ под
				; четырёхцветный спрайт — бордюр от этого перекрашивался (2026-09-08)
	; --- клавиатура -> joystick_state (биты: 0 up,1 down,2 left,3 right,4 fire,5 fire2) ---
	call get_joystick
	ld (joystick_state),a
	; --- H/J/X: сканируем ЗДЕСЬ, в гасящем. Порт $03 — это ещё и регистр вертикального скролла,
	; и опрос посреди кадра сдвигал картинку: экран подёргивался (get_keyboard звался каждый тик
	; из mainloop — проверка паузы). Теперь get_keyboard только читает vec_keys.
	ld a,$82		; порт B ППИ -> вход
	out ($00),a
	ld a,$DF		; ряд 5: H = бит 0, J = бит 2; читы: I = бит 1, L = бит 4
	out ($03),a
	in a,($02)
	cpl
	ld b,a
	and $05
	ld c,a
	ld a,b
	and $12
	ld b,a
	ld a,$EF		; ряд 4: G = бит 7 -> бит 0
	out ($03),a
	in a,($02)
	cpl
	rlca
	and 1
	or b
	ld b,a			; B = клавиши читов сейчас
	ld hl,vec_ckprev	; срабатывание по НАЖАТИЮ считаем здесь, а не в тике: тик бывает длиннее
	ld a,(hl)		; короткого нажатия, и клавиша терялась бы
	ld (hl),b
	cpl
	and b
	ld hl,vec_ckeys
	or (hl)
	ld (hl),a		; защёлка: тик заберёт и обнулит
	ld a,$7F		; ряд 7: X = бит 0 -> кладём в бит 3
	out ($03),a
	in a,($02)
	cpl
	rlca			; бит 0 -> бит 3 (три сдвига). Был лишний rrca перед ними: бит уезжал в
	rlca			; бит 2, `and $08` давал ноль ВСЕГДА — выход из паузы по X не работал
	rlca			; (2026-09-08, жалоба владельца «не выйти из паузы»).
	and $08
	or c
	ld (vec_keys),a
	ld a,$80		; вернуть режим ППИ, бордюр и скролл
	out ($00),a
	ld a,1
	out ($02),a
	ld a,$FF
	out ($03),a
	; хук клавиатуры (экран пароля): сканирование только здесь, в VBlank — порт $03 это ещё и
	; вертикальный скролл, дёргать его посреди кадра нельзя (картинка подпрыгивает)
	ld hl,(vec_key_hook)
	ld a,h
	or l
	jp z,isr_nokey
	call isr_hook_call
isr_nokey:
	; --- счётчик кадров без перерисовки ---
	ld a,(frames_noredraw)
	inc a
	ld (frames_noredraw),a
	ld hl,(FrameCounter)
	inc hl
	ld (FrameCounter),hl
    if !DEMO
	; --- музыка: как в ISR оригинала (mzk_subroutine -> MUSIC_Play), но данные в квазидиске ---
	ld a,(music_playing)
	or a
	jp z,isr_nomusic
	; сохранить ячейки эмуляции Z80 (главный код мог быть прерван внутри хелпера): холодная часть
	; плеера трогает только z_ix, z_a, z_ret (+ z_iy/z_tmp рядом) — 8 байт z_ix..z_ret, без циклов
	ld hl,(z_ix)
	ld (vec_zsave),hl
	ld hl,(z_iy)
	ld (vec_zsave+2),hl
	ld hl,(z_a)
	ld (vec_zsave+4),hl
	ld hl,(z_ret)
	ld (vec_zsave+6),hl
	ld a,(vec_kv_shadow)
	and $1c			; сохранить стековые биты: сброс пула идёт с EI, стек — в странице 3
	or KV_WIN_MUSIC
	out (KV_PORT),a
	call MUSIC_Play
	ld a,(vec_kv_shadow)
	out (KV_PORT),a
	ld hl,(vec_zsave)
	ld (z_ix),hl
	ld hl,(vec_zsave+2)
	ld (z_iy),hl
	ld hl,(vec_zsave+4)
	ld (z_a),hl
	ld hl,(vec_zsave+6)
	ld (z_ret),hl
isr_nomusic:
    endif
    if !VI53
	ld a,VEC_ISR_COST
	ld (vec_bud_used),a	; бюджет DI (программный): фаза кадра на выходе из ISR
    endif
	pop hl
	pop de
	pop bc
	pop af
	ei
	ret

; ---------------------------------------------------------------------------
; ПРЕРЫВАНИЕ ВО ВРЕМЯ СПРАЙТА В ПУЛ (drawSprite_pool, прямой кадр; вектор $0039 смотрит сюда от dsp_enter
; до dsp_leave_di). Порт в стековом режиме, SP — указатель в кадре: RST уже положил адрес возврата в два
; байта кадра под SP. Забираем его, уходим на настоящий стек (vec_sp_save) и зовём обычную ISR, на
; выходе возвращаем на место затёртую пару: по адресу возврата таблица isr_fix_tab говорит, где она
; (регистры, HL, ячейка isr_pair). Флаги прерванного кода живы: перенос — через jp c/scf, остальное —
; команды без флагов.
; Режим — байт: $FF нет пары (DI), $FE isr_pair, $FD HL; иначе два полубайта — источник старшего и
; младшего байта пары: 0 B, 1 C, 2 D, 3 E, 8 A (isr_a), +4 байт лежит РАЗВЁРНУТЫМ через rev256
; (зеркальные тела разворачивают пару прямо в регистрах; разворот — инволюция, починка разворачивает обратно).
ISF_NONE	equ $FF
ISF_MEM		equ $FE
ISF_HL		equ $FD
ISF_BC		equ $01		; младший C, старший B
ISF_DE		equ $23		; младший E, старший D
ISF_rCB		equ $05		; младший rev(C), старший B
ISF_rCrB	equ $45
ISF_EC		equ $13
ISF_rEC		equ $17
ISF_rBrC	equ $54
ISF_EB		equ $03
ISF_rEB		equ $07
ISF_rBC		equ $14
ISF_rAE		equ $3C
ISF_rCE		equ $35
ISF_rCrE	equ $75
isr_spr:
	ld (isr_hl),hl
	pop hl			; адрес возврата — из страницы квазидиска
	ld (isr_ret+1),hl
	ld (isr_a),a
	ld a,0			; не xor: флаги ещё не сохранены
	out (KV_PORT),a		; стековый режим выкл.: дальше настоящий стек
	ld hl,0
	jp c,isrs_c
	add hl,sp		; add hl,sp трогает только перенос
	jp isrs_sp
isrs_c:
	add hl,sp
	scf
isrs_sp:
	ld (isr_sp),hl		; SP прерванного блита (адрес возврата уже снят)
	ld hl,(vec_sp_save)
	ld sp,hl
	ld a,(isr_a)
	push af			; флаги и регистры прерванного блита — до конца, починке нужны BC и DE
	push bc
	push de
	ld hl,isr_spr_back
	push hl
	ld hl,(isr_hl)
	jp vec_isr		; сразу: она перезаряжает счётчик фазы ВИ53, задержка сдвинула бы фазу кадра
isr_spr_back:			; ret обычной ISR (после её ei — до следующего кадра прерываний не будет)
	di
	; режим починки: первая запись таблицы с концом диапазона больше адреса возврата
	ld hl,isr_fix_tab
isrs_find:
	ld a,(isr_ret+1)
	sub (hl)
	inc hl
	ld a,(isr_ret+2)
	sbc a,(hl)
	inc hl
	jp c,isrs_hit
	inc hl
	jp isrs_find
isrs_hit:
	ld a,(hl)
	cp ISF_NONE
	jp z,isrs_none
	ld hl,(isr_pair)
	cp ISF_MEM
	jp z,isrs_set
	ld hl,(isr_hl)
	cp ISF_HL
	jp z,isrs_set
	push af			; полубайты: старший байт, потом младший (isrs_byte портит HL)
	rrca
	rrca
	rrca
	rrca
	call isrs_byte
	pop hl			; H = режим
	push af			; старший байт пары — на стек
	ld a,h
	call isrs_byte
	pop hl			; H = старший байт
	ld l,a
isrs_set:
	ld (isr_pv),hl
	ld hl,isrb_fix
	jp isrs_go
isrs_none:
	ld hl,isrb_go
isrs_go:
	ld (isrb_sw+1),hl
	pop de
	pop bc
	pop af			; HL прерванного кода — в isr_hl (с входа)
	ld (isr_a),a
	ld hl,(isr_sp)
	ld sp,hl
	ld a,(vec_spr_curport)
	out (KV_PORT),a		; снова стековый режим блита
isrb_sw:
	jp isrb_fix		; самомодификация: isrb_fix / isrb_go
isrb_fix:
	ld hl,(isr_pv)
	push hl			; пара — на место адреса возврата
	inc sp
	inc sp
isrb_go:
	ld a,(isr_a)
	ld hl,(isr_hl)
	ei
isr_ret:
	jp 0			; самомодификация: адрес возврата

; isrs_byte (декодер байта пары) живёт в окне $6AB0 — vec_hi.asm

isr_hl:		dw 0
isr_sp:		dw 0
isr_pv:		dw 0
isr_pair:	dw 0		; пара под SP там, где её нет в регистрах (диапазоны [isr_pair] в коде блита)
isr_a:		db 0

; Диапазоны кода спрайта в пул: (конец диапазона, не включая; где пара под SP). Порядок — по адресам,
; метки — из разметки «---- [..]» в vec_vdp.asm. Адрес возврата = команда, которая ещё не исполнена.
isr_fix_tab:
	dw dtb_ei		; до ei тайла в слот — DI
	db ISF_NONE
	dw dtb_ei_end		; тайл в слот: пара под SP всегда в BC
	db ISF_BC
	dw dbk_ei		; до ei чёрного тайла в слот — DI
	db ISF_NONE
	dw dbk_ei_end		; чёрный тайл в слот: пара под началом слота
	db ISF_MEM
	dw dfb_ei		; до ei переднего тайла в слот — DI
	db ISF_NONE
	dw dfb_ei_end		; передний тайл в слот: пара в BC
	db ISF_BC
	dw dsp_col		; до пролога первой колонки — DI
	db ISF_NONE
	dw dsp_row_e1		; пролог колонки/сегмента и pop bc входа
	db ISF_MEM
	dw dsp_row		; jp после pop bc входа
	db ISF_BC
	dw dsp_row_pd		; pop bc строки: пара от третьего pop de прошлой строки
	db ISF_DE
	dw dsp_row_de		; pop de
	db ISF_BC
	dw dsp_sk_m		; тело строки, конец сегмента, пропуск до ld sp,hl включительно
	db ISF_DE
	dw dsp_sk_b		; после прыжка SP пропуска
	db ISF_MEM
	dw dsp_seg_end		; jp после pop bc пропуска
	db ISF_BC
	dw dsp_seg_end_h	; ex de,hl
	db ISF_DE
	dw dsp_seg_end_m	; ld (isr_pair),hl
	db ISF_HL
	dw dsp_leave_di+1	; конец сегмента, хвост колонки, выход до di включительно
	db ISF_MEM
	; зеркальный четырёхплоскостной путь (dsp_mirror)
	dw dspm_ei+1		; пролог зеркала до ei — DI
	db ISF_NONE
	dw dspm_row_e1		; пролог колонки/сегмента и pop bc входа
	db ISF_MEM
	dw dspm_row		; jp входа
	db ISF_BC
	dw dspm_row_bc		; ld d / pop bc строки: пара прошлой строки
	db ISF_rEC
	dw dspm_row_rc
	db ISF_BC
	dw dspm_row_rcb
	db ISF_rCB
	dw dspm_row_de		; плоскость 0, pop de
	db ISF_rCrB
	dw dspm_row_ec
	db ISF_DE
	dw dspm_row_ae
	db ISF_EC
	dw dspm_row_ce
	db ISF_rAE
	dw dspm_row_cre
	db ISF_rCE
	dw dspm_row_de2		; плоскости 1-2, pop de
	db ISF_rCrE
	dw dspm_row_ec2
	db ISF_DE
	dw dspm_row_rec2
	db ISF_EC
	dw dspm_sk_m		; плоскость 3, конец строки, пропуск до ld sp,hl включительно
	db ISF_rEC
	dw dspm_sk_b		; после прыжка SP, pop bc
	db ISF_MEM
	dw dspm_seg_end		; jp после pop bc пропуска
	db ISF_BC
	dw dspm_seg_end_e
	db ISF_rEC
	dw dspm_seg_end_d
	db ISF_EC
	dw dspm_seg_end_h
	db ISF_DE
	dw dspm_seg_end_m
	db ISF_HL
	dw dspm_leave_end	; конец сегмента, хвост (через dsp_tail), выход
	db ISF_MEM
	dw b2p_row_e		; между путями кода нет
	db ISF_NONE
	dw b2p_row_e1		; pop bc входа
	db ISF_MEM
	dw b2p_row_de		; jp входа, pop bc и pop de строки A
	db ISF_BC
	dw b2p_rowb_bc		; строка A, pop bc строки B
	db ISF_DE
	dw b2p_skipA		; строка B, конец сегмента на границе пары
	db ISF_BC
	dw b2p_skipB
	db ISF_DE
	dw b2p_split
	db ISF_BC
	dw b2p_split_h		; разрыв пары до ex de,hl включительно
	db ISF_DE
	dw b2p_split_m
	db ISF_HL
	dw b2p_cont_b		; переход и pop bc продолжения
	db ISF_MEM
	dw b2p_cont_end
	db ISF_BC
	; зеркальное двухплоскостное тело (b2pm_row_e): до него кода под EI нет
	dw b2pm_row_e1		; pop bc входа
	db ISF_MEM
	dw b2pm_row		; jp входа
	db ISF_BC
	dw b2pm_row_bc		; ld d / pop bc строки A: пара от строки B
	db ISF_rCB
	dw b2pm_row_rc
	db ISF_BC
	dw b2pm_row_rcb
	db ISF_rCB
	dw b2pm_row_de		; плоскости 0-2 строки A, pop de
	db ISF_rCrB
	dw b2pm_row_ec
	db ISF_DE
	dw b2pm_row_rec
	db ISF_EC
	dw b2pm_rowb_b		; плоскость 3 строки A, cp, ld b,e
	db ISF_rEC
	dw b2pm_rowb_rc
	db ISF_rBC
	dw b2pm_rowb_de		; pop de строки B
	db ISF_rBrC
	dw b2pm_rowb_eb
	db ISF_DE
	dw b2pm_rowb_reb
	db ISF_EB
	dw b2pm_rowb_rcb	; плоскости 0-2 строки B, ld c,e / ld e,b
	db ISF_rEB
	dw b2pm_endB_h		; плоскость 3 строки B, cp, пара -> HL
	db ISF_rCB
	dw b2pm_endB_m
	db ISF_HL
	dw b2pm_split
	db ISF_MEM
	dw b2pm_cont		; разрыв пары
	db ISF_rEC
	dw b2pm_cont_end	; продолжение пары из isr_pair
	db ISF_MEM
	dw $FFFF
	db ISF_NONE

; get_joystick: A = состояние. Матрица Вектора: out(3)=~(1<<ряд), in(2) — активный 0.
; ряд 0: б7 вниз, б6 вправо, б5 вверх, б4 влево;  ряд 7: б7 пробел, б2 Z, б0 X.
; ПОРТ 3 = ТАКЖЕ ВЕРТИКАЛЬНЫЙ СКРОЛЛ — после опроса обязательно вернуть $FF.
get_joystick:
	ld a,$82		; ППИ: порт B -> ВХОД (иначе in(2) отдаёт защёлку = «всё нажато»)
	out ($00),a
	ld a,$FE		; ряд 0
	out ($03),a
	in a,($02)
	cpl
	ld b,a			; B: б7 down, б6 right, б5 up, б4 left (1 = нажато)
	ld c,0
	ld a,b
	and $20
	jp z,gj_1
	ld c,1			; up
gj_1:
	ld a,b
	and $80
	jp z,gj_2
	ld a,c
	or 2			; down
	ld c,a
gj_2:
	ld a,b
	and $10
	jp z,gj_3
	ld a,c
	or 4			; left
	ld c,a
gj_3:
	ld a,b
	and $40
	jp z,gj_4
	ld a,c
	or 8			; right
	ld c,a
gj_4:
	ld a,$FD		; ряд 1: СТОП (бит 2) — выход в меню
	out ($03),a
	in a,($02)
	cpl
	ld b,a			; (направления уже собраны в C)
	and $28			; F1 (бит 3) + F3 (бит 5) вместе, вне игры — включить режим читов
	cp $28
	jp nz,gj_nocheat
	ld a,(vec_in_game)
	or a
	jp nz,gj_nocheat
	inc a
	ld (vec_cheat),a
gj_nocheat:
	ld a,b
	and $04
	jp z,gj_r7
	ld a,(vec_in_game)	; вне игры (меню/интро) клавишу игнорируем
	or a
	jp z,gj_r7
	ld a,2
	ld (player_dead),a	; движок сам выйдет из game; vec_main вернёт в меню
gj_r7:
	ld a,$7F		; ряд 7
	out ($03),a
	in a,($02)
	cpl
	ld b,a
	ld a,$80		; ППИ: порт B -> ВЫХОД (mode512 держим в 0, полосы на железе)
	out ($00),a
	xor a
	out ($02),a		; режим 256 точек
	ld a,$FF
	out ($03),a		; вернуть скролл! (mode set сбросил защёлки)
	ld a,b
	and $84			; пробел или Z
	jp z,gj_5
	ld a,c
	or $10			; fire
	ld c,a
gj_5:
	ld a,b
	and $01			; X
	jp z,gj_6
	ld a,c
	or $20			; fire2 (action)
	ld c,a
gj_6:
	; Действие (X) — ОДНО СРАБАТЫВАНИЕ НА НАЖАТИЕ, как get_opqa_end оригинала (input.asm).
	; script_player ставит action_ack=1, как только увидел бит 5; пока кнопку держат, опрос
	; обязан этот бит гасить и сбросить action_ack только после отпускания. Без этого удержание X
	; на порте раз за разом доставало и убирало меч (локстеп с оригиналом, сцена голема 2026-09-07:
	; тики 25..29, joystick_state 32 против 0, состояние героя 36/0/34 против 38).
	ld a,(action_ack)
	or a
	ld a,c			; mov a,c флаги не трогает — Z ещё от or a
	ret z			; подтверждения не было: отдаём как есть
	and $20
	jp nz,gj_mask		; кнопку всё ещё держат — бит гасим
	ld (action_ack),a	; A=0: кнопку отпустили, разрешаем следующее действие
	ld a,c
	ret
gj_mask:
	ld a,c
	and $DF
	ret

isr_hook_call:
	jp (hl)

; get_keyboard: HL = код клавиши MSX -> A != 0, если клавиша нажата.
KEY_H_CODE	equ $2003
KEY_J_CODE	equ $8003
KEY_X_CODE	equ $2005
get_keyboard:			; читает маску, снятую в ISR: порт $03 (он же скролл) здесь не трогаем
	ld a,(vec_keys)
	ld b,a
	ld a,h
	cp KEY_J_CODE>>8
	jp nz,gk_hx
	ld a,l
	cp KEY_J_CODE&255
	jp nz,gk_no
	ld a,b
	and $04
	ret
gk_hx:				; у H и X старший байт одинаков ($20)
	cp KEY_H_CODE>>8
	jp nz,gk_no
	ld a,l
	cp KEY_H_CODE&255
	ld a,b
	jp z,gk_h
	ld a,l
	cp KEY_X_CODE&255
	jp nz,gk_no
	ld a,b
	and $08
	ret
gk_h:
	and $01
	ret
gk_no:
	xor a
	ret
