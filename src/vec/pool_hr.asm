;;; pool_hr.asm — сброс пула: герой позади луча, зеркальный блит из нулевой страницы.
;;; Жили в зазоре перед выравниванием таблиц плеера (arkos_hot.asm); плеер 2026-10-12 уехал в квазидиск
;;; (оверлей arkos.bin, страница 3, ARK_ADDR), а эти процедуры зовутся из блитов и остаются в ROM.
;;; ---- сброс пула: герой позади луча (vec_vdp.asm, vpf_slot_chk) — в зазоре перед выравниванием ----
; A = фаза → A = 1, если слоты героя можно писать сейчас: луч уже ниже героя (фаза ≥ dl1) либо
; они успеют до его прихода (фаза + цена < dl0). Иначе 0. Портит HL.
vec_hr_fits:
	ld hl,vec_hr_dl1
	cp (hl)
	jp nc,vhf_yes
	ld hl,vec_hr_cost
	add a,(hl)
	jp c,vhf_no
	ld hl,vec_hr_dl0
	cp (hl)
	jp c,vhf_yes
vhf_no:
	xor a
	ret
vhf_yes:
	ld a,1
	ret
; Детектор круга: фаза упала относительно прошлого слота — луч пошёл сверху. A = 1, если герою
; пора вперёд (vec_hr_fits). Портит HL.
vec_hr_lap:
	call vec_phase
	ld hl,vec_hr_phase
	cp (hl)
	ld (hl),a
	jp nc,vhl_no
	jp vec_hr_fits
vhl_no:
	xor a
	ret
; Раздача слотов: цена слотов героя и дедлайны луча (DE = спрайт 0). Портит A, B, HL.
vpb_hr_calc:
	ld a,(vec_hr_lp)	; цена = 14 ед. на слот списка (слот сброса ≈ 3450 тактов)
	sub vec_hr_list & $ff
	ld b,a
	add a,a
	add a,a
	add a,a
	add a,a
	sub b
	sub b
	add a,30		; + прерывание с музыкой (24) внутри записи и накладные
	ld (vec_hr_cost),a
	ld hl,4			; y спрайта → дедлайны луча: верх 54 + (y&$F0)*3/4, низ 66 + ((y+31)&$F0)*3/4
	add hl,de
	ld a,(hl)
	and $f0
	rrca
	rrca
	ld b,a
	add a,a
	add a,b
	add a,54
	ld (vec_hr_dl0),a
	add a,36		; низ: три полосы вниз от верха (спрайт 32 px + невыровненный y) — с запасом
	ld (vec_hr_dl1),a
	ret
; Герой: расширить прямоугольник раздачи на ±2 колонки — стайлы росчерка меча (спрайт 3, ±24 px)
; попадают в его слоты и выводятся вместе с ним. C = sx0, E = sx1 (с обрезкой по полю).
vpb_hr_widen:
	ld a,c
	sub 2
	jp c,vhw_c
	ld c,a
vhw_c:
	ld a,e
	add a,2
	cp 16
	jp nc,vhw_e
	ld e,a
vhw_e:
	ret
; Зеркальный двухплоскостной блит живёт в НУЛЕВОЙ СТРАНИЦЕ (zp_blit2m.asm, копия кладётся в
; vec_load_leveltab). Если копия не удалась и там нули, прыжок туда уводил процессор исполнять
; пустоту: машина умирала намертво, экран в мусоре, клавиши не отвечают (жалоба 2026-09-09,
; причина порчи пока не найдена). Проверяем первый байт копии — у неё это `ld a,(...)` = $3A;
; при негодной копии рисуем прямым путём: кадр выйдет не зеркальным, зато игра живёт.
vec_zpm:
	ld a,(ZP_BLIT2M)
	cp $3A
	jp nz,vec_blit2
	ld a,150		; зеркальный: 146 ед. на 32 строки (blitcost), бюджета по колонкам в нём нет
	call vec_budget
	jp ZP_BLIT2M

; Вывод слотов героя списком (vec_hr_list..vec_hr_lp): блит каждого через vpf_slot, возврат
; через vec_blit_ret = vpf_hr_next; в конце — по vec_hr_ret (начало обхода / после слота / конец).
vpf_hero:
	ld hl,vpf_hr_next
	ld (vec_blit_ret),hl
	ld hl,vec_hr_list
	ld (vec_hr_i),hl
vpf_hr_next:
	ld hl,(vec_hr_i)
	ld a,(vec_hr_lp)	; список короче страницы — хватает младшего байта
	cp l
	jp z,vpf_hr_done
	ld a,(hl)		; индекс таблицы слотов: row16|cx
	inc hl
	ld (vec_hr_i),hl
	ld l,a
	ld h,vec_slot_tab/256
	and $f0
	ld b,a
	ld a,l
	and $0f
	ld c,a
	ld a,(hl)
	cp POOL_SLOTS
	jp nc,vpf_hr_next	; уже выведен/прямой
	jp vpf_slot
vpf_hr_done:
	ld hl,vpf_x_next
	ld (vec_blit_ret),hl
	ld hl,vec_hr_list	; список пуст = герой выведен
	ld (vec_hr_lp),hl
	ld hl,(vec_hr_ret)
	jp (hl)

