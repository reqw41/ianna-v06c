#!/usr/bin/env python3
"""СПЕЦИФИКАЦИЯ плеера Arkos Tracker 1 на Python — модель по ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm.

Зачем: нативный плеер на i8080 пишется НЕ переводом Z80-кода, а по этой модели. Модель — это
исполняемая спецификация: она читает тот же .mus и выдаёт ту же последовательность записей в
регистры AY по кадрам. Пока модель не совпадает с эталоном байт в байт на всех песнях и на
эффектах, писать ассемблер рано.

Запуск (сверка со стендовым эталоном Z80 из tests/music):
    python3 tools/arkos_model.py --check-z80           # все песни, 6200 кадров, с эффектами
    python3 tools/arkos_model.py --dump=music-level1.mus 600
    python3 tools/arkos_model.py --check-game=build/ay_45.txt --fxlog=build/fx_45.txt \
            --song=music-level1.mus                    # сверка с дампом игры (tools/aydump.py)

Формат .mus (Arkos Tracker 1, восстановлен из atInit/atSfxInit):
    +0..8    заголовок (сигнатура, канал сэмплов, частота YM (3 байта), частота воспроизведения)
    +9       скорость песни (SongSpeed)
    +10,+11  размер блока инструментов (word)
    +12      таблица инструментов (word на инструмент; адреса АБСОЛЮТНЫЕ — песня грузится по
             фиксированному адресу, на Векторе $C980, эффекты $D980)
    +12+size пре-линкер первого паттерна: PatternHeight, Transp1, Transp2, Transp3,
             SpecialTrackAddr (word); дальше — линкер.
Инструмент: [скорость][retrig] далее поток «звуковых» байтов (см. play_sound).

ВАЖНО (проверено моделью): в _atPlaySound первый `rr b` вносит в бит 7 регистра B флаг переноса,
оставшийся от сдвига TrackPitch (`sra h/rr l`). Этот бит НИКОГДА не проверяется дальше по коду
(во всех ветках он уходит в биты 5-6, а тестируются 0-4 и 5 после сдвигов) — нативному плееру
эмулировать этот перенос не нужно. Модель считает его честно и умеет сверить оба варианта
(--check-carry).
"""
import sys, os, re, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAYER_ASM = ROOT / 'ref/msx2/src/ArkosTrackerPlayer_CPC_MSX.asm'
MUS_DIR = ROOT / 'ref/msx2/src'
SONG_BASE = 0xC980      # адрес песни в окне квазидиска (как в игре: music.asm MUSIC_WIN)
SFX_BASE = 0xD980       # адрес набора эффектов (SFX_WIN)

R13_RETRIG = 0xFE       # _atDEF_R13RetrigValue


def load_note_periods():
    """Таблица периодов из исходника плеера (ветка atCNF_ZXPT=1 — Spectrum/Pentagon)."""
    txt = PLAYER_ASM.read_text(errors='replace')
    i = txt.index('_atLUT_notePeriods')
    j = txt.index('else', i)
    vals = []
    for line in txt[i:j].split('\n'):
        line = line.split(';')[0]
        m = re.search(r'\bdw\s+(.*)', line)
        if m:
            vals += [int(v) for v in m.group(1).split(',') if v.strip()]
    assert len(vals) == 144, f'ждём 144 периода, получено {len(vals)}'
    return vals


NOTE_PERIODS = load_note_periods()

# Раскладка _atVAR_AY3Registers (индексы внутри массива; дырки — как в оригинале)
I_R0, I_R1, I_R2, I_R3, I_R4, I_R5, I_R6 = 0, 1, 2, 3, 4, 5, 6
I_R8, I_DIGI, I_R9, I_UNUSED, I_R10, I_R11, I_R12, I_R13 = 7, 8, 9, 10, 11, 12, 13, 14


class Track:
    """Канал песни: своё состояние трека и инструмента (самомодифицируемые операнды оригинала)."""
    __slots__ = ('ptr', 'wait', 'volume', 'note', 'pitch', 'pitch_add', 'transp',
                 'inst_ptr', 'inst_addr', 'inst_speed', 'inst_speed_ctr', 'inst_lut')

    def __init__(self):
        self.ptr = 0; self.wait = 1; self.volume = 0; self.note = 0
        self.pitch = 0; self.pitch_add = 0; self.transp = 0
        self.inst_ptr = 0; self.inst_addr = 0; self.inst_speed = 6; self.inst_speed_ctr = 1
        self.inst_lut = 0


class Sfx:
    __slots__ = ('pitch', 'volume', 'note', 'instrument', 'speed', 'speed_ctr')

    def __init__(self):
        self.pitch = 0; self.volume = 0; self.note = 0
        self.instrument = 0; self.speed = 6; self.speed_ctr = 1


class Arkos:
    """Плеер целиком. mem — 64К байт: песня по SONG_BASE, эффекты по SFX_BASE."""

    def __init__(self, mem, carry_exact=True):
        self.m = mem
        self.carry_exact = carry_exact
        self.ay = [0] * 15
        self.r13_lock = 255           # операнд `cp 255` в PLY_PSGReg13_Retrig
        self.digidrum = 0
        self.song_speed = 1; self.song_speed_ctr = 1
        self.pattern_height = 1; self.pattern_height_ctr = 1
        self.linker = 0; self.special_track_addr = 0; self.special_track_ptr = 0
        self.wait_special = 1
        self.tr = [Track(), Track(), Track()]
        self.sfx = [Sfx(), Sfx(), Sfx()]
        self.sfx_inst_table = 0
        self.stat = __import__('collections').Counter()   # перепись веток формата (--census)
        self.ixl = 0                  # IXL оригинала: биты регистра 7 текущего канала.
                                      # ЖИВЁТ МЕЖДУ ВЫЗОВАМИ: PLY_PS_EndSFX (звук эффекта кончился)
                                      # возвращает адрес 0, НЕ трогая IXL, и в регистр 7 идёт
                                      # значение от музыкального канала — это слышно как «шум не
                                      # открылся на кадр окончания эффекта».

    # ---- служебное ----
    def b(self, a):
        return self.m[a & 0xFFFF]

    def w(self, a):
        return self.m[a & 0xFFFF] | (self.m[(a + 1) & 0xFFFF] << 8)

    # ---- API ----
    def at_init(self, de):
        """atInit: DE = адрес песни."""
        hl = de + 9
        self.song_speed = self.b(hl); hl += 1
        size = self.w(hl); hl += 2
        for t in self.tr:
            t.inst_lut = hl
        hl += size
        self.pattern_height = self.b(hl); hl += 1
        for t in self.tr:
            t.transp = self.b(hl); hl += 1
        self.special_track_addr = self.w(hl); hl += 2
        self.linker = hl
        self.song_speed_ctr = 1
        self.pattern_height_ctr = 1
        self.ay[I_R13] = 0xFF
        ip = self.w(self.tr[0].inst_lut) + 2      # инструмент 0, пропустить его заголовок
        for t in self.tr:
            t.inst_ptr = ip

    def at_sfx_init(self, de):
        self.sfx_inst_table = de + 12
        self.at_sfx_stop_all()

    def at_sfx_stop_all(self):
        for s in self.sfx:
            s.instrument = 0

    def at_sfx_stop(self, ch):
        self.sfx[ch].instrument = 0

    def at_sfx_play(self, ch, num, vol, note, speed, pitch):
        """atSfxPlay: A=канал(0..2), L=номер, H=громкость(0..15), E=нота, D=скорость, BC=питч."""
        s = self.sfx[ch]
        s.pitch = pitch & 0xFFFF
        s.note = note & 0xFF
        s.volume = (15 - vol) & 0xFF          # инвертированная громкость
        hl = self.w(self.sfx_inst_table + ((num * 2) & 0xFFFF))
        a = speed & 0xFF
        if a == 0:
            a = self.b(hl)                    # скорость из инструмента
        s.speed = a
        s.speed_ctr = a
        s.instrument = (hl + 2) & 0xFFFF      # пропустить скорость и retrig

    def at_stop(self):
        """atStop: обнуляет Reg8, digidrum, Reg9 (djnz-цикл на 3 байта — R10 остаётся, как в оригинале)."""
        self.ay[I_R8] = 0; self.ay[I_DIGI] = 0; self.ay[I_R9] = 0
        return self.ay3_update(0b00111111)

    # ---- главный тик ----
    def at_play(self):
        """Один кадр. Возвращает список записей (регистр, значение) в порядке вывода."""
        self.digidrum = 0
        a = (self.song_speed_ctr - 1) & 0xFF
        if a == 0:
            self._read_pattern()
            self._read_special_track()
            for i in range(3):
                self._read_track(i)
            a = self.song_speed
        self.song_speed_ctr = a
        r7 = self._play_channels()
        return self.ay3_update(r7)

    # ---- линкер/паттерн ----
    def _read_pattern(self):
        a = (self.pattern_height_ctr - 1) & 0xFF
        if a != 0:
            self.pattern_height_ctr = a
            return
        hl = self.linker
        flags = self.b(hl); hl += 1
        self.stat['линкер: новый паттерн'] += 1
        if flags & 1:                       # конец песни — переход на позицию зацикливания
            self.stat['линкер: зацикливание песни'] += 1
            hl = self.w(hl)
            flags = self.b(hl); hl += 1
        bit = 1                             # бит 0 уже разобран (конец песни)
        for t in self.tr:                   # транспозиции каналов 1..3
            if flags & (1 << bit):
                t.transp = self.b(hl); hl += 1
            bit += 1
        for t in self.tr:                   # адреса треков
            t.ptr = self.w(hl); hl += 2
        if flags & (1 << bit):              # бит 4: высота паттерна
            self.stat['линкер: новая высота паттерна'] += 1
            self.pattern_height = self.b(hl); hl += 1
        bit += 1
        if flags & (1 << bit):              # бит 5: новый спец-трек
            self.stat['линкер: новый спец-трек'] += 1
            self.special_track_addr = self.w(hl); hl += 2
        self.linker = hl
        self.special_track_ptr = self.special_track_addr
        self.wait_special = 1
        for t in self.tr:
            t.wait = 1
        self.pattern_height_ctr = self.pattern_height

    def _read_special_track(self):
        a = (self.wait_special - 1) & 0xFF
        if a != 0:
            self.wait_special = a
            return
        hl = self.special_track_ptr
        a = self.b(hl); hl += 1
        cy = a & 1; a >>= 1                 # srl a: данные (1) или ожидание (0)?
        if cy:
            cy2 = a & 1; a >>= 1            # srl a: скорость (0) или digidrum (1)?
            if a == 0:                      # escape-код: значение в следующем байте
                a = self.b(hl); hl += 1
            if a != self.b(hl - 1) >> 2:
                self.stat['спец-трек: escape-код'] += 1
            if cy2:
                self.stat['спец-трек: ДИГИДРАМ (не поддержан игрой)'] += 1
                self.digidrum = a
            else:
                self.stat['спец-трек: смена скорости'] += 1
                self.song_speed = a
            a = 1
        self.special_track_ptr = hl
        self.wait_special = a

    # ---- чтение трека ----
    def _read_track_data(self, hl):
        """_atReadTrack. Возвращает (hl, wait|None, d, e, b_instr, pitch_add)."""
        a = self.b(hl); hl += 1
        cy = a & 1; a >>= 1                 # srl a: полная оптимизация?
        if cy:                              # только нота, без питча/громкости, тот же инструмент
            self.stat['трек: полная оптимизация'] += 1
            d = 0b01000000
            e = (a - 1) & 0xFF
            if a - 1 >= 0:
                return hl, None, d, e, 0, 0
            e = self.b(hl); hl += 1         # escape-код (0): нота в следующем байте
            return hl, None, d, e, 0, 0
        a -= 32
        if a < 0:                           # 0-31 = ожидание
            return hl, (a + 32) & 0xFF, 0, 0, 0, 0
        if a == 0:                          # escape-код для дальних нот
            a = (self.b(hl) + 1) & 0xFF; hl += 1
        e = (a - 1) & 0xFF                  # нота
        d = self.b(hl); hl += 1             # параметры
        pitch_add = 0
        if d & 0x80:                        # питч?
            self.stat['трек: PitchAdd (портаменто)'] += 1
            pitch_add = self.w(hl); hl += 2
        instr = 0
        if d & 0x20:                        # новый инструмент?
            instr = self.b(hl); hl += 1
        return hl, None, d, e, instr, pitch_add

    def _read_track(self, i):
        t = self.tr[i]
        a = (t.wait - 1) & 0xFF
        if a != 0:
            t.wait = a
            return
        hl, wait, d, e, instr, pitch_add = self._read_track_data(t.ptr)
        t.ptr = hl
        if wait is not None:
            t.wait = wait
            return
        if d & 1:                           # громкость?
            t.volume = (d >> 1) & 0b1111
        if d & 0x80:                        # новый питч?
            t.pitch_add = pitch_add
        if d & 0x40:                        # нота?
            t.note = (e + t.transp) & 0xFF
            t.pitch = 0
            if d & 0x20:                    # новый инструмент?
                hl = self.w(t.inst_lut + ((instr * 2) & 0xFFFF))
                t.inst_speed = self.b(hl); hl += 1
                t.inst_speed_ctr = t.inst_speed
                retrig = self.b(hl); hl += 1
                if retrig != 0:
                    self.r13_lock = retrig
                t.inst_addr = hl
            else:                           # тот же инструмент — перезапустить с его начала
                hl = t.inst_addr
                t.inst_speed_ctr = t.inst_speed
            t.inst_ptr = hl
        t.wait = 1

    # ---- проигрывание каналов ----
    def _play_channels(self):
        """Каналы 3, 2, 1 (в порядке оригинала) + эффекты; возвращает значение регистра 7."""
        r7 = 0
        for ch in (2, 1, 0):
            t = self.tr[ch]
            freq_i = (I_R0, I_R2, I_R4)[ch]
            vol_i = (I_R8, I_R9, I_R10)[ch]
            t.pitch = (t.pitch + t.pitch_add) & 0xFFFF
            pitch, cy = sra2(t.pitch)
            hl = self.play_sound(t.inst_ptr, t.volume, t.note, pitch, freq_i, vol_i,
                                 False, cy if self.carry_exact else 0)
            a = (t.inst_speed_ctr - 1) & 0xFF
            if a == 0:
                t.inst_ptr = hl
                a = t.inst_speed
            t.inst_speed_ctr = a
            # эффект на этом канале
            s = self.sfx[ch]
            if s.instrument:
                hl = self.play_sound(s.instrument, s.volume, s.note, s.pitch,
                                     freq_i, vol_i, True, 0)
                if hl == 0:
                    s.instrument = 0        # инструмент кончился
                else:
                    a = (s.speed_ctr - 1) & 0xFF
                    if a == 0:
                        s.instrument = hl
                        a = s.speed
                    s.speed_ctr = a
            # сборка регистра 7: ((ixl3 << 1 | ixl2) << 1) | ixl1
            r7 = ((r7 << 1) | self.ixl) & 0xFF if ch != 2 else self.ixl
        return r7

    def play_sound(self, hl, inv_vol, note, pitch, freq_i, vol_i, is_sfx, cy_in):
        """_atPlaySound. hl — указатель инструмента, inv_vol = D, note = E, pitch = DE'.
        Возвращает новый hl (0 = звук эффекта кончился). Биты регистра 7 — в self.ixl."""
        ay = self.ay
        while True:
            b = self.b(hl); hl += 1
            b, cy = rr(b, cy_in)
            if cy:
                # ---- аппаратный звук ----
                self.stat['звук: аппаратный'] += 1
                b, cy = rr(b, 1)
                if cy:                                   # retrig — только на первом шаге строки
                    self.stat['звук: retrig R13'] += 1
                    if self.tr[0].inst_speed_ctr == self.tr[0].inst_speed:
                        self.r13_lock = R13_RETRIG
                if b & 2:                                # Loop / Independent
                    self.stat['звук: Loop/Independent'] += 1
                    if b & 1:                            # звук кончился
                        if is_sfx:
                            return 0        # IXL не трогаем — как в PLY_PS_EndSFX
                        hl = self.w(hl)                  # новый указатель, перезапуск инструмента
                        cy_in = 0
                        continue
                    # ---- Independent ----
                    self.stat['звук: Independent'] += 1
                    ay[vol_i] = 16
                    if b & 0x20:                         # звук?
                        self.ixl = 0b1000
                        saved_note = note
                        hl, freq = self.get_frequency(hl, b, note, pitch, manual=bool(b & 4))
                        ay[freq_i] = freq & 0xFF; ay[freq_i + 1] = freq >> 8
                        note = saved_note
                    else:
                        self.ixl = 0b1001
                    b = self.b(hl); hl += 1
                    ay[I_R13] = b & 0b1111
                    b, _ = rr(b, 0); b, _ = rr(b, 0)
                    hl, freq = self.get_frequency(hl, b, note, pitch, manual=bool(b & 4))
                    ay[I_R11] = freq & 0xFF; ay[I_R12] = freq >> 8
                    if not (b & 0x20):                   # шум?
                        return hl
                    ay[I_R6] = self.b(hl); hl += 1
                    self.ixl &= ~8
                    return hl
                # ---- Software/Hardware Dependent ----
                ay[vol_i] = 16
                self.ixl = 0b1000
                c = self.b(hl); hl += 1
                ay[I_R13] = c & 0b1111
                n = 7 - ((c >> 4) & 7)                   # сдвиг инвертирован в данных
                if b & 1:
                    self.stat['звук: Software Dependent'] += 1
                    # Software Dependent: программная частота -> канал, сдвиг вправо -> R11/R12
                    hl, freq = self.get_frequency(hl, b, note, pitch, manual=bool(b & 4))
                    ay[freq_i] = freq & 0xFF; ay[freq_i + 1] = freq >> 8
                    cy = 0
                    for _ in range(n):
                        cy = freq & 1; freq >>= 1
                    if cy:
                        freq = (freq + 1) & 0xFFFF       # округление по вытесненному биту
                    if b & 0x20:                         # аппаратный питч (word из инструмента)
                        freq = (freq + self.w(hl)) & 0xFFFF; hl += 2
                    ay[I_R11] = freq & 0xFF; ay[I_R12] = freq >> 8
                else:
                    self.stat['звук: Hardware Dependent'] += 1
                    # Hardware Dependent: аппаратная частота -> R11/R12, сдвиг влево -> канал
                    hl, freq = self.get_frequency(hl, b, note, pitch, manual=bool(b & 4))
                    ay[I_R11] = freq & 0xFF; ay[I_R12] = freq >> 8
                    for _ in range(n):
                        freq = (freq << 1) & 0xFFFF      # без округления
                    if b & 0x20:                         # программный питч
                        freq = (freq + self.w(hl)) & 0xFFFF; hl += 2
                    ay[freq_i] = freq & 0xFF; ay[freq_i + 1] = freq >> 8
                if not (c & 0x80):                       # шум?
                    return hl
                ay[I_R6] = self.b(hl); hl += 1
                self.ixl = 0
                return hl
            # ---- программный звук ----
            b, cy = rr(b, 0)
            if not cy:
                v = b & 0b1111
                self.stat['звук: программный, один байт'] += 1
                if v == 0:                               # нулевая громкость — звука нет
                    ay[vol_i] = 0
                    self.ixl = 0b1001
                    return hl
                self.ixl = 0b1000
                a = v - inv_vol
                ay[vol_i] = a if a >= 0 else 0
                b, _ = rr(b, 0)
                hl, freq = self.calc_frequency(hl, b, note, pitch)
                ay[freq_i] = freq & 0xFF; ay[freq_i + 1] = freq >> 8
                return hl
            # нужен второй байт
            self.stat['звук: программный, второй байт'] += 1
            self.ixl = 0b1000
            c = self.b(hl); hl += 1
            noise = c & 0b11111
            if noise:
                ay[I_R6] = noise
                self.ixl = 0
            a = (b & 0b1111) - inv_vol
            ay[vol_i] = a if a >= 0 else 0
            if not (c & 0x20):                           # звука нет
                self.stat['звук: второй байт без тона'] += 1
                self.ixl = (self.ixl + 1) & 0xFF          # inc ixl
                return hl
            b, _ = rr(b, 0)
            hl, freq = self.get_frequency(hl, b, note, pitch, manual=bool(c & 0x40))
            ay[freq_i] = freq & 0xFF; ay[freq_i + 1] = freq >> 8
            return hl

    def get_frequency(self, hl, b, note, pitch, manual):
        if manual:
            self.stat['частота: ручная (word)'] += 1
            return (hl + 2) & 0xFFFF, (self.w(hl) + pitch) & 0xFFFF
        return self.calc_frequency(hl, b, note, pitch)

    def calc_frequency(self, hl, b, note, pitch):
        """Частота по ноте: + питч инструмента (бит 4 B, word), + арпеджио (бит 3 B, byte)."""
        if b & 0x10:
            self.stat['частота: питч инструмента'] += 1
            pitch = (pitch + self.w(hl)) & 0xFFFF
            hl += 2
        a = note
        if b & 0x08:
            self.stat['частота: арпеджио'] += 1
            a = (a + self.b(hl)) & 0xFF
            hl += 1
            if a >= 144:
                a = 143
        return hl & 0xFFFF, (NOTE_PERIODS[a] + pitch) & 0xFFFF

    # ---- вывод в AY ----
    def ay3_update(self, r7):
        ay = self.ay
        out = [(0, ay[I_R0]), (1, ay[I_R1]), (2, ay[I_R2]), (3, ay[I_R3]),
               (4, ay[I_R4]), (5, ay[I_R5]), (6, ay[I_R6]),
               (7, (r7 & 0xBF) | 0x80),
               (8, ay[I_R8]), (9, ay[I_R9]), (10, ay[I_R10]),
               (11, ay[I_R11]), (12, ay[I_R12])]
        v = ay[I_R13]
        if v != self.r13_lock:               # R13 пишется только при смене формы огибающей
            out.append((13, v))
            self.r13_lock = v
        return out


def rr(v, cy_in):
    """Z80 `rr r`: v = (v >> 1) | (cy_in << 7); возвращает (v, вытесненный бит)."""
    return ((v >> 1) | (cy_in << 7)) & 0xFF, v & 1


def sra2(v):
    """`sra h / rr l` дважды: арифметический сдвиг 16-битного значения вправо на 2.
    Возвращает (результат, последний вытесненный бит) — этот бит попадает в CY."""
    s = v - 0x10000 if v & 0x8000 else v
    cy = (v >> 1) & 1
    return (s >> 2) & 0xFFFF, cy


# ================================ стенды ================================

def make_player(song, sfx='iannafx.mus', carry_exact=True):
    mem = bytearray(0x10000)
    d = (MUS_DIR / song).read_bytes()
    mem[SONG_BASE:SONG_BASE + len(d)] = d
    d = (MUS_DIR / sfx).read_bytes()
    mem[SFX_BASE:SFX_BASE + len(d)] = d
    p = Arkos(mem, carry_exact)
    p.at_init(SONG_BASE)
    p.at_sfx_init(SFX_BASE)
    return p


# Ветки формата, которых В ДАННЫХ ИГРЫ НЕТ (перепись --census) и которые нативный плеер
# сознательно НЕ реализует. Гейт --check-unused обязан падать, если они появятся в .mus.
NOT_IMPLEMENTED = [
    'спец-трек: ДИГИДРАМ (не поддержан игрой)',
    'звук: retrig R13',
    'звук: Software Dependent',
    'звук: Hardware Dependent',
]
# «звук: Independent» РЕАЛИЗОВАН: встречается 3 раза в эффекте 19 (FX_LONGJUMP) — единственное
# место во всей игре, где трогаются R11/R12/R13 (аппаратная огибающая).

ALL_BRANCHES = [
    'линкер: новый паттерн', 'линкер: зацикливание песни', 'линкер: новая высота паттерна',
    'линкер: новый спец-трек', 'спец-трек: escape-код', 'спец-трек: смена скорости',
    'спец-трек: ДИГИДРАМ (не поддержан игрой)', 'трек: полная оптимизация',
    'трек: PitchAdd (портаменто)', 'звук: аппаратный', 'звук: retrig R13',
    'звук: Loop/Independent', 'звук: Independent', 'звук: Software Dependent',
    'звук: Hardware Dependent', 'звук: программный, один байт', 'звук: программный, второй байт',
    'звук: второй байт без тона', 'частота: ручная (word)', 'частота: питч инструмента',
    'частота: арпеджио',
]

# Расписание эффектов эталонного стенда tests/music/z80_drv_sfx.asm (кадр -> номер эффекта),
# канал 1, громкость 15, нота 36, скорость 0, питч 0 — как FX_Play в игре.
SFX_TAB = [(100 + 0 * 256, 1), (44 + 1 * 256, 2), (188 + 2 * 256, 3), (176 + 4 * 256, 4),
           (220 + 5 * 256, 5), (230 + 5 * 256, 6), (208 + 7 * 256, 7), (40 + 10 * 256, 1),
           (228 + 12 * 256, 3), (4 + 16 * 256, 2), (136 + 19 * 256, 5), (112 + 23 * 256, 4)]


def run(p, frames, sfx_tab=None):
    """Прогон N кадров; sfx_tab — [(номер кадра, эффект)], триггер ПОСЛЕ atPlay (как в стенде)."""
    sched = dict(sfx_tab or [])
    out = []
    for f in range(frames):
        out.append(p.at_play())
        if f in sched:
            p.at_sfx_play(1, sched[f], 15, 36, 0, 0)
    return out


N_SFX = 21          # FX_SWORD1..FX_LEVEL_UP (music.asm)


def census():
    """Перепись веток формата: все песни по 6200 кадров + каждый из 21 эффекта на каждом канале."""
    import collections
    tot = collections.Counter()
    for song in sorted(f.name for f in MUS_DIR.glob('music-*.mus')):
        p = make_player(song)
        run(p, 6200, SFX_TAB)
        tot.update(p.stat)
    for ch in range(3):
        for n in range(1, N_SFX + 1):
            p = make_player('music-level1.mus')
            run(p, 30)
            p.at_sfx_play(ch, n, 15, 36, 0, 0)
            run(p, 300)
            tot.update(p.stat)
    return tot


def check_z80(carry_exact=True):
    """Сверка модели с эталоном Z80 (tests/music/z80_stream_sfx.json, генерится z80_run_sfx.js)."""
    import subprocess
    td = ROOT / 'tests/music'
    songs = sorted(f.name for f in MUS_DIR.glob('music-*.mus'))
    bad_total = 0
    for song in songs:
        subprocess.run(['node', 'z80_run_sfx.js'], cwd=td, check=True, capture_output=True,
                       env={**os.environ, 'SONG': song})
        ref = json.load(open(td / 'z80_stream_sfx.json'))
        got = run(make_player(song, carry_exact=carry_exact), len(ref), SFX_TAB)
        bad = [i for i in range(len(ref)) if [list(x) for x in got[i]] != ref[i]]
        bad_total += len(bad)
        print(f'{song:22s} кадров {len(ref)}, расхождений {len(bad)}' +
              (f' — первое в кадре {bad[0]}' if bad else ' — ИДЕНТИЧНО'), flush=True)
        if bad:
            i = bad[0]
            print('   эталон:', ref[i])
            print('   модель:', [list(x) for x in got[i]])
    print('ИТОГ:', 'МОДЕЛЬ СОВПАДАЕТ С ОРИГИНАЛОМ' if not bad_total else f'расхождений {bad_total}')
    return bad_total


def check_game(ay_path, fx_path, song, songmap=None):
    """Сверка модели с дампом ИГРЫ (tools/aydump.py --out=... --fxlog=...).

    Дамп адресован номером вызова плеера (MUSIC_Play из ISR) начиная с загрузки. События из
    fxlog: L = MUSIC_Load (atInit + atSfxInit), F = FX_Play (atSfxPlay канал 1, громкость 15,
    нота 36), S = MUSIC_Stop (atStop + atSfxStopAll — atStop сам пишет в AY). Записи, сделанные
    между вызовами плеера, игра относит к текущему номеру вызова — модель делает так же."""
    ref = {}
    for line in open(ay_path):
        c, r, v = (int(x) for x in line.split())
        ref.setdefault(c, []).append((r, v))
    events = {}
    for line in open(fx_path):
        c, k, n = line.split()
        events.setdefault(int(c), []).append((k, int(n)))
    mem = bytearray(0x10000)
    d = (MUS_DIR / song).read_bytes(); mem[SONG_BASE:SONG_BASE + len(d)] = d
    d = (MUS_DIR / 'iannafx.mus').read_bytes(); mem[SFX_BASE:SFX_BASE + len(d)] = d
    p = Arkos(mem)
    got = {}
    last = max(max(ref), max(events, default=0))
    for c in range(0, last + 1):
        if c:
            got.setdefault(c, []).extend(p.at_play())
        for k, n in events.get(c, []):
            if k == 'L':
                f = (songmap or {}).get(n)
                if f:                      # песня меню/интро лежит в окне вместо песни уровня
                    d = (MUS_DIR / f).read_bytes()
                    mem[SONG_BASE:SONG_BASE + 0x1000] = bytes(0x1000)
                    mem[SONG_BASE:SONG_BASE + len(d)] = d
                elif songmap:
                    d = (MUS_DIR / song).read_bytes()
                    mem[SONG_BASE:SONG_BASE + 0x1000] = bytes(0x1000)
                    mem[SONG_BASE:SONG_BASE + len(d)] = d
                p.at_init(SONG_BASE); p.at_sfx_init(SFX_BASE)
            elif k == 'F':
                p.at_sfx_play(1, n, 15, 36, 0, 0)
            elif k == 'S':
                got.setdefault(c, []).extend(p.at_stop())
                p.at_sfx_stop_all()
            elif k == 'Z':
                # игра сама гасит шум и огибающую после загрузки экрана (ld (_atVAR_Reg6),a ...)
                p.ay[I_R6] = p.ay[I_R11] = p.ay[I_R12] = n
    bad = [c for c in range(1, last + 1) if got.get(c, []) != ref.get(c, [])]
    if bad:
        c = bad[0]
        print(f'  первое расхождение на вызове {c}:\n   игра:   {ref.get(c)}\n   модель: {got.get(c)}')
    print(f'сверка с игрой ({song}): вызовов {last}, расхождений {len(bad)}' +
          (' — ИДЕНТИЧНО' if not bad else ''))
    return len(bad)


def main():
    args = sys.argv[1:]
    if '--check-z80' in args:
        sys.exit(1 if check_z80() else 0)
    if '--check-carry' in args:
        # доказательство, что перенос из сдвига TrackPitch не влияет на звук
        for song in sorted(f.name for f in MUS_DIR.glob('music-*.mus')):
            a = run(make_player(song, carry_exact=True), 6200, SFX_TAB)
            b = run(make_player(song, carry_exact=False), 6200, SFX_TAB)
            print(f'{song:22s} {"совпало" if a == b else "РАЗОШЛОСЬ"}')
        return
    if '--census' in args or '--check-unused' in args:
        tot = census()
        print('перепись веток формата: все песни по 6200 кадров + все 21 эффект на всех каналах:')
        for k, v in sorted(tot.items(), key=lambda x: -x[1]):
            print(f'  {v:9d}  {k}')
        print('НЕ ВСТРЕТИЛОСЬ (в нативном плеере не реализовано):')
        for k in ALL_BRANCHES:
            if k not in tot: print('  ', k)
        used = [k for k in NOT_IMPLEMENTED if tot.get(k)]
        if used:
            print('ОТКАЗ: в данных встретились ветки, которых нет в нативном плеере:', used)
            sys.exit(1)
        print('ГЕЙТ ПРОЙДЕН: ни одна нереализованная ветка в данных не встречается')
        return
    cg = next((a[13:] for a in args if a.startswith('--check-game=')), None)
    if cg:
        fx = next((a[8:] for a in args if a.startswith('--fxlog=')), None)
        song = next((a[7:] for a in args if a.startswith('--song=')), 'music-level1.mus')
        sm = next((a[10:] for a in args if a.startswith('--songmap=')), None)
        sm = dict((int(k), v) for k, v in (x.split(':') for x in sm.split(','))) if sm else None
        sys.exit(1 if check_game(cg, fx, song, sm) else 0)
    dump = next((a[7:] for a in args if a.startswith('--dump=')), None)
    if dump:
        n = int(next((a for a in args if a.isdigit()), '600'))
        for i, fr in enumerate(run(make_player(dump), n, SFX_TAB)):
            print(i, ' '.join(f'{r}:{v}' for r, v in fr))
        return
    print(__doc__)


if __name__ == '__main__':
    main()
