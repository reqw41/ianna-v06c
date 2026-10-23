"""Раскладка дискеты Ianna — общая для build_fdd.py (образ) и build_vec.py (константы загрузчика).

Дискета — МикроДОС на 82 дорожки (839 680 Б, как у дискет «Базиса» и Tony): её грузит штатное ПЗУ
Вектора-06Ц и читают CP/M 4.0 Вектора Турбо+ и плагин FAR MultiImage. Дорожка = обе стороны = 10 секторов
по 1024 Б; LBA = дорожка * 10 + сектор.

    дорожки 0..3      загрузочная область МикроДОС (секторы 0..39): дескриптор, ROM, экран меню в хвосте дорожки 3
    дорожка 4, 0..3   каталог МикроДОС (4 сектора, 128 записей)
    LBA 44..75        IANNA.COM — копия ROM для CP/M и ПЗУ Турбо+ (32 КБ, блоки 2..17)
    LBA 76..79        хвост дорожки 7 — библиотека банков
    дорожки 8..74     наборы уровней и библиотека банков
    дорожки 75..81    семь слайдов (80 и 81 — за пределами диска CP/M: DSM = 379)
Всё от LBA 76 до конца диска CP/M записано в каталог файлом IANNA.DAT, чтобы CP/M не считала место свободным.
"""
SEC = 1024
TRACK = 10 * SEC
TRACKS = 82
DISK = TRACKS * TRACK                 # 839 680 Б
MENU_TRACK, MENU_SEC = 3, 3           # экран меню (сектор с 1)
DIR_LBA = 40                          # каталог: блоки 0 и 1
DATA_LBA = 44                         # блок 2
COM_LBA = 44                          # IANNA.COM
LEVEL_TRACKS = list(range(8, 75))     # наборы уровней и библиотека банков
LIB_TAIL = (7, 4)                     # дорожка 7: свободны последние 4 сектора (за IANNA.COM)
PIC_TRACK = 75                        # слайды 0..6 — дорожки 75..81
DAT_LBA = 76                          # IANNA.DAT — от хвоста дорожки 7 до конца диска CP/M
DSM = 379                             # последний блок CP/M: LBA 798..799
# Блок параметров диска МикроДОС (байты 5..30 дескриптора): сектор 1 КБ, 5 секторов, 80 дорожек, SPT = 40,
# блок 2 КБ (BSH = 4, BLM = 15), DSM = 379, DRM = 127, AL0 = C0h, OFF = 8. С DSM = 391 CP/M 4.0 Турбо+
# отвечает «Disk I/O error» (найдено в порте Tony).
DPB = bytes.fromhex('00000101010301050050002800040f007b017f00c00020000800')


def msdos_dir(files):
    """Каталог МикроДОС (CP/M 2.2) на 4 сектора: files = [((имя, расш), LBA начала, байт)].
    Блок 2 КБ = 2 сектора, блок 0 — LBA 40; в записи 8 номеров блоков по 2 Б (DSM > 255), до 16 КБ на
    экстент (EXM = 0), RC — записи по 128 Б в экстенте. Свободные записи — E5h. По образцу порта Tony."""
    d = bytearray(b'\xe5' * (DATA_LBA - DIR_LBA) * SEC)
    used, e = set(), 0
    for (name, ext), lba, size in files:
        assert (lba - DIR_LBA) % 2 == 0 and lba >= DATA_LBA, (name, lba)
        b0, nblk = (lba - DIR_LBA) // 2, (size + 2047) // 2048
        blocks = list(range(b0, b0 + nblk))
        assert not used & set(blocks) and blocks[-1] <= DSM, (name, blocks[0], blocks[-1])
        used |= set(blocks)
        recs = (size + 127) // 128
        for x in range(0, len(blocks), 8):
            ent = bytearray(32)
            ent[1:9] = name.upper().ljust(8).encode()
            ent[9:12] = ext.upper().ljust(3).encode()
            ent[12] = (x // 8) & 31
            ent[14] = (x // 8) >> 5
            ent[15] = min(128, recs - x * 16)
            for i, blk in enumerate(blocks[x:x + 8]):
                ent[16 + 2 * i:18 + 2 * i] = blk.to_bytes(2, 'little')
            d[e * 32:e * 32 + 32] = ent
            e += 1
        if recs % 128 == 0:
            # файл кончается ровно на границе экстента: плагин FAR MultiImage видит файл, только найдя неполный
            # последний экстент, — добавить пустой (RC = 0, без блоков); cpmtools его принимает
            ent = bytearray(32)
            ent[1:9] = name.upper().ljust(8).encode()
            ent[9:12] = ext.upper().ljust(3).encode()
            ent[12] = (recs // 128) & 31
            ent[14] = (recs // 128) >> 5
            d[e * 32:e * 32 + 32] = ent
            e += 1
    assert e <= 128, 'каталог МикроДОС переполнен'
    return d
