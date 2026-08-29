# Ручные замены для мест, где автоматический перевод даёт неточные флаги.
# Ключ: (имя файла, номер строки оригинала). Значение: список строк i8080-кода.
OVERRIDES = {
    # depack.asm: `rl c` / `jr nc,apget4bits` / `ld a,b` / `jr z,apwritebyte`
    # Z80: Z после rl c = (C==0). i8080 RAL не ставит Z -> считаем явно перед ld a,b.
    ('depack.asm', 20): ['ld (z_a),a', 'ld a,c', 'rla', 'ld c,a', 'ld a,(z_a)'],   # A = битовый буфер, беречь!
    ('depack.asm', 22): ['ld a,c', 'or a', 'ld a,b'],          # Z=(C==0), CY здесь дальше не нужен (and a)
    # depack.asm: `ld c,(hl)` / `rr c` / `ret z` / ... `ld a,2` / `adc a,b`
    # нужны и Z (C==0 -> конец потока), и CY (младший бит) для adc.
    ('depack.asm', 34): ['ld a,c', 'rra', 'ld c,a', 'push af', 'or a', 'jp nz,apb3_nz', 'pop af', 'ret', 'apb3_nz:', 'pop af'],
    ('depack.asm', 35): [],
}
