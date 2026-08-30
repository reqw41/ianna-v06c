;;; arkos_hot.asm, часть 1 — ВЕКТОР: горячая часть плеера Arkos Tracker 1 на i8080 вручную.
;;; Заменяет строки оригинала «Play Sound on Track 3/2/1» (до _atAY3Update). Алгоритм 1:1,
;;; самомодифицируемые операнды _atVAR_* — как в оригинале (их читает холодный код и atSfxPlay).
;;; Регистры Z80, которых нет: DE' (TrackPitch) -> ps_pitch; HL' (частота) -> HL, указатель
;;; инструмента на это время в ps_iptr; IY -> ps_freqp/ps_volp; IXL/IXH -> ps_ixl/ps_ixh;
;;; AF' (сборка R7) -> ps_r7. Гейт: tests/music/check.sh (поток AY 1:1 с Z80-оригиналом).

;*** Play Sound on Track 3 ***
	ld hl,_atVAR_AY3Registers + 4
	ld (ps_freqp),hl		; IY -> регистры канала: частота
	ld hl,_atVAR_AY3Registers + 4 + 7
	ld (ps_volp),hl			; IY+7 -> громкость
_atVAR_Track3Pitch	ld hl,0
_atVAR_Track3PitchAdd	ld de,0
	add hl,de
	ld (_atVAR_Track3Pitch + 1),hl
	call ps_sra2			; питч/4 со знаком
	ld (ps_pitch),hl		; DE' = TrackPitch
_atVAR_Track3Volume	equ $+2
_atVAR_Track3Note	equ $+1
	ld de,0				; D = инвертированная громкость, E = нота
_atVAR_Track3InstrumentPtr ld hl,0
	call _atPlaySound
_atVAR_Track3InstSpeedCtr ld a,1
	dec a
	jp nz,_atSoundTrack3_noForward
	ld (_atVAR_Track3InstrumentPtr + 1),hl
_atVAR_Track3InstSpeed	ld a,6
_atSoundTrack3_noForward
	ld (_atVAR_Track3InstSpeedCtr + 1),a
; Эффект на канале 3. Раскладка операндов одинакова для трёх каналов — atSfxPlay адресует их
; смещениями от _atVAR_SfxTrack1_pitch.
_atVAR_SfxTrack3_pitch	ld de,0
	ex de,hl
	ld (ps_pitch),hl
_atVAR_SfxTrack3_instrument ld hl,0	; 0 = эффекта нет
	ld a,l
	or h
	jp z,_atNoSfxTrack3
_atVAR_SfxTrack3_volume	equ $+2
_atVAR_SfxTrack3_note	equ $+1
	ld de,0
	ld a,1
	ld (PLY_PS_EndSound_SFX + 1),a
	call _atPlaySound
	xor a
	ld (PLY_PS_EndSound_SFX + 1),a
	ld a,l				; адрес 0 = инструмент кончился
	or h
	jp z,_atVAR_SfxTrack3_setInstrumentAddr
_atVAR_SfxTrack3_instrumentSpeedCtr ld a,1
	dec a
	jp nz,_atSfxTrack3_noForward
_atVAR_SfxTrack3_setInstrumentAddr
	ld (_atVAR_SfxTrack3_instrument + 1),hl
_atVAR_SfxTrack3_instrumentSpeed ld a,6
_atSfxTrack3_noForward
	ld (_atVAR_SfxTrack3_instrumentSpeedCtr + 1),a
_atNoSfxTrack3

	ld a,(ps_ixl)			; R7: флаги канала 3
	ld (ps_r7),a

;*** Play Sound on Track 2 ***
	ld hl,_atVAR_AY3Registers + 2
	ld (ps_freqp),hl		; IY -> регистры канала: частота
	ld hl,_atVAR_AY3Registers + 2 + 7
	ld (ps_volp),hl			; IY+7 -> громкость
_atVAR_Track2Pitch	ld hl,0
_atVAR_Track2PitchAdd	ld de,0
	add hl,de
	ld (_atVAR_Track2Pitch + 1),hl
	call ps_sra2			; питч/4 со знаком
	ld (ps_pitch),hl		; DE' = TrackPitch
_atVAR_Track2Volume	equ $+2
_atVAR_Track2Note	equ $+1
	ld de,0				; D = инвертированная громкость, E = нота
_atVAR_Track2InstrumentPtr ld hl,0
	call _atPlaySound
_atVAR_Track2InstSpeedCtr ld a,1
	dec a
	jp nz,_atSoundTrack2_noForward
	ld (_atVAR_Track2InstrumentPtr + 1),hl
_atVAR_Track2InstSpeed	ld a,6
_atSoundTrack2_noForward
	ld (_atVAR_Track2InstSpeedCtr + 1),a
; Эффект на канале 2. Раскладка операндов одинакова для трёх каналов — atSfxPlay адресует их
; смещениями от _atVAR_SfxTrack1_pitch.
_atVAR_SfxTrack2_pitch	ld de,0
	ex de,hl
	ld (ps_pitch),hl
_atVAR_SfxTrack2_instrument ld hl,0	; 0 = эффекта нет
	ld a,l
	or h
	jp z,_atNoSfxTrack2
_atVAR_SfxTrack2_volume	equ $+2
_atVAR_SfxTrack2_note	equ $+1
	ld de,0
	ld a,1
	ld (PLY_PS_EndSound_SFX + 1),a
	call _atPlaySound
	xor a
	ld (PLY_PS_EndSound_SFX + 1),a
	ld a,l				; адрес 0 = инструмент кончился
	or h
	jp z,_atVAR_SfxTrack2_setInstrumentAddr
_atVAR_SfxTrack2_instrumentSpeedCtr ld a,1
	dec a
	jp nz,_atSfxTrack2_noForward
_atVAR_SfxTrack2_setInstrumentAddr
	ld (_atVAR_SfxTrack2_instrument + 1),hl
_atVAR_SfxTrack2_instrumentSpeed ld a,6
_atSfxTrack2_noForward
	ld (_atVAR_SfxTrack2_instrumentSpeedCtr + 1),a
_atNoSfxTrack2

	ld a,(ps_r7)			; R7: (ch3 << 1 | ch2) << 1
	add a,a
	ld b,a
	ld a,(ps_ixl)
	or b
	add a,a
	ld (ps_r7),a

;*** Play Sound on Track 1 ***
	ld hl,_atVAR_AY3Registers + 0
	ld (ps_freqp),hl		; IY -> регистры канала: частота
	ld hl,_atVAR_AY3Registers + 0 + 7
	ld (ps_volp),hl			; IY+7 -> громкость
_atVAR_Track1Pitch	ld hl,0
_atVAR_Track1PitchAdd	ld de,0
	add hl,de
	ld (_atVAR_Track1Pitch + 1),hl
	call ps_sra2			; питч/4 со знаком
	ld (ps_pitch),hl		; DE' = TrackPitch
_atVAR_Track1Volume	equ $+2
_atVAR_Track1Note	equ $+1
	ld de,0				; D = инвертированная громкость, E = нота
_atVAR_Track1InstrumentPtr ld hl,0
	call _atPlaySound
_atVAR_Track1InstSpeedCtr ld a,1
	dec a
	jp nz,_atSoundTrack1_noForward
	ld (_atVAR_Track1InstrumentPtr + 1),hl
_atVAR_Track1InstSpeed	ld a,6
_atSoundTrack1_noForward
	ld (_atVAR_Track1InstSpeedCtr + 1),a
; Эффект на канале 1. Раскладка операндов одинакова для трёх каналов — atSfxPlay адресует их
; смещениями от _atVAR_SfxTrack1_pitch.
_atVAR_SfxTrack1_pitch	ld de,0
	ex de,hl
	ld (ps_pitch),hl
_atVAR_SfxTrack1_instrument ld hl,0	; 0 = эффекта нет
	ld a,l
	or h
	jp z,_atNoSfxTrack1
_atVAR_SfxTrack1_volume	equ $+2
_atVAR_SfxTrack1_note	equ $+1
	ld de,0
	ld a,1
	ld (PLY_PS_EndSound_SFX + 1),a
	call _atPlaySound
	xor a
	ld (PLY_PS_EndSound_SFX + 1),a
	ld a,l				; адрес 0 = инструмент кончился
	or h
	jp z,_atVAR_SfxTrack1_setInstrumentAddr
_atVAR_SfxTrack1_instrumentSpeedCtr ld a,1
	dec a
	jp nz,_atSfxTrack1_noForward
_atVAR_SfxTrack1_setInstrumentAddr
	ld (_atVAR_SfxTrack1_instrument + 1),hl
_atVAR_SfxTrack1_instrumentSpeed ld a,6
_atSfxTrack1_noForward
	ld (_atVAR_SfxTrack1_instrumentSpeedCtr + 1),a
_atNoSfxTrack1

	ld a,(ps_r7)			; R7 = ... | ch1 -> A для _atAY3Update
	ld b,a
	ld a,(ps_ixl)
	or b

;;;SPLIT;;;
;;; arkos_hot.asm, часть 2 — _atPlaySound и подпрограммы (заменяет оригинал до «Read Track»).
; Вход: HL = указатель на данные инструмента, D = инвертированная громкость, E = нота,
; ps_pitch = TrackPitch, ps_freqp/ps_volp = регистры канала. Выход: HL = новый указатель
; инструмента (0 = эффект кончился), ps_ixl = флаги R7 канала (бит 3 шум выкл, бит 0 звук выкл).
_atPlaySound
	ld b,(hl)
	inc hl
	ld a,b
	rra
	ld b,a				; rr b: аппаратный звук?
	jp c,PLY_PS_Hard
	ld a,b
	rra
	ld b,a				; rr b: нужен второй байт?
	jp c,PLY_PS_S_SecondByteNeeded
	ld a,b
	and %1111
	jp nz,PLY_PS_S_SoundOn
	; громкость 0 — звука нет: громкость 0 (на случай аппаратного баса раньше), звук и шум выкл
	push hl
	ld hl,(ps_volp)
	ld (hl),a
	pop hl
	ld a,%1001
	ld (ps_ixl),a
	ret
PLY_PS_S_SoundOn
	ld a,%1000
	ld (ps_ixl),a
	ld a,b
	and %1111
	sub d				; кодировать громкость
	jp nc,ps_so_1
	xor a
ps_so_1:
	push hl
	ld hl,(ps_volp)
	ld (hl),a
	pop hl
	ld a,b
	rra
	ld b,a				; rr b: флаги для подпрограммы
	call _atSound_calcFrequency
	jp ps_store_freq_ret
PLY_PS_S_SecondByteNeeded
	ld a,%1000			; по умолчанию: шум выкл, звук вкл
	ld (ps_ixl),a
	ld c,(hl)
	inc hl
	ld a,c				; шум?
	and %11111
	jp z,PLY_PS_S_SBN_NoNoise
	ld (_atVAR_Reg6),a
	xor a
	ld (ps_ixl),a			; открыть шум
PLY_PS_S_SBN_NoNoise
	ld a,b
	and %1111
	sub d
	jp nc,ps_sbn_1
	xor a
ps_sbn_1:
	push hl
	ld hl,(ps_volp)
	ld (hl),a
	pop hl
	ld a,c				; звук?
	and $20
	jp nz,PLY_PS_S_SBN_Sound
	ld a,(ps_ixl)			; нет звука: inc ixl
	inc a
	ld (ps_ixl),a
	ret
PLY_PS_S_SBN_Sound
	ld a,b
	rra
	ld b,a				; rr b
	ld a,c
	and $40				; bit 6,c: ручная частота?
	call _atSound_getFrequency
ps_store_freq_ret:			; HL = частота -> регистры канала; вернуть указатель инструмента
	ex de,hl
	ld hl,(ps_freqp)
	ld (hl),e
	inc hl
	ld (hl),d
	ld hl,(ps_iptr)
	ret
;**********
;Hard Sound
;**********
PLY_PS_Hard
	ld a,b
	rra
	ld b,a				; rr b: retrig
	jp nc,PLY_PS_Hard_NoRetrig
	ld a,(_atVAR_Track1InstSpeedCtr + 1)	; retrig только на первом шаге строки инструмента
	ld c,a
	ld a,(_atVAR_Track1InstSpeed + 1)
	cp c
	jp nz,PLY_PS_Hard_NoRetrig
	ld a,_atDEF_R13RetrigValue
	ld (_atVAR_R13Lock + 1),a
PLY_PS_Hard_NoRetrig
	ld a,b
	and 2				; bit 1,b: Loop/Independent?
	jp nz,PLY_PS_Hard_LoopOrIndependent
	; аппаратный звук: громкость 16
	push hl
	ld hl,(ps_volp)
	ld (hl),16
	pop hl
	ld a,%1000
	ld (ps_ixl),a
	ld c,(hl)			; второй байт
	inc hl
	ld a,c
	and %1111			; форма огибающей
	ld (_atVAR_Reg13),a
	ld a,b
	and 1				; bit 0,b
	jp z,PLY_PS_HardwareDependent
;******************
;Software Dependent
;******************
	ld a,b
	and 4				; bit 4-2,b: ручная частота?
	call _atSound_getFrequency
	ex de,hl			; программная частота -> регистры канала (HL остаётся = частота)
	ld hl,(ps_freqp)
	ld (hl),e
	inc hl
	ld (hl),d
	ex de,hl
	; сдвиг вправо: n = 7 - ((c >> 4) & 7)  (в оригинале jr $+2 по цепочке srl h / rr l)
	ld a,c
	rra
	rra
	rra
	rra
	cpl
	and 7
	jp z,PLY_PS_SD_NoInc		; n = 0: в оригинале CY = 0 (после and) — без округления
	ld d,a
ps_sd_loop:
	ld a,h
	or a
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	dec d				; dec не трогает CY
	jp nz,ps_sd_loop
	jp nc,PLY_PS_SD_NoInc		; округление по вытесненному биту
	inc hl
PLY_PS_SD_NoInc
	ld a,b
	and $20				; bit 7-2,b: аппаратный питч?
	jp z,PLY_PS_SD_NoHardwarePitch
	ex de,hl			; прибавить питч (word из инструмента) к аппаратной частоте
	ld hl,(ps_iptr)
	ld a,(hl)
	inc hl
	add a,e
	ld e,a
	ld a,(hl)
	inc hl
	adc a,d
	ld d,a
	ld (ps_iptr),hl
	ex de,hl
PLY_PS_SD_NoHardwarePitch
	ld (_atVAR_Reg11),hl
	ld hl,(ps_iptr)
;This code is also used by Hardware Dependent.
PLY_PS_SD_Noise
	ld a,c				; шум?
	and $80
	ret z
	ld a,(hl)
	inc hl
	ld (_atVAR_Reg6),a
	xor a
	ld (ps_ixl),a
	ret
;Hardware Dependent
PLY_PS_HardwareDependent
	ld a,b
	and 4				; ручная аппаратная частота?
	call _atSound_getFrequency
	ld (_atVAR_Reg11),hl		; аппаратная частота
	; сдвиг влево: n = 7 - ((c >> 4) & 7)  (цепочка sla l / rl h = add hl,hl)
	ld a,c
	rra
	rra
	rra
	rra
	cpl
	and 7
	jp z,PLY_PS_HD_Shifted
	ld d,a
ps_hd_loop:
	add hl,hl
	dec d
	jp nz,ps_hd_loop
PLY_PS_HD_Shifted
	ld a,b
	and $20				; программный питч?
	jp z,PLY_PS_HD_NoSoftwarePitch
	ex de,hl
	ld hl,(ps_iptr)
	ld a,(hl)
	inc hl
	add a,e
	ld e,a
	ld a,(hl)
	inc hl
	adc a,d
	ld d,a
	ld (ps_iptr),hl
	ex de,hl
PLY_PS_HD_NoSoftwarePitch
	ex de,hl			; программная частота -> регистры канала
	ld hl,(ps_freqp)
	ld (hl),e
	inc hl
	ld (hl),d
	ld hl,(ps_iptr)
	jp PLY_PS_SD_Noise
PLY_PS_Hard_LoopOrIndependent
	ld a,b
	and 1				; bit 0,b: 0 = Independent, 1 = Loop (конец звука)
	jp z,PLY_PS_Independent
PLY_PS_EndSound_SFX ld a,0		; 1 = играет эффект: конец = адрес 0
	or a
	jp nz,PLY_PS_EndSFX
	ld a,(hl)			; конец звука: новый указатель и перезапуск инструмента
	inc hl
	ld h,(hl)
	ld l,a
	jp _atPlaySound
PLY_PS_EndSFX
	ld hl,0
	ret
;Independent
PLY_PS_Independent
	push hl
	ld hl,(ps_volp)
	ld (hl),16
	pop hl
	ld a,b
	and $20				; bit 7-2,b: звук?
	jp nz,PLY_PS_I_SoundOn
	ld a,%1001			; без звука: программная частота не нужна
	ld (ps_ixl),a
	jp PLY_PS_I_SkipSoftwareFrequencyCalculation
PLY_PS_I_SoundOn
	ld a,%1000
	ld (ps_ixl),a
	ld a,e
	ld (ps_ixh),a			; сохранить ноту (арпеджио её меняет)
	ld a,b
	and 4
	call _atSound_getFrequency
	ex de,hl
	ld hl,(ps_freqp)
	ld (hl),e
	inc hl
	ld (hl),d
	ld hl,(ps_iptr)
	ld a,(ps_ixh)
	ld e,a
PLY_PS_I_SkipSoftwareFrequencyCalculation
	ld b,(hl)			; второй байт
	inc hl
	ld a,b
	and %1111
	ld (_atVAR_Reg13),a
	ld a,b				; rr b; rr b
	rra
	rra
	ld b,a
	ld a,b
	and 4				; ручная аппаратная частота?
	call _atSound_getFrequency
	ld (_atVAR_Reg11),hl
	ld hl,(ps_iptr)
	ld a,b
	and $20				; шум?
	ret z
	ld a,(hl)
	inc hl
	ld (_atVAR_Reg6),a
	ld a,(ps_ixl)			; res 3,ixl
	and $F7
	ld (ps_ixl),a
	ret
; _atSound_getFrequency: Z=0 -> ручная частота (word) + TrackPitch; иначе по ноте:
;   бит 4 B — питч инструмента (word, прибавляется к TrackPitch), бит 3 B — арпеджио (byte).
; Вход: HL = инструмент, B = флаги, E = нота. Выход: HL = частота, ps_iptr = инструмент дальше.
; Портит A, DE.
_atSound_getFrequency:
	jp nz,_atSound_getFrequency_manual
_atSound_calcFrequency:
	ld a,b
	and $10
	jp z,_atSound_calcFrequency_noPitch
	ld a,(hl)			; питч инструмента -> TrackPitch (DE = громкость/нота — не трогать!)
	inc hl
	push hl
	ld hl,ps_pitch
	add a,(hl)
	ld (hl),a
	pop hl
	ld a,(hl)
	inc hl
	push hl
	ld hl,ps_pitch+1
	adc a,(hl)			; CY от первого add: push/pop/ld hl,nn флаги не трогают
	ld (hl),a
	pop hl
_atSound_calcFrequency_noPitch
	ld a,b
	and $08
	ld a,e				; нота (and не трогает A? трогает — поэтому флаг проверяем сразу)
	jp z,_atSound_calcFrequency_noArp
	add a,(hl)			; + арпеджио
	inc hl
	cp 144
	jp c,_atSound_calcFrequency_noArp
	ld a,143
_atSound_calcFrequency_noArp
	ld (ps_iptr),hl
	ld l,a
	ld h,0
	add hl,hl
	ld de,_atLUT_notePeriods
	add hl,de
	ld e,(hl)
	inc hl
	ld d,(hl)
	ld hl,(ps_pitch)
	add hl,de			; период + TrackPitch (+ питч инструмента)
	ret
_atSound_getFrequency_manual
	ld e,(hl)			; ручная частота + TrackPitch
	inc hl
	ld d,(hl)
	inc hl
	ld (ps_iptr),hl
	ld hl,(ps_pitch)
	add hl,de
	ret
; ps_sra2: HL >>= 2 арифметически (sra h / rr l дважды)
ps_sra2:
	ld a,h
	rla
	ld a,h
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	ld a,h
	rla
	ld a,h
	rra
	ld h,a
	ld a,l
	rra
	ld l,a
	ret
; ячейки нативного плеера
ps_pitch:	dw 0			; DE' — TrackPitch
ps_iptr:	dw 0			; указатель инструмента на время расчёта частоты
ps_freqp:	dw 0			; IY -> частота канала
ps_volp:	dw 0			; IY+7 -> громкость канала
ps_ixl:		db 0			; флаги R7 канала
ps_ixh:		db 0			; сохранённая нота
ps_r7:		db 0			; AF' — сборка R7
