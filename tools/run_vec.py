#!/usr/bin/env python3
"""Headless-прогон ianna.rom (Вектор-06Ц) на emu_kvaz (i8080 + квазидиск) с рендером PNG.

  run_vec.py <кадров> [маршрут] [out.png]
  маршрут: "none" | "left" | "right:100,none:20,left:50" (клавиши: up/down/left/right/fire/action)
Печатает состояние игрока (entity/sprite), PC и такты.
"""
import sys, re, pathlib
sys.path.insert(0, str(pathlib.Path.home() / 'projects/metalgear-v06c/tools'))
sys.path.insert(0, str(pathlib.Path.home() / 'projects/knightmare-v06c/tools'))
from emu_kvaz import I8080Kvaz as I8080

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEY_ROW0 = {'down': 0x80, 'right': 0x40, 'up': 0x20, 'left': 0x10}
KEY_ROW7 = {'fire': 0x80, 'z': 0x04, 'action': 0x01}

def load_syms(lst):
    sym = {}
    for line in pathlib.Path(lst).read_text(errors='replace').splitlines():
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_.]*)\s+=\s+\$([0-9A-Fa-f]{4})', line)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
    return sym

def render(vram, pal, path, scale=2):
    import zlib, struct
    W = H = 256
    def rgb(b):
        return ((b & 7) * 255 // 7, ((b >> 3) & 7) * 255 // 7, ((b >> 6) & 3) * 255 // 3)
    colors = [rgb(p) for p in pal]
    raw = bytearray()
    rows = []
    for y in range(H):
        line = (255 - y) & 0xFF
        row = []
        for x in range(W):
            off = (x >> 3) * 256 + line
            bit = 0x80 >> (x & 7)
            idx = 0
            for p in range(4):
                if vram[p * 0x2000 + off] & bit:
                    idx |= 8 >> p
            row.append(colors[idx])
        rows.append(row)
    for y in range(H * scale):
        raw.append(0)
        for x in range(W * scale):
            raw += bytes(rows[y // scale][x // scale])
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W*scale, H*scale, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b''))
    pathlib.Path(path).write_bytes(png)

def make_cpu(keys):
    cpu = I8080()
    cpu.load_edd(ROOT / 'build/ianna.edd')
    rom = (ROOT / 'build/ianna.rom').read_bytes()
    cpu.mem[0x100:0x100+len(rom)] = rom
    cpu.pc = 0x100
    cur = [0xFF]
    def out_handler(port, val):
        if port == 0x03: cur[0] = val
        elif port == 0x10: cpu.kv_out(port, val)
    def in_handler(port):
        if port == 0x02:
            v = 0xFF
            if cur[0] == 0xFE:
                for k in keys:
                    if k in KEY_ROW0: v &= ~KEY_ROW0[k] & 0xFF
            if cur[0] == 0x7F:
                for k in keys:
                    if k in KEY_ROW7: v &= ~KEY_ROW7[k] & 0xFF
            return v
        return 0xFF
    cpu.out_handler = out_handler
    cpu.in_handler = in_handler
    return cpu

def dump_state(cpu, sym):
    ent = sym.get('ENTITY_DATA'); spd = sym.get('SPDATA')
    if ent is None: return
    e = cpu.mem[ent:ent+12]
    print('  player entity: spr=%04x script=%d pos=%d energy=%d state=%d anim=%d' % (e[0] | (e[1] << 8), e[2], e[3], e[4], e[5], e[6]))
    if spd:
        s = cpu.mem[spd:spd+8]
        print('  sprite0: addr=%04x type=%02x x=%d y=%d nx=%d ny=%d redraw=%d' % (s[0] | (s[1] << 8), s[2], s[3], s[4], s[5], s[6], s[7]))
    for name in ('joystick_state', 'frames_noredraw', 'ndirtyrects', 'current_levelx', 'current_levely', 'player_dead'):
        if name in sym: print('  %s=%d' % (name, cpu.mem[sym[name]]), end='')
    print()

def main():
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    route = sys.argv[2] if len(sys.argv) > 2 else 'none'
    out = sys.argv[3] if len(sys.argv) > 3 else str(ROOT / 'build/frame.png')
    sym = load_syms(ROOT / 'build/ianna_vec.lst')
    keys = set()
    cpu = make_cpu(keys)
    segs = [(k, int(n)) for k, n in (s.split(':') for s in route.split(','))] if ':' in route else [(route, frames)]
    total = 0
    try:
        for k, n in segs:
            keys.clear(); keys.update(x for x in k.split('+') if x != 'none')
            cpu.run_frames(n, max_per=6_000_000)
            total += n
            if cpu.halted is False and cpu.icount and False: pass
    except Exception as ex:
        print('ОШИБКА эмуляции:', ex)
    print(f'кадров: {total}, инструкций: {cpu.icount}, halted={cpu.halted}, pc={cpu.pc:#06x} sp={cpu.sp:#06x}')
    # где стоим: ближайшая метка
    near = max((a, n) for n, a in sym.items() if a <= cpu.pc) if sym else None
    if near: print(f'  pc около {near[1]}+{cpu.pc-near[0]}')
    dump_state(cpu, sym)
    pal = list(cpu.mem[sym['vec_palette']:sym['vec_palette']+16]) if 'vec_palette' in sym else [0]*16
    render(bytes(cpu.mem[0x8000:0x10000]), pal, out)
    print('PNG:', out)

if __name__ == '__main__':
    main()
