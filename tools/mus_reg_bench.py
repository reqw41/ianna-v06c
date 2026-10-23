#!/usr/bin/env python3
"""A/B: Arkos vs тишина vs поток регистров AY на тяжёлых сценах.

На входе в atPlay в режимах silence/psg тело плеера не исполняется:
  silence — сразу ret (потолок)
  psg     — один кадр psgpack-потока пишется в AY, начисляются такты
            откалиброванного psg_tick (реальный i8080-разбор маски)

  python3 tools/mus_reg_bench.py [/tmp/ianna_gates_mus] [--ticks=30]
"""
from __future__ import annotations
import sys, os, re, bisect, pathlib, collections, tempfile, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, os.environ.get('PSGPACK_DIR', str(ROOT / 'tools/vendor')))   # psgpack.py (упаковщик потока AY) — внешний, не входит в репозиторий
import arkos_model as am
from psgpack import pack

GATEDIR = pathlib.Path(next((a for a in sys.argv[1:] if not a.startswith('--')), '/tmp/ianna_gates_mus'))
TICKS = int(next((a[8:] for a in sys.argv if a.startswith('--ticks=')), '30'))
# сцены через ';': L:X,Y;L:X,Y
SCENES = next((a[9:] for a in sys.argv if a.startswith('--scenes=')),
              '1:4,5;2:4,6;3:1,0;3:1,2;4:6,2;6:6,1')
LEVEL_MUSIC = [1, 5, 3, 4, 5, 6, 7, 8, 8]
FRAME = 59904

# ---- калибровка psg_tick: собрать, прогнать N кадров потока, снять среднее ----
PSG_ASM = """\
	org $100
psg_tick:
	ld a,(psg_hold)
	or a
	jp z,psg_frame
	dec a
	ld (psg_hold),a
	ret
psg_frame:
	ld hl,(psg_ptr)
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld a,d
	inc a
	jp nz,psg_notend
	ld a,e
	inc a
	jp z,psg_loop
psg_notend:
	ld a,d
	or e
	jp nz,psg_write
	ld a,(hl)
	inc hl
	dec a
	ld (psg_hold),a
	ld (psg_ptr),hl
	ret
psg_write:
	ld b,14
	ld c,0
psg_bit:
	and a
	ld a,d
	rra
	ld d,a
	ld a,e
	rra
	ld e,a
	jp nc,psg_skip
	ld a,(hl)
	inc hl
	push bc
	push de
	ld e,a
	ld a,c
	out ($15),a
	ld a,e
	out ($14),a
	pop de
	pop bc
psg_skip:
	inc c
	dec b
	jp nz,psg_bit
	ld (psg_ptr),hl
	ret
psg_loop:
	ld hl,(psg_base)
	ld (psg_ptr),hl
	xor a
	ld (psg_hold),a
	jp psg_frame
psg_ptr:	dw stream
psg_base:	dw stream
psg_hold:	db 0
stream:
"""


def song_loop_pack(level_no):
    name = f'music-level{LEVEL_MUSIC[level_no - 1]}.mus'
    p = am.make_player(name)
    frames, prev, loop_at = [], [0] * 14, []
    for _ in range(30000):
        before = p.stat.get('линкер: зацикливание песни', 0)
        writes = p.at_play()
        after = p.stat.get('линкер: зацикливание песни', 0)
        fr = prev[:]
        w13 = False
        for r, v in writes:
            if r == 13:
                fr[13] = v; w13 = True
            elif r < 13:
                fr[r] = v
        out = [fr[r] for r in range(13)] + ([fr[13]] if w13 else [0xFF])
        for r in range(13):
            prev[r] = fr[r]
        if w13:
            prev[13] = fr[13]
        frames.append(out)
        if after > before:
            loop_at.append(len(frames) - 1)
            if len(loop_at) == 2:
                break
    a, b = loop_at[0], loop_at[1]
    blob, st = pack(frames[a:b], retune=False)
    return name, blob, st, b - a


def calibrate_psg(blob, nframes=400):
    """Оценка тактов psg_tick по маске потока (без отдельной сборки — быстро и стабильно).

    Модель по замерам Tony juke_psg + разбору маски: hold ≈ 45 т; кадр с K записями
    ≈ 180 + K×95 (out пары $15/$14 + обход бит)."""
    return _calibrate_heuristic(blob, nframes)

def _calibrate_heuristic(blob, nframes):
    i = 0; costs = []; frames = 0
    while frames < nframes and i + 2 <= len(blob):
        mask = blob[i] | (blob[i + 1] << 8); i += 2
        if mask == 0xFFFF:
            i = 0; continue
        if mask == 0:
            n = blob[i]; i += 1
            take = min(n, nframes - frames)
            costs.extend([45] * take)
            frames += take
            continue
        k = bin(mask).count('1')
        i += k
        costs.append(180 + k * 95)
        frames += 1
    return {'avg': sum(costs) / max(1, len(costs)), 'max': max(costs or [0]),
            'min': min(costs or [0]), 'n': len(costs)}

class PsgStream:
    """Курсор по psgpack; tick() пишет AY и возвращает оценку тактов psg_tick."""
    def __init__(self, blob):
        self.blob = blob
        self.i = 0
        self.hold = 0
        self.base = 0
        self.writes = 0

    def tick(self, out_ay):
        if self.hold:
            self.hold -= 1
            return 45
        if self.i + 2 > len(self.blob):
            self.i = self.base
        mask = self.blob[self.i] | (self.blob[self.i + 1] << 8)
        self.i += 2
        if mask == 0xFFFF:
            self.i = self.base
            return self.tick(out_ay)
        if mask == 0:
            n = self.blob[self.i]; self.i += 1
            self.hold = max(0, n - 1)
            return 45
        k = 0
        for r in range(14):
            if mask >> r & 1:
                v = self.blob[self.i]; self.i += 1
                out_ay(r, v); k += 1; self.writes += 1
        return 180 + k * 95


def run_scene(rom, lst, edd, xy, n, mode, stream: PsgStream | None, CYC):
    os.environ['IANNA_EDD'] = str(edd)
    import run_vec as rv
    rv.STEP_BUDGET = 400000
    sym = rv.load_syms(pathlib.Path(lst))
    keys = []; cpu = rv.make_cpu(keys)
    rom_b = pathlib.Path(rom).read_bytes()
    cpu.mem[0x100:0x100 + len(rom_b)] = rom_b
    cpu.pc = 0x100
    rv.patch_menu(cpu)
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))

    # MUSIC_Play = `jp atPlay`; ISR делает `call MUSIC_Play`. Хукаем точку CALL.
    music_play = sym['MUSIC_Play']
    at_play = sym['atPlay']
    ay_writes = [0]

    def out_ay(reg, val):
        cpu.out_handler(0x15, reg)
        cpu.out_handler(0x14, val)
        ay_writes[0] += 1

    rv.START = tuple(int(v) for v in xy.split(','))
    rv.start_game(cpu, keys, sym)
    if mode == 'silence':
        cpu.mem[music_play] = 0xC9  # ret — после прогрева
    keys.append('right')
    RS = sym['RunScripts']; FC = sym['FrameCounter']
    ticks = 0; tot = 0; mus = 0; mem = cpu.mem; step = cpu.step
    hooks = 0; irqs = 0

    # Стиль abcyc: считаем такты исполнения; halt = граница кадра (IRQ).
    # Это CPU-работа тика (без дотягивания halt до FRAME) — честно для сравнения
    # статей «музыка», а тик/с ниже — оценка 50/(т/тик/FRAME), завышенная без idle.
    while ticks < n:
        steps = 0
        while not cpu.halted and steps < 600000:
            pc = cpu.pc
            if mode == 'psg' and pc == music_play:
                ret_lo = mem[cpu.sp]; ret_hi = mem[cpu.sp + 1]
                cpu.sp = (cpu.sp + 2) & 0xFFFF
                cost = stream.tick(out_ay)
                tot += cost; mus += cost; hooks += 1
                cpu.pc = ret_lo | (ret_hi << 8)
                steps += 1
                continue
            w = CYC[mem[pc]]; tot += w
            if mode == 'arkos' and (at_play <= pc < at_play + 0xA00 or pc == music_play):
                mus += w
            if mode == 'silence' and pc == music_play:
                mus += w; hooks += 1
            if pc == RS:
                ticks += 1; mem[FC] = ticks & 0xFF
            step(); steps += 1
        if steps >= 600000:
            raise RuntimeError(f'hang ticks={ticks} pc={cpu.pc:04X} mode={mode}')
        cpu.halted = False
        if cpu.ie:
            cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38; irqs += 1
    fpt = tot / n / FRAME  # нижняя оценка кадров/тик по CPU-работе
    return {
        'tot': tot, 'per_tick': tot / n, 'mus': mus, 'hooks': hooks,
        'irqs': irqs, 'fpt': fpt, 'tps': 50 / max(fpt, 0.01),
        'ay_writes': ay_writes[0],
        'mus_per_tick': mus / n,
    }


def main():
    src = open(ROOT / 'tools/profile_vec.py').read()
    i = src.index('# Такты ВЕКТОРА'); j = src.index('keys = []')
    g = {}; exec(src[i:j], g); CYC = g['CYC']

    scenes = [(int(a), f'{b},{c}') for a, b, c in re.findall(r'(\d+):(\d+),(\d+)', SCENES)]
    print(f'сцены ({TICKS} тиков, вправо): {scenes}')

    packs = {}
    for lv, _ in scenes:
        if lv in packs:
            continue
        name, blob, st, nf = song_loop_pack(lv)
        cal = calibrate_psg(blob)
        packs[lv] = (name, blob, st, nf, cal)
        print(f'  ур.{lv} {name}: петля {nf}ф/{nf/50:.0f}с, psgpack {st["bytes"]} Б, '
              f'psg_tick ~{cal["avg"]:.0f} т/кадр (min {cal["min"]:.0f} max {cal["max"]:.0f})',
              flush=True)

    print(f'\n{"сцена":8} {"режим":8} {"CPU т/тик":>10} {"муз т/тик":>10} {"IRQs":>5}',
          flush=True)
    print('(тик/с здесь не вывод — только CPU-работа без idle halt; смотри Δ музыки)', flush=True)
    rows = []
    for lv, xy in scenes:
        rom, lst, edd = GATEDIR / f'l{lv}.rom', GATEDIR / f'l{lv}.lst', GATEDIR / f'l{lv}.edd'
        if not rom.exists():
            print(f'  нет {rom}'); continue
        name, blob, st, nf, cal = packs[lv]
        for mode in ('arkos', 'silence', 'psg'):
            print(f'  … {lv}:{xy} {mode}', flush=True)
            stream = PsgStream(blob) if mode == 'psg' else None
            r = run_scene(rom, lst, edd, xy, TICKS, mode, stream, CYC)
            print(f'{lv}:{xy:5} {mode:8} {r["per_tick"]:10.0f} {r["mus_per_tick"]:10.0f} {r["irqs"]:5d}',
                  flush=True)
            rows.append((lv, xy, mode, r))

    print('\nΔ музыка т/тик к arkos (главный замер):')
    by = collections.defaultdict(dict)
    for lv, xy, mode, r in rows:
        by[(lv, xy)][mode] = r
    for k, m in sorted(by.items()):
        a = m['arkos']
        for mode in ('silence', 'psg'):
            if mode not in m:
                continue
            d = a['mus_per_tick'] - m[mode]['mus_per_tick']
            dcpu = a['per_tick'] - m[mode]['per_tick']
            print(f'  {k[0]}:{k[1]:5} {mode:8}  музыка {a["mus_per_tick"]:.0f} → {m[mode]["mus_per_tick"]:.0f}  '
                  f'({d:+.0f} т/тик)  CPU тика {dcpu:+.0f}')


if __name__ == '__main__':
    main()
