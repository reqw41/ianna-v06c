;;; arkos_hot.asm — плеер Arkos Tracker 1 для Вектора-06Ц, НАТИВНЫЙ i8080.
;;;
;;; Написан НЕ переводом Z80-исходника, а по исполняемой спецификации tools/arkos_model.py
;;; (она, в свою очередь, сверена побитово с оригиналом ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm
;;; на всех 13 песнях по 6200 кадров и на всех 21 эффекте). Формат .mus не менялся.
;;;
;;; Чем отличается от перевода, который тут был раньше:
;;;  * нет эмуляции Z80: ни IX/IY (через ячейки-указатели ps_freqp/ps_volp), ни второго набора
;;;    регистров (exx), ни 16-битных сдвигов по цепочке srl/rr;
;;;  * состояние каналов — плоские структуры в памяти, а не самомодифицируемые операнды;
;;;  * питч трека почти всегда нулевой (93 % каналокадров на песнях игры) — заведён флаг tN_pon,
;;;    и на быстрой ветке сдвиг питча не считается вовсе;
;;;  * таблица периодов разложена на две страничные половины (младшие/старшие байты), выборка
;;;    периода — 5 команд без умножения индекса на 2.
;;;
;;; ЧТО СОЗНАТЕЛЬНО НЕ РЕАЛИЗОВАНО (перепись данных: tools/arkos_model.py --census, гейт
;;; --check-unused падает, если это появится в .mus):
;;;   Software Dependent и Hardware Dependent (аппаратная огибающая, привязанная к тону) —
;;;   в песнях и эффектах Ianna не встречаются ни разу. Ветка помечена ps_h_dependent и просто
;;;   возвращает «звука нет».
;;; Реализовано, хотя встречается редко: Independent (3 раза в эффекте 19, FX_LONGJUMP —
;;; единственное место, где вообще трогаются R11/R12/R13), retrig R13 (в данных не встречается),
;;; дигидрам спец-трека (оригинал пишет его в мёртвую ячейку — здесь просто игнорируется).
;;;
;;; Интерфейс (его зовут music.asm и игра): atInit (DE = адрес песни), atPlay, atStop,
;;; atSfxInit (DE = адрес эффектов), atSfxPlay (A=канал, L=номер, H=громкость, E=нота,
;;; D=скорость, BC=питч), atSfxStopAll, atSfxStop (A=канал). Плюс теневые байты
;;; _atVAR_Reg6/_atVAR_Reg11/_atVAR_Reg12 — их гасит сама игра после MUSIC_Load из LoadScreen.
;;;
;;; Гейты: tests/music/check.sh и tests/music/check_all.py (поток AY 1:1 с Z80-оригиналом),
;;; tools/aydump.py + tools/arkos_model.py --check-game (то же в игре).

_atDEF_R13Retrig	equ $FE		; значение-«замок» R13, заставляющее перезапустить огибающую
VI_THR			equ 4		; ВИ53: кадры эффекта тише этой громкости — тишина

;;; ============================== atPlay: один кадр ==============================
atPlay:
	ld a,(at_songctr)
	dec a
	jp nz,ap_keepspeed
	call at_readrow			; линкер, спец-трек, три трека
	ld a,(at_songspeed)
ap_keepspeed:
	ld (at_songctr),a

;;; ------------------------------ канал 3 ------------------------------
	ld a,(t3_pon)
	or a
	jp nz,ch3_pslow
	ld (ps_pitch),a			; питч канала нулевой (A = 0)
	ld (ps_pitch+1),a
ch3_pgo:
	ld hl,(t3_note)			; L = нота, H = инвертированная громкость
	ex de,hl			; D = громкость, E = нота
	ld hl,(t3_iptr)
	call ps_sound
	jp c,ch3_nofreq
	ex de,hl
	ld (ay_r0+4),hl			; период канала 3 -> R4,R5
	ex de,hl
ch3_nofreq:
	ld a,(ps_vol)
	ld (ay_r0+10),a			; громкость канала 3 -> R10
	ld a,(t3_ictr)			; шаг инструмента: указатель двигаем только по счётчику
	dec a
	jp nz,ch3_nofwd
	ld (t3_iptr),hl
	ld a,(t3_ispeed)
ch3_nofwd:
	ld (t3_ictr),a
	ld a,(s3_instr+1)		; эффект на канале 3? (адрес всегда >= $D980, хватает старшего байта)
	or a
	jp z,ch3_nosfx
	ld hl,(s3_pitch)
	ld (ps_pitch),hl
	ld hl,(s3_note)
	ex de,hl
	ld hl,(s3_instr)
	ld a,1
	ld (ps_sfx),a
	call ps_sound
	jp c,ch3_snofreq
	ex de,hl
	ld (ay_r0+4),hl
	ex de,hl
ch3_snofreq:
	ld a,(ps_vol)
	ld (ay_r0+10),a
	xor a
	ld (ps_sfx),a
	ld a,h				; адрес 0 = инструмент эффекта кончился
	or l
	jp z,ch3_ssetinstr
	ld a,(s3_sctr)
	dec a
	jp nz,ch3_snofwd
ch3_ssetinstr:
	ld (s3_instr),hl
	ld a,(s3_speed)
ch3_snofwd:
	ld (s3_sctr),a
ch3_nosfx:
	ld a,(ps_ixl)			; регистр 7: биты канала 3 идут на позиции 2
	add a,a
	add a,a
	ld (ps_r7),a

;;; ------------------------------ канал 2 ------------------------------
	ld a,(t2_pon)
	or a
	jp nz,ch2_pslow
	ld (ps_pitch),a
	ld (ps_pitch+1),a
ch2_pgo:
	ld hl,(t2_note)
	ex de,hl
	ld hl,(t2_iptr)
	call ps_sound
	jp c,ch2_nofreq
	ex de,hl
	ld (ay_r0+2),hl			; период канала 2 -> R2,R3
	ex de,hl
ch2_nofreq:
	ld a,(ps_vol)
	ld (ay_r0+9),a			; громкость канала 2 -> R9
	ld a,(t2_ictr)
	dec a
	jp nz,ch2_nofwd
	ld (t2_iptr),hl
	ld a,(t2_ispeed)
ch2_nofwd:
	ld (t2_ictr),a
	ld a,(s2_instr+1)
	or a
	jp z,ch2_nosfx
	ld hl,(s2_pitch)
	ld (ps_pitch),hl
	ld hl,(s2_note)
	ex de,hl
	ld hl,(s2_instr)
	ld a,1
	ld (ps_sfx),a
	call ps_sound
	jp c,ch2_snofreq
	ex de,hl
	ld (ay_r0+2),hl
	ex de,hl
ch2_snofreq:
	ld a,(ps_vol)
	ld (ay_r0+9),a
	xor a
	ld (ps_sfx),a
	ld a,h
	or l
	jp z,ch2_ssetinstr
	ld a,(s2_sctr)
	dec a
	jp nz,ch2_snofwd
ch2_ssetinstr:
	ld (s2_instr),hl
	ld a,(s2_speed)
ch2_snofwd:
	ld (s2_sctr),a
ch2_nosfx:
	ld a,(ps_ixl)
	add a,a
	ld b,a
	ld a,(ps_r7)
	or b
	ld (ps_r7),a

;;; ------------------------------ канал 1 ------------------------------
	ld a,(t1_pon)
	or a
	jp nz,ch1_pslow
	ld (ps_pitch),a
	ld (ps_pitch+1),a
ch1_pgo:
	ld hl,(t1_note)
	ex de,hl
	ld hl,(t1_iptr)
	call ps_sound
	jp c,ch1_nofreq
	ex de,hl
	ld (ay_r0),hl			; период канала 1 -> R0,R1
	ex de,hl
ch1_nofreq:
	ld a,(ps_vol)
	ld (ay_r0+8),a			; громкость канала 1 -> R8
	ld a,(t1_ictr)
	dec a
	jp nz,ch1_nofwd
	ld (t1_iptr),hl
	ld a,(t1_ispeed)
ch1_nofwd:
	ld (t1_ictr),a
	ld a,(s1_instr+1)
	or a
	jp z,ch1_nosfx
	ld hl,(s1_pitch)
	ld (ps_pitch),hl
	ld hl,(s1_note)
	ex de,hl
	ld hl,(s1_instr)
	ld a,1
	ld (ps_sfx),a
	call ps_sound
	jp c,ch1_snofreq
	ex de,hl
	ld (ay_r0),hl
	ex de,hl
ch1_snofreq:
	ld a,(ps_vol)
	ld (ay_r0+8),a
	xor a
	ld (ps_sfx),a
	ld a,h
	or l
	jp z,ch1_ssetinstr
	ld a,(s1_sctr)
	dec a
	jp nz,ch1_snofwd
ch1_ssetinstr:
	ld (s1_instr),hl
	ld a,(s1_speed)
ch1_snofwd:
	ld (s1_sctr),a
ch1_nosfx:
	ld a,(ps_ixl)
	ld b,a
	ld a,(ps_r7)
	or b
	jp at_ay3update

; медленная ветка питча: питч трека += приращение, ps_pitch = питч >> 2 (арифметически).
ch3_pslow:
	ld hl,t3_pitch
	call ps_pitchcalc
	jp ch3_pgo
ch2_pslow:
	ld hl,t2_pitch
	call ps_pitchcalc
	jp ch2_pgo
ch1_pslow:
	ld hl,t1_pitch
	call ps_pitchcalc
	jp ch1_pgo

; HL -> tN_pitch (dw питч, dw приращение). Ниже 7 % каналокадров — скорость не важна.
ps_pitchcalc:
	ld (ps_pblk),hl
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a				; HL = приращение
	add hl,de
	ex de,hl			; DE = новый питч
	ld hl,(ps_pblk)
	ld (hl),e
	inc hl
	ld (hl),d
	ex de,hl			; HL = питч
	ld a,h				; >>1 арифметически
	rla
	ld a,h
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	ld a,h				; ещё раз
	rla
	ld a,h
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	ld (ps_pitch),hl
	ret

;;; ============================== вывод в AY ==============================
; Вход: A = значение регистра 7 (сборка из битов каналов).
at_ay3update:
	and $BF				; бит 6 = 0, бит 7 = 1 (как в оригинале)
	or $80
	ld (ay_r0+7),a
	ld hl,ay_r0
	xor a
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,1
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,2
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,3
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,4
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,5
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,6
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,7
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,8
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,9
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,10
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,11
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,12
	out ($15),a
	ld a,(hl)
	out ($14),a
	inc hl
	ld a,13				; R13 пишется только при СМЕНЕ формы огибающей
	out ($15),a
	ld a,(hl)
	ld hl,ps_r13lock
	cp (hl)
	jp z,vi_tick
	ld (hl),a
	out ($14),a
;;; ВИ53 вместо AY: только когда AY нет (ay_none, ark_init -> ay_detect). Звучит эффект канала 2 (B — на
;;; нём играет FX_Play) на счётчике 2 ВИ53, музыка молчит. Громкости у ВИ53 нет: тихие кадры (ниже
;;; VI_THR) — тишина. Тон — меандр той же высоты (делитель = период AY * 55/4), шум — меандр случайной
;;; высоты (1,2–5,8 кГц), тем ниже, чем больше период шума. Счётчики 0 и 1 не трогаются.
vi_tick:
	ld a,(ay_none)
	or a
	ret z
	ld a,(s2_instr+1)		; 0 = эффекта нет (адреса инструментов $D9xx и выше)
	or a
	jp z,vi_mute
	ld a,(ay_r0+9)			; 0..15, 16 = огибающая (громко)
	cp VI_THR
	jp c,vi_mute
	ld a,(ay_r0+7)
	rra
	rra				; CY = бит 1: тон канала B выключен
	jp nc,vi_tone
	and 4				; бит 4 (шум B выключен) — теперь бит 2
	jp nz,vi_mute
	ld a,(_atVAR_Reg6)		; шум: делитель = (период шума / 8 + 1) * 256 + случайный байт
	rrca
	rrca
	rrca
	and 3
	inc a
	ld h,a
	ld a,(vi_rnd)			; x*5+1
	ld b,a
	add a,a
	add a,a
	add a,b
	inc a
	ld (vi_rnd),a
	ld l,a
	jp vi_out
vi_tone:
	ld hl,(ay_r0+2)
	ld a,h
	and $0f
	ld h,a
	ld d,h
	ld e,l				; DE = P
	add hl,hl
	ld b,h
	ld c,l				; BC = 2P
	add hl,hl
	add hl,hl
	add hl,hl
	ld a,l
	sub c
	ld l,a
	ld a,h
	sbc a,b
	ld h,a				; HL = 14P
	or a
	ld a,d
	rra
	ld d,a
	ld a,e
	rra
	ld e,a
	or a
	ld a,d
	rra
	ld d,a
	ld a,e
	rra
	ld e,a				; DE = P/4
	ld a,l
	sub e
	ld l,a
	ld a,h
	sbc a,d
	ld h,a				; HL = 13,75P
	jp vi_out

;;; ============================== звук одного канала ==============================
; Вход:  HL = указатель на данные инструмента, D = инвертированная громкость, E = нота,
;        ps_pitch = питч трека (word), ps_sfx = 1, если это эффект.
; Выход: HL = новый указатель (0 = звук эффекта кончился), DE = частота,
;        CY = 1, если частота не считалась (её писать не нужно),
;        ps_vol = байт громкости канала, ps_ixl = биты регистра 7 (бит 3 шум выкл, бит 0 тон выкл).
; ps_ixl ЖИВЁТ МЕЖДУ ВЫЗОВАМИ: на кадре, когда эффект кончился, в R7 идёт значение музыкального
; канала (проверено моделью: иначе расходятся 11 кадров из 6200 на каждой песне).
ps_sound:
	ld a,(hl)
	inc hl
	rra				; бит 0: аппаратный звук?
	jp c,ps_hard
	rra				; бит 1: нужен второй байт?
	jp c,ps_second
	ld b,a				; B = байт>>2: биты 3-0 громкость, бит 5 питч, бит 4 арпеджио
	and $0F
	jp nz,ps_soundon
	ld (ps_vol),a			; нулевая громкость: звука нет (A = 0)
	ld a,%1001
	ld (ps_ixl),a
	scf
	ret
ps_soundon:
	sub d				; кодировать громкость
	jp nc,ps_so1
	xor a
ps_so1:
	ld (ps_vol),a
	ld a,%1000
	ld (ps_ixl),a
	call ps_calcfreq
	ex de,hl			; DE = частота, HL = указатель инструмента
	or a				; CY = 0: частота посчитана
	ret

; второй байт: шум и/или запрет тона, возможна ручная частота
ps_second:
	ld b,a
	ld a,%1000
	ld (ps_ixl),a
	ld c,(hl)
	inc hl
	ld a,c
	and %11111			; шум?
	jp z,ps_sb_nonoise
	ld (_atVAR_Reg6),a
	xor a
	ld (ps_ixl),a			; открыть шумовой канал
ps_sb_nonoise:
	ld a,b
	and $0F
	sub d
	jp nc,ps_sb1
	xor a
ps_sb1:
	ld (ps_vol),a
	ld a,c
	and $20				; тон?
	jp nz,ps_sb_sound
	ld a,(ps_ixl)			; тона нет — поднять бит запрета
	inc a
	ld (ps_ixl),a
	scf
	ret
ps_sb_sound:
	ld a,c
	and $40				; ручная частота?
	call ps_getfreq
	ex de,hl
	or a
	ret

;;; --------------------------- аппаратный звук ---------------------------
ps_hard:
	rra				; бит 1: retrig? (в бит 7 уходит перенос — он нигде не читается)
	ld b,a
	jp nc,ps_h_noretrig
	ld a,(t1_ictr)			; retrig только на первом шаге строки инструмента (счётчики канала 1 —
	ld c,a				; так в оригинале, для всех трёх каналов)
	ld a,(t1_ispeed)
	cp c
	jp nz,ps_h_noretrig
	ld a,_atDEF_R13Retrig
	ld (ps_r13lock),a
ps_h_noretrig:
	ld a,b
	and 2
	jp z,ps_h_dependent		; Software/Hardware Dependent — в данных игры не встречается
	ld a,b
	and 1
	jp z,ps_independent
	ld a,(ps_sfx)			; звук кончился
	or a
	jp nz,ps_endsfx
	ld a,(hl)			; обычный звук: перезапустить инструмент с нового адреса
	inc hl
	ld h,(hl)
	ld l,a
	jp ps_sound
ps_endsfx:
	ld hl,0				; эффект кончился: ps_ixl и ps_vol не трогаем
	scf
	ret
; Ветка есть только чтобы не уйти в мусор, если формат когда-нибудь принесёт эти команды:
; гейт tools/arkos_model.py --check-unused обязан упасть раньше, чем это исполнится.
ps_h_dependent:
	ld a,%1001
	ld (ps_ixl),a
	scf
	ret

;;; --------------------------- Independent ---------------------------
; Аппаратная огибающая, независимая от тона. Встречается только в эффекте 19 (FX_LONGJUMP).
ps_independent:
	ld a,16
	ld (ps_vol),a
	xor a
	ld (ps_ihasf),a
	ld a,b
	and $20				; тон?
	jp z,ps_i_nosound
	ld a,%1000
	ld (ps_ixl),a
	ld a,e
	ld (ps_ixh),a			; сохранить ноту: арпеджио её испортит
	ld a,b
	and 4				; ручная частота?
	push bc
	call ps_getfreq
	pop bc
	ld (ps_ifreq),hl		; программная частота — вернём её каналу в конце
	ex de,hl			; HL = указатель инструмента
	ld a,1
	ld (ps_ihasf),a
	ld a,(ps_ixh)
	ld e,a
	jp ps_i_cont
ps_i_nosound:
	ld a,%1001
	ld (ps_ixl),a
ps_i_cont:
	ld b,(hl)			; второй байт
	inc hl
	ld a,b
	and $0F
	ld (ay_r0+13),a			; форма огибающей -> R13
	ld a,b
	rra
	rra
	ld b,a
	and 4				; ручная аппаратная частота?
	push bc
	call ps_getfreq
	pop bc
	ld (_atVAR_Reg11),hl		; аппаратная частота -> R11,R12
	ex de,hl
	ld a,b
	and $20				; шум?
	jp z,ps_i_end
	ld a,(hl)
	inc hl
	ld (_atVAR_Reg6),a
	ld a,(ps_ixl)
	and $F7
	ld (ps_ixl),a
ps_i_end:
	ld a,(ps_ihasf)
	or a
	jp z,ps_i_nofreq
	push hl
	ld hl,(ps_ifreq)
	ex de,hl
	pop hl
	or a
	ret
ps_i_nofreq:
	scf
	ret

;;; --------------------------- расчёт частоты ---------------------------
; ps_getfreq: Z = 1 -> частота по ноте, иначе ручная (word из инструмента).
; Вход:  HL = указатель инструмента, B = флаги (бит 5 питч инструмента, бит 4 арпеджио), E = нота.
; Выход: HL = частота, DE = указатель инструмента (регистры переставлены!). Портит A, B, C, DE.
ps_getfreq:
	jp nz,ps_manualfreq
ps_calcfreq:
	ld a,b
	and $20				; питч инструмента (word) прибавляется к питчу трека
	jp z,ps_cf_nopitch
	ld a,(hl)
	inc hl
	ld c,a
	ld a,(ps_pitch)
	add a,c
	ld (ps_pitch),a
	ld a,(hl)			; перенос переживает ld a,(hl)/inc hl/ld c,a/ld a,(nn) — флаги не трогают
	inc hl
	ld c,a
	ld a,(ps_pitch+1)
	adc a,c
	ld (ps_pitch+1),a
ps_cf_nopitch:
	ld a,b
	and $10				; арпеджио (byte) прибавляется к ноте
	ld a,e
	jp z,ps_cf_noarp
	add a,(hl)
	inc hl
	cp 144
	jp c,ps_cf_noarp
	ld a,143
ps_cf_noarp:
	ex de,hl			; DE = указатель инструмента, HL свободен под таблицу
	ld l,a
	ld h,at_perlo>>8		; таблицы периодов выровнены по странице
	ld c,(hl)
	ld h,at_perhi>>8
	ld b,(hl)
	ld hl,(ps_pitch)
	add hl,bc
	ret
ps_manualfreq:
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	push hl
	ld hl,(ps_pitch)
	add hl,de
	pop de				; DE = указатель инструмента
	ret

;;; ============================== чтение строки песни ==============================
at_readrow:
	ld a,(at_pattctr)
	dec a
	jp nz,at_setpatt
	call at_linker
	ld a,(at_pattheight)
at_setpatt:
	ld (at_pattctr),a
	call at_special
	call at_track1
	call at_track2
	jp at_track3

; линкер: транспозиции, адреса треков, высота паттерна, спец-трек, зацикливание песни
at_linker:
	ld hl,(at_linkptr)
	ld a,(hl)
	inc hl
	rra				; бит 0: конец песни?
	ld b,a
	jp nc,at_lk_cont
	ld a,(hl)			; перейти на позицию зацикливания и прочитать её флаги
	inc hl
	ld h,(hl)
	ld l,a
	ld a,(hl)
	inc hl
	rra
	ld b,a
at_lk_cont:
	ld a,b				; бит 1: транспозиция канала 1
	rra
	ld b,a
	jp nc,at_lk_k1
	ld a,(hl)
	inc hl
	ld (t1_transp),a
at_lk_k1:
	ld a,b
	rra
	ld b,a
	jp nc,at_lk_k2
	ld a,(hl)
	inc hl
	ld (t2_transp),a
at_lk_k2:
	ld a,b
	rra
	ld b,a
	jp nc,at_lk_k3
	ld a,(hl)
	inc hl
	ld (t3_transp),a
at_lk_k3:
	ld a,(hl)			; адреса трёх треков — всегда
	ld (t1_ptr),a
	inc hl
	ld a,(hl)
	ld (t1_ptr+1),a
	inc hl
	ld a,(hl)
	ld (t2_ptr),a
	inc hl
	ld a,(hl)
	ld (t2_ptr+1),a
	inc hl
	ld a,(hl)
	ld (t3_ptr),a
	inc hl
	ld a,(hl)
	ld (t3_ptr+1),a
	inc hl
	ld a,b				; бит 4: новая высота паттерна
	rra
	ld b,a
	jp nc,at_lk_k4
	ld a,(hl)
	inc hl
	ld (at_pattheight),a
at_lk_k4:
	ld a,b				; бит 5: новый спец-трек
	rra
	ld b,a
	jp nc,at_lk_k5
	ld a,(hl)
	ld (at_sptrack),a
	inc hl
	ld a,(hl)
	ld (at_sptrack+1),a
	inc hl
at_lk_k5:
	ld (at_linkptr),hl
	ld hl,(at_sptrack)
	ld (at_spptr),hl
	ld a,1				; высота трека не связана с высотой паттерна — счётчики сбрасываем
	ld (at_spwait),a
	ld (t1_wait),a
	ld (t2_wait),a
	ld (t3_wait),a
	ret

; спец-трек: только смена скорости песни (дигидрам оригинал пишет в мёртвую ячейку)
at_special:
	ld a,(at_spwait)
	dec a
	jp nz,at_sp_store
	ld hl,(at_spptr)
	ld a,(hl)
	inc hl
	or a				; srl a: CY = 0, потом сдвиг
	rra
	jp nc,at_sp_setptr		; ожидание: A = число строк
	or a
	rra				; данные: CY = скорость(0)/дигидрам(1)
	ld c,0
	jp nc,at_sp_c0
	inc c
at_sp_c0:
	or a				; Z по значению: 0 = escape-код, значение в следующем байте
	jp nz,at_sp_noesc
	ld a,(hl)
	inc hl
at_sp_noesc:
	ld b,a
	ld a,c
	or a
	jp nz,at_sp_digi		; дигидрам — игрой не используется
	ld a,b
	ld (at_songspeed),a
at_sp_digi:
	ld a,1
at_sp_setptr:
	ld (at_spptr),hl
at_sp_store:
	ld (at_spwait),a
	ret

; чтение строки трека: HL = указатель.
; Выход: HL обновлён; CY = 1 -> ожидание A строк; иначе D = параметры, E = нота,
;        at_rt_instr = номер инструмента, at_rt_pitch = приращение питча.
at_readtrack:
	ld a,(hl)
	inc hl
	or a
	rra				; бит 0: полная оптимизация (только нота)?
	jp c,at_rt_full
	sub 32				; 0-31 = ожидание
	jp c,at_rt_wait
	jp nz,at_rt_noesc
	ld a,(hl)			; escape-код для дальних нот
	inc hl
	inc a
at_rt_noesc:
	dec a
	ld e,a				; нота
	ld a,(hl)
	ld d,a				; параметры
	inc hl
	and $80				; питч?
	jp z,at_rt_np
	ld a,(hl)
	ld (at_rt_pitch),a
	inc hl
	ld a,(hl)
	ld (at_rt_pitch+1),a
	inc hl
at_rt_np:
	ld a,d
	and $20				; новый инструмент?
	ret z
	ld a,(hl)
	ld (at_rt_instr),a
	inc hl
	or a
	ret
at_rt_wait:
	add a,32			; CY = 1: это ожидание
	ret
at_rt_full:
	ld d,%01000000			; только нота, без питча и громкости, тот же инструмент
	sub 1
	ld e,a
	ret nc
	ld e,(hl)			; escape-код (0): нота в следующем байте
	inc hl
	or a
	ret

;;; --- три трека. Тела одинаковы, различаются только адресами ячеек канала. ---
at_track1:
	ld a,(t1_wait)
	dec a
	jp nz,at_t1_store
	ld hl,(t1_ptr)
	call at_readtrack
	ld (t1_ptr),hl
	jp c,at_t1_store
	ld a,d
	rra				; громкость?
	jp nc,at_t1_kv
	and $0F
	ld (t1_vol),a
at_t1_kv:
	ld a,d
	and $80				; новое приращение питча?
	jp z,at_t1_kp
	ld hl,(at_rt_pitch)
	ld (t1_padd),hl
	ld a,h
	or l
	jp z,at_t1_kp
	ld a,1
	ld (t1_pon),a
at_t1_kp:
	ld a,d
	and $40				; нота?
	jp z,at_t1_kn
	ld a,e
	ld hl,t1_transp
	add a,(hl)			; транспозиция из линкера
	ld (t1_note),a
	ld hl,0
	ld (t1_pitch),hl		; нота сбрасывает питч трека
	ld hl,(t1_padd)
	ld a,h
	or l
	jp z,at_t1_p0
	ld a,1
at_t1_p0:
	ld (t1_pon),a
	ld a,d
	and $20				; новый инструмент?
	jp z,at_t1_same
	ld a,(at_rt_instr)
	call at_instr			; HL = адрес инструмента, скорость в A
	ld (t1_ispeed),a
	ld (t1_ictr),a
	ld a,(at_rt_retrig)
	or a
	jp z,at_t1_nrt
	ld (ps_r13lock),a
at_t1_nrt:
	ld (t1_iaddr),hl
	jp at_t1_setptr
at_t1_same:
	ld hl,(t1_iaddr)		; тот же инструмент — перезапустить с начала
	ld a,(t1_ispeed)
	ld (t1_ictr),a
at_t1_setptr:
	ld (t1_iptr),hl
at_t1_kn:
	ld a,1
at_t1_store:
	ld (t1_wait),a
	ret

at_track2:
	ld a,(t2_wait)
	dec a
	jp nz,at_t2_store
	ld hl,(t2_ptr)
	call at_readtrack
	ld (t2_ptr),hl
	jp c,at_t2_store
	ld a,d
	rra
	jp nc,at_t2_kv
	and $0F
	ld (t2_vol),a
at_t2_kv:
	ld a,d
	and $80
	jp z,at_t2_kp
	ld hl,(at_rt_pitch)
	ld (t2_padd),hl
	ld a,h
	or l
	jp z,at_t2_kp
	ld a,1
	ld (t2_pon),a
at_t2_kp:
	ld a,d
	and $40
	jp z,at_t2_kn
	ld a,e
	ld hl,t2_transp
	add a,(hl)
	ld (t2_note),a
	ld hl,0
	ld (t2_pitch),hl
	ld hl,(t2_padd)
	ld a,h
	or l
	jp z,at_t2_p0
	ld a,1
at_t2_p0:
	ld (t2_pon),a
	ld a,d
	and $20
	jp z,at_t2_same
	ld a,(at_rt_instr)
	call at_instr
	ld (t2_ispeed),a
	ld (t2_ictr),a
	ld a,(at_rt_retrig)
	or a
	jp z,at_t2_nrt
	ld (ps_r13lock),a
at_t2_nrt:
	ld (t2_iaddr),hl
	jp at_t2_setptr
at_t2_same:
	ld hl,(t2_iaddr)
	ld a,(t2_ispeed)
	ld (t2_ictr),a
at_t2_setptr:
	ld (t2_iptr),hl
at_t2_kn:
	ld a,1
at_t2_store:
	ld (t2_wait),a
	ret

at_track3:
	ld a,(t3_wait)
	dec a
	jp nz,at_t3_store
	ld hl,(t3_ptr)
	call at_readtrack
	ld (t3_ptr),hl
	jp c,at_t3_store
	ld a,d
	rra
	jp nc,at_t3_kv
	and $0F
	ld (t3_vol),a
at_t3_kv:
	ld a,d
	and $80
	jp z,at_t3_kp
	ld hl,(at_rt_pitch)
	ld (t3_padd),hl
	ld a,h
	or l
	jp z,at_t3_kp
	ld a,1
	ld (t3_pon),a
at_t3_kp:
	ld a,d
	and $40
	jp z,at_t3_kn
	ld a,e
	ld hl,t3_transp
	add a,(hl)
	ld (t3_note),a
	ld hl,0
	ld (t3_pitch),hl
	ld hl,(t3_padd)
	ld a,h
	or l
	jp z,at_t3_p0
	ld a,1
at_t3_p0:
	ld (t3_pon),a
	ld a,d
	and $20
	jp z,at_t3_same
	ld a,(at_rt_instr)
	call at_instr
	ld (t3_ispeed),a
	ld (t3_ictr),a
	ld a,(at_rt_retrig)
	or a
	jp z,at_t3_nrt
	ld (ps_r13lock),a
at_t3_nrt:
	ld (t3_iaddr),hl
	jp at_t3_setptr
at_t3_same:
	ld hl,(t3_iaddr)
	ld a,(t3_ispeed)
	ld (t3_ictr),a
at_t3_setptr:
	ld (t3_iptr),hl
at_t3_kn:
	ld a,1
at_t3_store:
	ld (t3_wait),a
	ret

; A = номер инструмента -> HL = адрес данных (заголовок пропущен), A = скорость,
; at_rt_retrig = байт retrig.
at_instr:
	ld l,a
	ld h,0
	add hl,hl
	ex de,hl
	ld hl,(at_ilut)
	add hl,de
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	ld a,(hl)			; скорость инструмента
	inc hl
	ld d,a
	ld a,(hl)			; retrig
	inc hl
	ld (at_rt_retrig),a
	ld a,d
	ret

;;; ============================== управление ==============================
; atInit: DE = адрес песни. Раскладка .mus: +9 скорость, +10 размер блока инструментов (word),
; +12 таблица инструментов, за ней пре-линкер (высота паттерна, 3 транспозиции, адрес спец-трека).
atInit:
	ld hl,9
	add hl,de
	ld a,(hl)
	inc hl
	ld (at_songspeed),a
	ld a,(hl)
	inc hl
	ld c,a
	ld a,(hl)
	inc hl
	ld b,a
	ld (at_ilut),hl
	add hl,bc			; пропустить блок инструментов
	ld a,(hl)
	inc hl
	ld (at_pattheight),a
	ld a,(hl)
	inc hl
	ld (t1_transp),a
	ld a,(hl)
	inc hl
	ld (t2_transp),a
	ld a,(hl)
	inc hl
	ld (t3_transp),a
	ld a,(hl)
	inc hl
	ld (at_sptrack),a
	ld a,(hl)
	inc hl
	ld (at_sptrack+1),a
	ld (at_linkptr),hl
	ld a,1
	ld (at_songctr),a
	ld (at_pattctr),a
	ld a,$FF
	ld (ay_r0+13),a
	ld hl,(at_ilut)			; указатели инструментов -> инструмент 0 без заголовка
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	inc hl
	inc hl
	ld (t1_iptr),hl
	ld (t2_iptr),hl
	ld (t3_iptr),hl
	ret

; atStop: гасит громкости каналов 1 и 2 (оригинал чистит Reg8, digidrum, Reg9 — R10 не трогает)
; и выключает тон и шум на всех каналах.
atStop:
	xor a
	ld (ay_r0+8),a
	ld (ay_r0+9),a
	ld a,%00111111
	jp at_ay3update

; atSfxInit: DE = адрес набора эффектов.
atSfxInit:
	ld hl,12
	add hl,de
	ld (at_sfxlut),hl
atSfxStopAll:
	ld hl,0
	ld (s1_instr),hl
	ld (s2_instr),hl
	ld (s3_instr),hl
	ret

; atSfxStop: A = канал (0..2).
atSfxStop:
	call at_sfxblk
	ld de,6
	add hl,de
	ld (hl),0
	inc hl
	ld (hl),0
	ret

; A = канал -> HL = база блока эффекта.
at_sfxblk:
	ld l,a
	ld h,0
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,s1_pitch
	add hl,de
	ret

; atSfxPlay: A = канал (0..2), L = номер эффекта, H = громкость (0..15), E = нота,
; D = скорость (0 = из инструмента), BC = питч. Игра зовёт только с A=1, D=0, BC=0.
atSfxPlay:
	ld (sfx_num),hl			; +0 номер, +1 громкость
	ld h,d
	ld l,e
	ld (sfx_note),hl		; +0 нота, +1 скорость
	ld h,b
	ld l,c
	ld (sfx_pit),hl
	push af
	ld a,(sfx_num)			; адрес инструмента эффекта
	ld l,a
	ld h,0
	add hl,hl
	ex de,hl
	ld hl,(at_sfxlut)
	add hl,de
	ld a,(hl)
	inc hl
	ld h,(hl)
	ld l,a
	ld (sfx_ia),hl
	ld a,(sfx_note+1)		; скорость: своя или из инструмента
	or a
	jp nz,sfx_uspeed
	ld a,(hl)
sfx_uspeed:
	ld (sfx_spd),a
	pop af
	call at_sfxblk
	ld a,(sfx_pit)
	ld (hl),a
	inc hl
	ld a,(sfx_pit+1)
	ld (hl),a
	inc hl
	ld a,(sfx_note)
	ld (hl),a			; нота
	inc hl
	ld a,15
	ld b,a
	ld a,(sfx_num+1)
	ld c,a
	ld a,b
	sub c
	ld (hl),a			; инвертированная громкость
	inc hl
	ld a,(sfx_spd)
	ld (hl),a			; скорость
	inc hl
	ld (hl),a			; счётчик скорости
	inc hl
	ld a,(sfx_ia)			; адрес инструмента + 2 (пропустить скорость и retrig)
	add a,2
	ld (hl),a
	inc hl
	ld a,(sfx_ia+1)
	adc a,0
	ld (hl),a
	ret

;;; ============================== данные ==============================
; Таблицы периодов нот (Spectrum/Pentagon, atCNF_ZXPT=1) разложены на младшие и старшие байты,
; каждая половина выровнена по странице: выборка периода — ld l,нота / ld h,стр / ld c,(hl) ...
	align 256
at_perlo:
	db 220,7,61,127,203,34,130,235,93,214,87,223
	db 110,3,159,63,230,145,65,246,174,107,44,240
	db 183,130,79,32,243,200,161,123,87,54,22,248
	db 220,193,168,144,121,100,80,61,44,27,11,252
	db 238,224,212,200,189,178,168,159,150,141,133,126
	db 119,112,106,100,94,89,84,79,75,71,67,63
	db 59,56,53,50,47,45,42,40,37,35,33,31
	db 30,28,26,25,24,22,21,20,19,18,17,16
	db 15,14,13,12,12,11,11,10,9,9,8,8
	db 7,7,7,6,6,6,5,5,5,4,4,4
	db 4,4,3,3,3,3,3,2,2,2,2,2
	db 2,2,2,2,2,2,2,2,2,2,2,2

; --- состояние плеера: ровно в дырке между двумя половинами таблицы (112 байт), поэтому
; at_perhi = at_perlo + 256 и второй align ничего не тратит. Блоки эффектов не влезали — они
; вынесены за at_perhi (сторож: в build/ianna_vec.lst at_perhi - at_perlo обязан быть $100). ---
at_songspeed:	db 1		; скорость песни (кадров на строку)
at_songctr:	db 1
at_pattheight:	db 1		; высота паттерна (строк)
at_pattctr:	db 1
at_linkptr:	dw 0		; указатель в линкере
at_sptrack:	dw 0		; адрес спец-трека
at_spptr:	dw 0
at_spwait:	db 1
at_ilut:	dw 0		; таблица инструментов песни
at_sfxlut:	dw 0		; таблица инструментов эффектов
at_rt_instr:	db 0		; выход at_readtrack
at_rt_pitch:	dw 0
at_rt_retrig:	db 0		; выход at_instr

ps_pitch:	dw 0		; питч, действующий на текущем вызове ps_sound
ps_pblk:	dw 0
ps_vol:		db 0		; байт громкости, посчитанный ps_sound
ps_ixl:		db 0		; биты регистра 7 канала (живут между вызовами)
ps_ixh:		db 0		; сохранённая нота (Independent)
ps_r7:		db 0		; сборка регистра 7
ps_sfx:		db 0		; 1 = играем эффект (конец звука = адрес 0)
ps_ifreq:	dw 0		; Independent: программная частота
ps_ihasf:	db 0
ps_r13lock:	db 255
ay_none:	db 0		; 1 = AY нет, эффекты идут на ВИ53 (ay_detect)
vi_on:		db 0		; счётчик 2 ВИ53 в режиме меандра
vi_rnd:		db 0		; последнее записанное значение R13 (операнд `cp` оригинала)

sfx_num:	dw 0		; разбор аргументов atSfxPlay
sfx_note:	dw 0
sfx_pit:	dw 0
sfx_ia:		dw 0
sfx_spd:	db 0

; теневые регистры AY в порядке вывода: R0..R13
ay_r0:		db 0,0,0,0,0,0
_atVAR_Reg6:	db 0		; шум; гасится игрой после MUSIC_Load (LoadScreen)
		db 0		; R7 — собирается в at_ay3update
		db 0,0,0	; R8,R9,R10 — громкости каналов 1,2,3
_atVAR_Reg11:	db 0
_atVAR_Reg12:	db 0
		db 0		; R13

; --- каналы песни ---
t1_note:	db 0
t1_vol:		db 0		; инвертированная громкость
t1_iptr:	dw 0
t1_iaddr:	dw 0
t1_ispeed:	db 6
t1_ictr:	db 1
t1_pitch:	dw 0
t1_padd:	dw 0
t1_pon:		db 0		; 0 = питч и приращение нулевые (быстрая ветка)
t1_ptr:		dw 0
t1_wait:	db 1
t1_transp:	db 0

t2_note:	db 0
t2_vol:		db 0
t2_iptr:	dw 0
t2_iaddr:	dw 0
t2_ispeed:	db 6
t2_ictr:	db 1
t2_pitch:	dw 0
t2_padd:	dw 0
t2_pon:		db 0
t2_ptr:		dw 0
t2_wait:	db 1
t2_transp:	db 0

t3_note:	db 0
t3_vol:		db 0
t3_iptr:	dw 0
t3_iaddr:	dw 0
t3_ispeed:	db 6
t3_ictr:	db 1
t3_pitch:	dw 0
t3_padd:	dw 0
t3_pon:		db 0
t3_ptr:		dw 0
t3_wait:	db 1
t3_transp:	db 0


	align 256
at_perhi:
	db 14,14,13,12,11,11,10,9,9,8,8,7
	db 7,7,6,6,5,5,5,4,4,4,4,3
	db 3,3,3,3,2,2,2,2,2,2,2,1
	db 1,1,1,1,1,1,1,1,1,1,1,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0
	db 0,0,0,0,0,0,0,0,0,0,0,0

; --- каналы эффектов (блоки по 8 байт, adressуются atSfxPlay как s1_pitch + канал*8) ---
s1_pitch:	dw 0
s1_note:	db 0
s1_vol:		db 0
s1_speed:	db 6
s1_sctr:	db 1
s1_instr:	dw 0		; 0 = эффекта нет
s2_pitch:	dw 0
s2_note:	db 0
s2_vol:		db 0
s2_speed:	db 6
s2_sctr:	db 1
s2_instr:	dw 0
s3_pitch:	dw 0
s3_note:	db 0
s3_vol:		db 0
s3_speed:	db 6
s3_sctr:	db 1
s3_instr:	dw 0

;;; Хвост ВИ53 и проба AY — в куске данных: в коде ($C010-$C7FF) места нет.
vi_out:
	ld a,(vi_on)
	or a
	jp nz,vi_cnt
	inc a
	ld (vi_on),a
	ld a,$B6			; счётчик 2, режим 3 (меандр); дальше только делитель — без щелчка
	out ($08),a
vi_cnt:
	ld a,l
	out ($09),a
	ld a,h
	out ($09),a
	ret
vi_mute:
	ld a,(vi_on)
	or a
	ret z
	xor a
	ld (vi_on),a
	ld a,$B0			; режим 0: выход стоит
	out ($08),a
	xor a
	out ($09),a
	out ($09),a
	ret

; ay_none = 0, если AY отвечает на чтение регистра 0 (порт 15h) двумя образцами, как в порте Tony
; (чтение через 14h у vector06js не проверяется — места нет). Зовёт ark_init при каждой загрузке песни:
; оверлей приезжает с набором уровня. Портит BC.
ay_detect:
	xor a
	out ($15),a
	ld b,$55
	call ayd_rd
	jp nz,ayd_set
	ld b,$AA
	call ayd_rd
ayd_set:
	ld (ay_none),a
	ret
; B = образец -> A = 0 (ответил) или 1, флаг Z — то же.
ayd_rd:
	ld a,b
	out ($14),a
	in a,($15)
	sub b
	ret z
	ld a,1
	ret
