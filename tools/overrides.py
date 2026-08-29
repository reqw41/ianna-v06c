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

    # ---- Arkos-плеер: самомодифицируемые jr $+2 в развёрнутые цепочки сдвигов -> циклы.
    # Смещение = 4*k пар (k = 0..7); SD: пропустить k из 8 пар (srl h; rr l) = 8-k сдвигов вправо,
    # затем округление по CY (jr nc,$+3 / inc hl). HD: 7 пар (sla l; rl h) = 7-k сдвигов влево.
    ('arkos_src.asm', 959): ['ld (ply_sd_cnt),a'],
    ('arkos_src.asm', 963): ['ld (z_a),a', 'ld a,(ply_sd_cnt)', 'rrca', 'rrca', 'cpl', 'and 7', 'inc a',
                             'ld (ply_sd_loop),a',
                             'ply_sd_l:', 'ld a,h', 'or a', 'rra', 'ld h,a', 'ld a,l', 'rra', 'ld l,a',
                             'ld a,(ply_sd_loop)', 'dec a', 'ld (ply_sd_loop),a', 'jp nz,ply_sd_l',
                             'ld a,(z_a)', 'jp nc,ply_sd_noinc', 'inc hl', 'ply_sd_noinc:'],
    **{('arkos_src.asm', n): [] for n in range(964, 980)},
    ('arkos_src.asm', 1030): ['ld (ply_hd_cnt),a'],
    ('arkos_src.asm', 1035): ['ld (z_a),a', 'ld a,(ply_hd_cnt)', 'rrca', 'rrca', 'cpl', 'and 7',
                              'ld (ply_sd_loop),a', 'or a', 'jp z,ply_hd_done',
                              'ply_hd_l:', 'add hl,hl',
                              'ld a,(ply_sd_loop)', 'dec a', 'ld (ply_sd_loop),a', 'jp nz,ply_hd_l',
                              'ply_hd_done:', 'ld a,(z_a)'],
    **{('arkos_src.asm', n): [] for n in range(1036, 1050)},
}
