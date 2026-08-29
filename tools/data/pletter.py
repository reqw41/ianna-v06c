"""Декодер Pletter (uitpakmode=1) — точный порт pletter.asm (Manuel Pazos) из репо Ianna.
Битовый буфер эмулируется как в Z80-коде: A с битом-сторожем, add a,a / rla."""
def depack(src):
    pos = 1
    out = bytearray([src[0]])
    a = 128
    def getbit():
        nonlocal a, pos
        cy = (a >> 7) & 1
        a = (a << 1) & 0xff
        if a == 0:                      # буфер пуст: ld a,(hl); rla (вдвигает cy)
            nb = src[pos]; pos += 1
            cy2 = (nb >> 7) & 1
            a = ((nb << 1) & 0xff) | cy
            cy = cy2
        return cy
    while True:
        if getbit() == 0:               # литерал
            out.append(src[pos]); pos += 1
            continue
        hl = 1                          # длина: interlaced Elias-gamma
        while True:
            if getbit() == 0:
                break
            hl = (hl << 1) | getbit()
            if hl > 0xffff:             # adc hl,hl с переносом = конец потока
                return bytes(out)
        length = hl + 1
        c = src[pos]; pos += 1
        b = 0
        if c & 0x80:                    # длинное смещение: 3 бита + флаг (режим 1)
            b = getbit(); b = (b << 1) | getbit(); b = (b << 1) | getbit()
            if getbit():
                b += 1; c &= 0x7f
        offset = ((b << 8) | c) + 1
        for _ in range(length):
            out.append(out[-offset])
