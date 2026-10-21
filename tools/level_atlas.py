#!/usr/bin/env python3
"""Лабиринт уровней: PNG каждого экрана (враги на спавне; герой только на старте) + тик/с.

  python3 tools/level_atlas.py [--levels=1-9] [--out=build/atlas] [--frames=120]
                                [--snap=/tmp/ianna_gates_mus] [--rebuild]
                                [--resnap] [--html-only]

Для каждого уровня нужен ROM+EDD+lst (из --snap или сборки build_edd+build_vec).
HTML: build/atlas/index.html и levelN.html — карта по переходам.
На бейдже скорости два числа: стоя / ходьба вправо (пока экран не сменился).
"""
import sys, os, re, json, base64, subprocess, pathlib, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(next((o[6:] for o in OPTS if o.startswith('--out=')), str(ROOT / 'build/atlas')))
SNAP = pathlib.Path(next((o[7:] for o in OPTS if o.startswith('--snap=')), '/tmp/ianna_gates_mus'))
FRAMES = int(next((o[9:] for o in OPTS if o.startswith('--frames=')), '100'))
JOBS = int(next((o[7:] for o in OPTS if o.startswith('--jobs=')), '4'))
REBUILD = '--rebuild' in OPTS
LEVELS_OPT = next((o[9:] for o in OPTS if o.startswith('--levels=')), '1-9')

def parse_levels(s):
    out = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-', 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out

LEVELS = parse_levels(LEVELS_OPT)
FRAME_CYC = 59904.0

sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/data'))
import run_vec as rv
from level_tools import parse_level

SRC = ROOT / 'ref/msx2/src'


def ensure_level(lv):
    """ROM/LST/EDD для уровня: из snap или сборка в OUT/snap."""
    for base in (SNAP, OUT / 'snap', ROOT / 'build'):
        rom = base / (f'l{lv}.rom' if base != ROOT / 'build' else 'ianna.rom')
        lst = base / (f'l{lv}.lst' if base != ROOT / 'build' else 'ianna_vec.lst')
        edd = base / (f'l{lv}.edd' if base != ROOT / 'build' else 'ianna.edd')
        if base == ROOT / 'build':
            # только если только что собрали под этот уровень
            continue
        if rom.exists() and lst.exists() and edd.exists() and not REBUILD:
            return rom, lst, edd
    snap_dir = OUT / 'snap'
    snap_dir.mkdir(parents=True, exist_ok=True)
    rom, lst, edd = snap_dir / f'l{lv}.rom', snap_dir / f'l{lv}.lst', snap_dir / f'l{lv}.edd'
    if rom.exists() and lst.exists() and edd.exists() and not REBUILD:
        return rom, lst, edd
    print(f'  сборка уровня {lv}…', flush=True)
    subprocess.check_call([sys.executable, str(ROOT / 'tools/data/build_edd.py'), f'--level={lv}'],
                          cwd=ROOT, stdout=subprocess.DEVNULL)
    subprocess.check_call([sys.executable, str(ROOT / 'tools/build_vec.py')],
                          cwd=ROOT, stdout=subprocess.DEVNULL)
    rom.write_bytes((ROOT / 'build/ianna.rom').read_bytes())
    lst.write_bytes((ROOT / 'build/ianna_vec.lst').read_bytes())
    edd.write_bytes((ROOT / 'build/ianna.edd').read_bytes())
    return rom, lst, edd


# На Векторе кадр MSX y=0 лежит на строке framebuffer +32 (vec_vdp.asm).
# Поле 0..159 → framebuffer y=32..191 (без панели/HUD).
ATLAS_Y0 = 32
ATLAS_H = 160
# cache-bust превью (меняли кроп/героя)
ATLAS_IMG_V = 'nh2'


def render_field(vram, pal, path, scale=1):
    """Только игровое поле (MSX y=0..159) со сдвигом Вектора +32."""
    import zlib, struct
    W, H = 256, ATLAS_H
    def rgb(b):
        return ((b & 7) * 255 // 7, ((b >> 3) & 7) * 255 // 7, ((b >> 6) & 3) * 255 // 3)
    colors = [rgb(p) for p in pal]
    rows = []
    for y in range(H):
        line = (255 - (y + ATLAS_Y0)) & 0xFF
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
    raw = bytearray()
    for y in range(H * scale):
        raw.append(0)
        for x in range(W * scale):
            raw += bytes(rows[y // scale][x // scale])
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W * scale, H * scale, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b''))
    pathlib.Path(path).write_bytes(png)


def _vram_rgb_field(vram, pal):
    """RGB игрового поля (ATLAS_H×256), как в render_field."""
    def rgb(b):
        return ((b & 7) * 255 // 7, ((b >> 3) & 7) * 255 // 7, ((b >> 6) & 3) * 255 // 3)
    colors = [rgb(p) for p in pal]
    rows = []
    for y in range(ATLAS_H):
        line = (255 - (y + ATLAS_Y0)) & 0xFF
        row = []
        for x in range(256):
            off = (x >> 3) * 256 + line
            bit = 0x80 >> (x & 7)
            idx = 0
            for p in range(4):
                if vram[p * 0x2000 + off] & bit:
                    idx |= 8 >> p
            row.append(colors[idx])
        rows.append(row)
    return rows


def _erase_hero_rgb(fg_rows, bg_rows, sp):
    """Убрать героя: в его прямоугольнике вернуть пиксели фона после LoadScreen."""
    x, y = sp[3], sp[4]
    nw, nh = max(sp[5], 3) * 8, max(sp[6], 4) * 8
    out = [list(r) for r in fg_rows]
    for dy in range(nh):
        my = y + dy
        if my < 0 or my >= ATLAS_H:
            continue
        for dx in range(nw):
            mx = x + dx
            if 0 <= mx < 256:
                out[my][mx] = bg_rows[my][mx]
    return out


def _write_rgb_png(rows, path, scale=1):
    import zlib, struct
    H = len(rows)
    W = len(rows[0])
    raw = bytearray()
    for y in range(H * scale):
        raw.append(0)
        for x in range(W * scale):
            raw += bytes(rows[y // scale][x // scale])
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W * scale, H * scale, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b''))
    pathlib.Path(path).write_bytes(png)


def _emu_step_hooks(cpu, sym, bg_box, ls_ret):
    """SaveCheckpoint + снимок VRAM после каждого LoadScreen (нужен последний — целевой экран)."""
    pc = cpu.pc
    if pc == sym['LoadScreen']:
        ls_ret[0] = cpu.mem[cpu.sp] | (cpu.mem[cpu.sp + 1] << 8)
    elif ls_ret[0] is not None and pc == ls_ret[0]:
        bg_box[0] = bytes(cpu.mem[0x8000:0x10000])
        ls_ret[0] = None
    if rv.START and not rv._start_done[0] and pc == sym['SaveCheckpoint']:
        cpu.mem[sym['current_levelx']] = rv.START[0]
        cpu.mem[sym['current_levely']] = rv.START[1]
        rv._start_done[0] = True


def _run_frames_snap_bg(cpu, n, sym, bg_box, ls_ret):
    budget = rv.STEP_BUDGET
    for _ in range(n):
        c = 0
        while not cpu.halted and c < budget:
            _emu_step_hooks(cpu, sym, bg_box, ls_ret)
            cpu.step()
            c += 1
        cpu.halted = False
        if cpu.ie:
            cpu.ie = False
            cpu.push(cpu.pc)
            cpu.pc = 0x38


def _start_game_snap_bg(cpu, keys, sym, bg_box, ls_ret, max_frames=1500):
    w = rv.Warmup(sym, keys)
    done = False
    for fr in range(max_frames):
        c = 0
        while not cpu.halted and c < rv.STEP_BUDGET:
            _emu_step_hooks(cpu, sym, bg_box, ls_ret)
            if w.step(cpu.pc, fr):
                done = True
            cpu.step()
            c += 1
        cpu.halted = False
        if cpu.ie:
            cpu.ie = False
            cpu.push(cpu.pc)
            cpu.pc = 0x38
        if done:
            break
    keys.clear()
    _run_frames_snap_bg(cpu, 10, sym, bg_box, ls_ret)
    assert done, 'игра не стартовала'


def _tps_pair(cell_or_json):
    """Из ячейки/JSON → (tps_stand, tps_walk). Старый формат — одно число = только стоя."""
    if cell_or_json is None:
        return None, None
    if isinstance(cell_or_json, (int, float)):
        return float(cell_or_json), None
    if isinstance(cell_or_json, dict):
        if 'stand' in cell_or_json or 'walk' in cell_or_json:
            st = cell_or_json.get('stand')
            wk = cell_or_json.get('walk')
            return (float(st) if st is not None else None,
                    float(wk) if wk is not None else None)
        # ячейка атласа
        st = cell_or_json.get('tps_stand', cell_or_json.get('tps'))
        wk = cell_or_json.get('tps_walk')
        return (float(st) if st is not None else None,
                float(wk) if wk is not None else None)
    return None, None


def _tps_worst(stand, walk):
    vals = [t for t in (stand, walk) if t is not None]
    return min(vals) if vals else None


def _format_spd(stand, walk):
    def fmt(t):
        return f'{t:.1f}' if t is not None else '—'
    return f'{fmt(stand)}/{fmt(walk)}'


def _measure_tps(cpu, sym, CYC, FRAME, nframes, keys_hold, stop_on_load=False):
    """Считает тик/с по входам в RunScripts за nframes. keys_hold — клавиши на время замера.
    stop_on_load: оборвать при LoadScreen (ходьба не уезжает на соседний экран в статистику)."""
    mem = cpu.mem
    RS = sym['RunScripts']
    LS = sym['LoadScreen']
    keys = cpu.keys if hasattr(cpu, 'keys') else None
    # run_vec держит keys как list, переданный в make_cpu
    cyc = [0]
    next_irq = FRAME
    tick_frames = []
    tstart = 0
    end = nframes * FRAME
    seen_load = False
    while cyc[0] < end:
        if cpu.halted:
            cyc[0] = next_irq
        else:
            pc = cpu.pc
            if stop_on_load and pc == LS:
                seen_load = True
            if pc == RS:
                if seen_load:
                    break
                tick_frames.append((cyc[0] - tstart) / FRAME)
                tstart = cyc[0]
            cyc[0] += CYC[mem[pc]]
            cpu.step()
        if cyc[0] >= next_irq:
            next_irq += FRAME
            if cpu.ie:
                cpu.ie = False
                cpu.halted = False
                cpu.push(cpu.pc)
                cpu.pc = 0x38
    norm = tick_frames[1:]
    if len(norm) < 5:
        return None, None
    avg = sum(norm) / len(norm)
    tps = 50.0 / max(avg, 0.01)
    return round(avg, 2), round(min(10.0, tps), 1)


def capture_screen(rom, lst, edd, xy, png_path, measure_frames, hide_hero=False):
    """Старт на экране xy: PNG после прогрева + тик/с стоя и в ходьбе вправо.
    measure_frames=0 — только PNG.
    hide_hero=True — герой вырезается с PNG: прямоугольник спрайта ← фон после LoadScreen.
    Возвращает (frames_stand, tps_stand, frames_walk, tps_walk)."""
    os.environ['IANNA_EDD'] = str(edd)
    rv.START = xy
    rv._start_done[0] = False
    rv.STEP_BUDGET = 400000
    sym = rv.load_syms(pathlib.Path(lst))
    keys = []
    cpu = rv.make_cpu(keys)
    data = pathlib.Path(rom).read_bytes()
    cpu.mem[0x100:0x100 + len(data)] = data
    cpu.pc = 0x100
    rv.patch_menu(cpu)
    a = sym['random']; rd = sym['randData']
    cpu.mem[a:a + 9] = bytes((0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9))
    bg_box = [None]
    ls_ret = [None]
    _start_game_snap_bg(cpu, keys, sym, bg_box, ls_ret)
    keys.clear()
    _run_frames_snap_bg(cpu, 30, sym, bg_box, ls_ret)
    pal = list(cpu.mem[sym['vec_palette']:sym['vec_palette'] + 16])
    vram = bytes(cpu.mem[0x8000:0x10000])
    if hide_hero and bg_box[0] is not None:
        sp = bytes(cpu.mem[sym['SPDATA']:sym['SPDATA'] + 8])
        fg = _vram_rgb_field(vram, pal)
        bg = _vram_rgb_field(bg_box[0], pal)
        _write_rgb_png(_erase_hero_rgb(fg, bg, sp), png_path, scale=1)
    else:
        render_field(vram, pal, png_path, scale=1)

    if measure_frames <= 0:
        return None, None, None, None

    src = open(ROOT / 'tools/profile_vec.py').read()
    ns = {}
    exec(src[src.index('# Такты ВЕКТОРА'):src.index('keys = []')], ns)
    CYC = ns['CYC']
    FRAME = 59904

    keys.clear()
    fr_s, tps_s = _measure_tps(cpu, sym, CYC, FRAME, measure_frames, keys_hold=None, stop_on_load=False)
    keys.clear()
    keys.append('right')
    fr_w, tps_w = _measure_tps(cpu, sym, CYC, FRAME, measure_frames, keys_hold=None, stop_on_load=True)
    keys.clear()
    return fr_s, tps_s, fr_w, tps_w


def html_escape(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


OBJECT_TELEPORTER = 9
MSX_STRING_AREA = 0xC000
DIR_DELTA = {'L': (-1, 0), 'R': (1, 0), 'U': (0, -1), 'D': (0, 1)}
DIR_REV = {'L': 'R', 'R': 'L', 'U': 'D', 'D': 'U'}
# длины параметров действий скрипта (scripts.asm)
_ACTION_LEN = {
    0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 1, 7: 1, 8: 2, 9: 1, 10: 1, 11: 1, 12: 1,
    13: 1, 14: 1, 15: 1, 16: 0, 17: 0, 18: 4, 19: 0, 20: 1, 21: 1, 22: 0, 23: 0, 24: 0,
    25: 5, 26: 1, 27: 0, 28: 0, 29: 1, 30: 1, 31: 1, 32: 1, 33: 1, 34: 1, 35: 0, 36: 1,
    37: 1, 38: 0, 39: 3, 40: 3, 41: 2, 42: 2, 43: 0, 44: 4, 45: 4, 46: 2, 47: 4, 48: 0,
    49: 1,
}


def _rd16(b, o):
    return b[o] | (b[o + 1] << 8)


def _hardness(screen):
    """Карта твёрдости 16×10, значение 0..3 (0 ≈ проходимо/пусто)."""
    raw = screen[320:360]
    H = [[0] * 16 for _ in range(10)]
    for y in range(10):
        for x in range(16):
            byte = raw[y * 4 + (x >> 2)]
            H[y][x] = (byte >> (2 * (x & 3))) & 3
    return H


def _script_first_teleport(block, sc_tab, sid):
    """Первый ACTION_TELEPORT/EXT в скрипте (после WAIT_CONTACT и т.п.)."""
    if sid < 0:
        return None
    a = _rd16(block, sc_tab + 2 * sid) - MSX_STRING_AREA
    if a < 0 or a >= len(block):
        return None
    i = 0
    for _ in range(20):
        if a + i >= len(block):
            return None
        op = block[a + i]
        if op == 0xFF:
            return None
        ln = _ACTION_LEN.get(op)
        if ln is None:
            return None
        if op in (18, 45) and a + i + 4 < len(block):
            return block[a + i + 1], block[a + i + 2], block[a + i + 3], block[a + i + 4]
        i += 1 + ln
    return None


def _exit_dir(sx, sy):
    scores = {'R': sx, 'L': 15 - sx, 'D': sy, 'U': 9 - sy}
    return max(scores, key=scores.get)


def _entry_dir(px, py):
    if px <= 48:
        return 'L'
    if px >= 200:
        return 'R'
    if py <= 40:
        return 'U'
    if py >= 120:
        return 'D'
    return None


def _edge_open(H, side):
    """Проход через край: два соседних нуля на границе (коридор), не «небо» сверху."""
    if side == 'R':
        return any(H[y][15] == 0 and H[y][14] == 0 for y in range(2, 10))
    if side == 'L':
        return any(H[y][0] == 0 and H[y][1] == 0 for y in range(2, 10))
    if side == 'D':
        return any(H[9][x] == 0 and H[8][x] == 0 for x in range(16))
    if side == 'U':
        return any(H[0][x] == 0 and H[1][x] == 0 for x in range(16))
    return False


def level_transitions(level_no, w, h):
    """Все реальные переходы: (src, dest, dir, kind).
    kind: 'warp' | 'edge'. dir — куда идёшь из src (L/R/U/D).
    Если с экрана в сторону уже есть телепорт — краевой выход туда же не дублируем."""
    from build_edd import screens_of
    raw = (SRC / f'level{level_no}.map').read_bytes()
    info = parse_level(raw)
    block = info['strings']['es']
    sc_tab = _rd16(block, 2) - MSX_STRING_AREA
    scr = screens_of(list(raw))
    edges = []
    seen = set()
    warp_dirs = collections.defaultdict(set)  # src -> set(dir)

    def add(a, b, d, kind):
        key = (a, b, d, kind)
        if key in seen or a == b:
            return
        if not (0 <= b[0] < w and 0 <= b[1] < h):
            return
        seen.add(key)
        edges.append((a, b, d, kind))

    for y in range(h):
        for x in range(w):
            s = scr[y * w + x]
            o = s[360:403]
            for off in (13, 19, 25, 31, 37):
                typ, sx, sy, sid = o[off + 1], o[off + 2], o[off + 3], o[off + 5]
                if typ != OBJECT_TELEPORTER:
                    continue
                tp = _script_first_teleport(block, sc_tab, sid)
                if not tp:
                    continue
                tx, ty, px, py = tp
                d = _exit_dir(sx, sy)
                add((x, y), (tx, ty), d, 'warp')
                warp_dirs[(x, y)].add(d)

    for y in range(h):
        for x in range(w):
            H = _hardness(scr[y * w + x])
            for d, nx, ny in (('L', x - 1, y), ('R', x + 1, y), ('U', x, y - 1), ('D', x, y + 1)):
                if d in warp_dirs[(x, y)]:
                    continue  # телепорт занимает эту сторону
                if 0 <= nx < w and 0 <= ny < h and _edge_open(H, d):
                    add((x, y), (nx, ny), d, 'edge')
    return edges


def layout_rooms(level_no, w, h, start):
    """Координаты карты: Kruskal-остов (сначала все телепорты, потом края).

    Рёбра остова → pos[dest]=pos[src]+delta. Индекс (x,y) на карту не копируется.
    Переходы вне остова рисуются линиями (могут быть длинными при конфликте сторон)."""
    trans = level_transitions(level_no, w, h)
    warps = [(a, b, d) for a, b, d, k in trans if k == 'warp']
    rooms = [(x, y) for y in range(h) for x in range(w)]
    start = tuple(start)

    uf = {n: n for n in rooms}

    def find(x):
        while uf[x] != x:
            uf[x] = uf[uf[x]]
            x = uf[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        uf[rb] = ra
        return True

    tree_out = collections.defaultdict(list)

    def dir_taken(node, d):
        return any(dd == d for _, dd in tree_out[node])

    def add_tree(a, b, d):
        """Одна сторона экрана — не больше одного соседа (иначе геометрический конфликт)."""
        rd = DIR_REV[d]
        if dir_taken(a, d) or dir_taken(b, rd):
            return False
        if not union(a, b):
            return False
        tree_out[a].append((b, d))
        tree_out[b].append((a, rd))
        return True

    # 1) телепорты — максимальный приоритет
    for a, b, d in warps:
        add_tree(a, b, d)
    # 2) края
    for a, b, d, k in trans:
        if k == 'edge':
            add_tree(a, b, d)

    pos = {}
    occupied = {}

    def place_at(node, xy):
        if node in pos:
            return
        if xy not in occupied:
            pos[node] = xy
            occupied[xy] = node
            return
        ox, oy = xy
        for r in range(1, w + h + 8):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) + abs(dy) != r:
                        continue
                    c = (ox + dx, oy + dy)
                    if c not in occupied:
                        pos[node] = c
                        occupied[c] = node
                        return

    def embed(seed, origin):
        q = collections.deque()
        place_at(seed, origin)
        q.append(seed)
        while q:
            cur = q.popleft()
            cx, cy = pos[cur]
            for dest, d in tree_out.get(cur, []):
                if dest in pos:
                    continue
                dx, dy = DIR_DELTA[d]
                place_at(dest, (cx + dx, cy + dy))
                q.append(dest)

    embed(start, (0, 0))
    for n in rooms:
        if n not in pos:
            ox = max((p[0] for p in pos.values()), default=-2) + 3
            embed(n, (ox, 0))

    def satisfied(pairs):
        ok = tot = 0
        for a, b, d in pairs:
            tot += 1
            if a in pos and b in pos:
                dx, dy = DIR_DELTA[d]
                if (pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]) == (dx, dy):
                    ok += 1
        return ok, tot

    wok, wtot = satisfied(warps)
    e_pairs = [(a, b, d) for a, b, d, k in trans if k == 'edge']
    eok, etot = satisfied(e_pairs)

    minx = min(p[0] for p in pos.values())
    miny = min(p[1] for p in pos.values())
    laid = {n: (p[0] - minx, p[1] - miny) for n, p in pos.items()}
    return laid, warps, trans, (wok, wtot, eok, etot)


# Цвета рамок зон на карте (A, B, C, …)
ZONE_COLORS = [
    '#e75', '#5ae', '#5c6', '#c6e', '#ec5', '#6cd', '#e69', '#8d6',
    '#d85', '#79e', '#ad5', '#e9a',
]


def level_zones(level_no, w, h, start, cells=None):
    """Компоненты связности по всем переходам (warp+edge).

    Зона A — компонента старта; дальше по убыванию числа экранов.
    Возвращает (room→zone_id, zones_list).
    zones_list: [{id, color, screens, n, tps_min, tps_avg, nslow}, ...]"""
    trans = level_transitions(level_no, w, h)
    start = tuple(start)
    rooms = [(x, y) for y in range(h) for x in range(w)]
    adj = collections.defaultdict(set)
    for a, b, _d, _k in trans:
        adj[a].add(b)
        adj[b].add(a)

    seen = set()
    comps = []

    def bfs(seed):
        q = collections.deque([seed])
        seen.add(seed)
        comp = []
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        return comp

    if start in rooms:
        comps.append(bfs(start))
    for r in rooms:
        if r not in seen:
            comps.append(bfs(r))

    # A = старт; остальные по размеру
    start_comp = comps[0] if comps and start in comps[0] else None
    rest = [c for c in comps if c is not start_comp]
    rest.sort(key=lambda c: (-len(c), min(c)))
    ordered = ([start_comp] if start_comp is not None else []) + rest

    room_zone = {}
    zones = []
    for i, comp in enumerate(ordered):
        if not comp:
            continue
        zid = chr(ord('A') + i) if i < 26 else f'Z{i}'
        col = ZONE_COLORS[i % len(ZONE_COLORS)]
        screens = sorted(comp, key=lambda p: (p[1], p[0]))
        tps_vals = []
        if cells:
            for sx, sy in screens:
                st, wk = _tps_pair(cells.get((sx, sy), {}))
                w = _tps_worst(st, wk)
                if w is not None:
                    tps_vals.append(w)
        z = dict(
            id=zid,
            color=col,
            screens=screens,
            n=len(screens),
            tps_min=min(tps_vals) if tps_vals else None,
            tps_avg=(sum(tps_vals) / len(tps_vals)) if tps_vals else None,
            nslow=sum(1 for t in tps_vals if t < 10.0),
            has_start=(start in comp),
        )
        zones.append(z)
        for s in screens:
            room_zone[s] = zid
    return room_zone, zones


def write_zones_json(lv, w, h, start, zones, room_zone, out_path):
    payload = {
        'level': lv,
        'grid': [w, h],
        'start': list(start),
        'nzones': len(zones),
        'zones': [
            {
                'id': z['id'],
                'color': z['color'],
                'n': z['n'],
                'has_start': z['has_start'],
                'tps_min': z['tps_min'],
                'tps_avg': round(z['tps_avg'], 2) if z['tps_avg'] is not None else None,
                'nslow': z['nslow'],
                'screens': [[x, y] for x, y in z['screens']],
            }
            for z in zones
        ],
        'room_zone': {f'{x},{y}': zid for (x, y), zid in room_zone.items()},
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def write_level_html(lv, w, h, cells, out_html, start=None):
    """Карта по реальным переходам (телепорты + края), не по индексу (x,y)."""
    def color(tps):
        if tps is None:
            return '#555'
        if tps >= 9.8:
            return '#2a2'
        if tps >= 8.0:
            return '#8a0'
        if tps >= 6.5:
            return '#c80'
        return '#c33'

    start = tuple(start) if start else (0, 0)
    layout, warps, trans, (wok, wtot, eok, etot) = layout_rooms(lv, w, h, start)
    room_zone, zones = level_zones(lv, w, h, start, cells)
    write_zones_json(lv, w, h, start, zones, room_zone, out_html.with_name(f'level{lv}_zones.json'))

    max_mx = max(p[0] for p in layout.values()) + 1
    max_my = max(p[1] for p in layout.values()) + 1
    zone_color = {z['id']: z['color'] for z in zones}

    cell_w = 140
    cell_h = cell_w * ATLAS_H // 256
    map_w = max_mx * cell_w
    map_h = max_my * cell_h

    tip_from = collections.defaultdict(list)
    for a, b, d, k in trans:
        tip_from[a].append(f'{k[0]}{d}→({b[0]},{b[1]})')

    lines = []
    drawn = set()
    for a, b, d, k in trans:
        if a not in layout or b not in layout:
            continue
        key = tuple(sorted((a, b))) + (k,)
        if key in drawn:
            continue
        drawn.add(key)
        ax, ay = layout[a]
        bx, by = layout[b]
        x1 = (ax + 0.5) * cell_w
        y1 = (ay + 0.5) * cell_h
        x2 = (bx + 0.5) * cell_w
        y2 = (by + 0.5) * cell_h
        col = '#fc6' if k == 'warp' else '#4af'
        op = '0.85' if k == 'warp' else '0.45'
        sw = '2.5' if k == 'warp' else '1.5'
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-opacity="{op}" stroke-width="{sw}"/>'
        )

    cells_html = []
    for (lx, ly), (mx, my) in sorted(layout.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        c = cells.get((lx, ly), {})
        tps_s, tps_w = _tps_pair(c)
        tps = _tps_worst(tps_s, tps_w)
        img = c.get('img')
        err = c.get('err')
        label = f'{lx},{ly}'
        speed = _format_spd(tps_s, tps_w)
        zid = room_zone.get((lx, ly), '?')
        zcol = zone_color.get(zid, '#888')
        cls = 'cell'
        if (lx, ly) == start:
            cls += ' start'
        tips = tip_from.get((lx, ly), [])
        title = f'экран ({label}) · зона {zid} · стоя/ходьба {speed}'
        if tips:
            title += ' · ' + ', '.join(tips)
        if err:
            body = f'<div class="err">{html_escape(err[:80])}</div>'
        else:
            body = (
                f'<img src="{img}?v={ATLAS_IMG_V}" alt="{label}" loading="lazy">'
                f'<span class="xy">{label}</span>'
                f'<span class="zone" style="background:{zcol}">{zid}</span>'
                f'<span class="spd" style="background:{color(tps)}" title="стоя / ходьба">{speed}</span>'
            )
        cells_html.append(
            f'<div class="{cls}" style="grid-column:{mx+1};grid-row:{my+1};'
            f'box-shadow:inset 0 0 0 2px {zcol}" '
            f'title="{html_escape(title)}">{body}</div>'
        )

    zone_rows = []
    for z in zones:
        scr = ' '.join(f'({x},{y})' for x, y in z['screens'])
        tmin = f'{z["tps_min"]:.1f}' if z['tps_min'] is not None else '—'
        tavg = f'{z["tps_avg"]:.1f}' if z['tps_avg'] is not None else '—'
        mark = ' ← старт' if z['has_start'] else ''
        zone_rows.append(
            f'<tr><td><span class="zbadge" style="background:{z["color"]}">{z["id"]}</span>{mark}</td>'
            f'<td>{z["n"]}</td><td>{z["nslow"]}</td><td>{tmin}</td><td>{tavg}</td>'
            f'<td class="scrs">{html_escape(scr)}</td></tr>'
        )

    nwarp = len({(a, b) for a, b, _ in warps})
    doc = f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Уровень {lv} — зоны</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #111; color: #eee; margin: 1rem; }}
a {{ color: #8cf; }}
h1 {{ font-weight: 600; font-size: 1.25rem; margin: 0.4rem 0; }}
h2 {{ font-weight: 600; font-size: 1rem; margin: 1.2rem 0 0.4rem; color: #ccc; }}
.meta {{ color: #999; margin: 0 0 0.8rem; max-width: 56rem; line-height: 1.4; font-size: 14px; }}
.legend span {{ display: inline-block; padding: 2px 8px; margin: 0 6px 8px 0; border-radius: 3px;
  color: #111; font-size: 12px; font-weight: 600; }}
.legend .startmark {{ background: transparent; color: #fc6; border: 1px solid #fc6; }}
.legend .warpmark {{ background: transparent; color: #fc6; border: 1px solid #fc6; }}
.legend .edgemark {{ background: transparent; color: #4af; border: 1px solid #4af; }}
.mapwrap {{ overflow: auto; border: 1px solid #333; display: inline-block; max-width: 100%;
  position: relative; }}
.grid {{
  display: grid;
  grid-template-columns: repeat({max_mx}, {cell_w}px);
  grid-template-rows: repeat({max_my}, {cell_h}px);
  gap: 0;
  width: {map_w}px;
  background: #0a0a0a;
}}
.cell {{
  position: relative;
  margin: 0; padding: 0;
  overflow: hidden;
}}
.cell.start {{ outline: 2px solid #fc6; outline-offset: -2px; z-index: 1; }}
.cell img {{
  display: block; width: 100%; height: 100%;
  object-fit: fill; image-rendering: pixelated; background: #000;
}}
.xy {{
  position: absolute; left: 3px; top: 2px;
  font-size: 10px; color: #fff; text-shadow: 0 0 3px #000, 0 1px 2px #000;
  opacity: 0.85; pointer-events: none;
}}
.zone {{
  position: absolute; left: 3px; bottom: 3px;
  font-size: 11px; font-weight: 800; color: #111;
  padding: 1px 5px; border-radius: 2px; pointer-events: none;
}}
.spd {{
  position: absolute; right: 3px; bottom: 3px;
  font-size: 9px; font-weight: 700; color: #111;
  padding: 1px 4px; border-radius: 2px; pointer-events: none;
  letter-spacing: -0.02em;
}}
.err {{ color: #f66; font-size: 11px; padding: 8px; }}
.links {{
  position: absolute; left: 0; top: 0; width: {map_w}px; height: {map_h}px;
  pointer-events: none; z-index: 2;
}}
table.zones {{ border-collapse: collapse; font-size: 13px; margin: 0.4rem 0 1rem; max-width: 100%; }}
table.zones td, table.zones th {{ padding: 5px 10px; border-bottom: 1px solid #333; text-align: left; vertical-align: top; }}
table.zones th {{ color: #aaa; font-weight: 500; }}
.zbadge {{ display: inline-block; min-width: 1.2em; text-align: center; padding: 1px 6px;
  border-radius: 3px; color: #111; font-weight: 800; margin-right: 6px; }}
.scrs {{ color: #aaa; font-family: ui-monospace, monospace; font-size: 12px; line-height: 1.45;
  max-width: 40rem; }}
</style></head><body>
<p><a href="index.html">← все уровни</a> · <a href="level{lv}_zones.json">zones.json</a></p>
<h1>Уровень {lv} — зоны по переходам</h1>
<p class="meta">Зона = компонента связности (телепорт или открытый край). A — зона старта
({start[0]},{start[1]}). Зон: {len(zones)}. Раскладка карты — остов переходов.
Телепорты рядом: {wok}/{wtot}, края: {eok}/{etot} ({nwarp} телепортов).
Жёлтые линии — телепорт, синие — край.
Скорость на бейдже: <b>стоя / ходьба</b> (тик/с; цвет — худшее из двух).</p>
<h2>Зоны</h2>
<table class="zones">
<tr><th>Зона</th><th>Экранов</th><th>&lt;10 т/с</th><th>Мин</th><th>Средн</th><th>Экраны</th></tr>
{''.join(zone_rows)}
</table>
<p class="legend">
<span style="background:#2a2">≥9.8</span>
<span style="background:#8a0">≥8</span>
<span style="background:#c80">≥6.5</span>
<span style="background:#c33">&lt;6.5</span>
<span class="startmark">старт</span>
<span class="warpmark">телепорт</span>
<span class="edgemark">край</span>
</p>
<div class="mapwrap">
<div class="grid">
{''.join(cells_html)}
</div>
<svg class="links" viewBox="0 0 {map_w} {map_h}" xmlns="http://www.w3.org/2000/svg">
{''.join(lines)}
</svg>
</div>
</body></html>
'''
    out_html.write_text(doc, encoding='utf-8')
    return len(zones)


def write_index(levels_meta, out_html):
    rows = []
    for row in levels_meta:
        if len(row) >= 6:
            lv, w, h, nslow, avg_min, nzones = row[:6]
        else:
            lv, w, h, nslow, avg_min = row
            nzones = '—'
        rows.append(
            f'<tr><td><a href="level{lv}.html">Уровень {lv}</a></td>'
            f'<td>{w}×{h}</td><td>{nzones}</td><td>{nslow}</td>'
            f'<td>{avg_min:.1f} тик/с</td>'
            f'<td><a href="level{lv}_zones.json">json</a></td></tr>')
    doc = f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Ianna — зоны уровней</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #1a1a1c; color: #eee; margin: 1.5rem; }}
a {{ color: #8cf; }}
table {{ border-collapse: collapse; }}
td, th {{ padding: 6px 12px; border-bottom: 1px solid #333; text-align: left; }}
th {{ color: #aaa; font-weight: 500; }}
</style></head><body>
<h1>Зоны The Sword of Ianna (Vector-06C)</h1>
<p>Зона = компонента связности по телепортам и открытым краям. Для разбиения уровней / подгрузки.</p>
<table>
<tr><th>Уровень</th><th>Сетка</th><th>Зон</th><th>Экранов &lt;10 тик/с</th><th>Мин. тик/с</th><th>Данные</th></tr>
{''.join(rows)}
</table>
</body></html>
'''
    out_html.write_text(doc, encoding='utf-8')


def _job(args):
    """Воркер: один экран. args = (lv, x, y, rom, lst, edd, png, frames, hide_hero)"""
    lv, x, y, rom, lst, edd, png, frames, hide_hero = args
    try:
        fr_s, tps_s, fr_w, tps_w = capture_screen(
            pathlib.Path(rom), pathlib.Path(lst), pathlib.Path(edd),
            (x, y), pathlib.Path(png), frames, hide_hero=hide_hero)
        return lv, x, y, dict(
            tps=tps_s, tps_stand=tps_s, tps_walk=tps_w,
            frames=fr_s, frames_walk=fr_w,
            img=f'img/l{lv}_{x}_{y}.png', err=None)
    except Exception as e:
        return lv, x, y, dict(tps=None, tps_stand=None, tps_walk=None,
                              frames=None, frames_walk=None, img=None, err=str(e))


def resnap_pngs():
    """Переснять только PNG (скорости из JSON), с правильным кропом +32."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'img').mkdir(exist_ok=True)
    paths = {lv: ensure_level(lv) for lv in LEVELS}
    meta_all = []
    for lv in LEVELS:
        info = parse_level((SRC / f'level{lv}.map').read_bytes())
        w, h = info['w'], info['h']
        start = (info['header'][17], info['header'][18])
        rom, lst, edd = paths[lv]
        speeds = {}
        jpath = OUT / f'level{lv}.json'
        if jpath.exists():
            speeds = json.loads(jpath.read_text(encoding='utf-8'))
        print(f'=== resnap ур.{lv} {w}×{h} ===', flush=True)
        jobs = [(lv, x, y, str(rom), str(lst), str(edd),
                 str(OUT / 'img' / f'l{lv}_{x}_{y}.png'), 0,
                 (x, y) != start)
                for y in range(h) for x in range(w)]
        cells = {}
        done = 0
        with ProcessPoolExecutor(max_workers=JOBS) as pool:
            futs = [pool.submit(_job, j) for j in jobs]
            for fut in as_completed(futs):
                _, x, y, cell = fut.result()
                tps = speeds.get(f'{x},{y}')
                st, wk = _tps_pair(tps)
                cell['tps'] = st
                cell['tps_stand'] = st
                cell['tps_walk'] = wk
                cells[(x, y)] = cell
                done += 1
                if done % 10 == 0 or done == len(jobs):
                    print(f'  [{done}/{len(jobs)}]', flush=True)
        nz = write_level_html(lv, w, h, cells, OUT / f'level{lv}.html', start=start)
        worst = [_tps_worst(*_tps_pair(c)) for c in cells.values()]
        tps_list = [t for t in worst if t is not None]
        nslow = sum(1 for t in tps_list if t < 10.0)
        amin = min(tps_list) if tps_list else 0
        meta_all.append((lv, w, h, nslow, amin, nz))
    write_index(meta_all, OUT / 'index.html')
    print(f'готово: {OUT / "index.html"}', flush=True)


def main():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'img').mkdir(exist_ok=True)
    meta_all = []

    # сначала все наборы (последовательно — общая build/)
    paths = {}
    for lv in LEVELS:
        paths[lv] = ensure_level(lv)

    for lv in LEVELS:
        info = parse_level((SRC / f'level{lv}.map').read_bytes())
        w, h = info['w'], info['h']
        rom, lst, edd = paths[lv]
        start = (info['header'][17], info['header'][18])
        print(f'=== уровень {lv}: {w}×{h} = {w*h} экранов, jobs={JOBS} ===', flush=True)
        jobs = []
        for y in range(h):
            for x in range(w):
                png = OUT / 'img' / f'l{lv}_{x}_{y}.png'
                jobs.append((lv, x, y, str(rom), str(lst), str(edd), str(png), FRAMES,
                             (x, y) != start))
        cells = {}
        done = 0
        with ProcessPoolExecutor(max_workers=JOBS) as pool:
            futs = [pool.submit(_job, j) for j in jobs]
            for fut in as_completed(futs):
                _, x, y, cell = fut.result()
                cells[(x, y)] = cell
                done += 1
                st, wk = _tps_pair(cell)
                if st is not None or wk is not None:
                    mark = _format_spd(st, wk) + ' т/с'
                else:
                    mark = f'FAIL {(cell.get("err") or "")[:40]}'
                print(f'  [{done}/{len(jobs)}] ({x},{y}) {mark}', flush=True)
        nz = write_level_html(lv, w, h, cells, OUT / f'level{lv}.html', start=start)
        worst = [_tps_worst(*_tps_pair(c)) for c in cells.values()]
        tps_list = [t for t in worst if t is not None]
        nslow = sum(1 for t in tps_list if t < 10.0)
        amin = min(tps_list) if tps_list else 0
        meta_all.append((lv, w, h, nslow, amin, nz))
        summary = {
            f'{x},{y}': {
                'stand': cells[(x, y)].get('tps_stand'),
                'walk': cells[(x, y)].get('tps_walk'),
            }
            for y in range(h) for x in range(w)
        }
        (OUT / f'level{lv}.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    write_index(meta_all, OUT / 'index.html')
    print(f'готово: {OUT / "index.html"}', flush=True)


def regen_html_only():
    """Пересобрать HTML из уже снятых PNG/JSON без эмуляции."""
    OUT.mkdir(parents=True, exist_ok=True)
    meta_all = []
    for lv in LEVELS:
        info = parse_level((SRC / f'level{lv}.map').read_bytes())
        w, h = info['w'], info['h']
        start = (info['header'][17], info['header'][18])
        jpath = OUT / f'level{lv}.json'
        if not jpath.exists():
            print(f'нет {jpath}, пропуск', flush=True)
            continue
        speeds = json.loads(jpath.read_text(encoding='utf-8'))
        cells = {}
        for y in range(h):
            for x in range(w):
                key = f'{x},{y}'
                img = f'img/l{lv}_{x}_{y}.png'
                st, wk = _tps_pair(speeds.get(key))
                if not (OUT / img).exists():
                    cells[(x, y)] = dict(err='нет PNG', tps=None, tps_stand=None, tps_walk=None, img=None)
                else:
                    cells[(x, y)] = dict(tps=st, tps_stand=st, tps_walk=wk, img=img)
        nz = write_level_html(lv, w, h, cells, OUT / f'level{lv}.html', start=start)
        worst = [_tps_worst(*_tps_pair(c)) for c in cells.values()]
        tps_list = [t for t in worst if t is not None]
        nslow = sum(1 for t in tps_list if t < 10.0)
        amin = min(tps_list) if tps_list else 0
        meta_all.append((lv, w, h, nslow, amin, nz))
        print(f'уровень {lv}: {nz} зон, сетка {w}×{h}, старт {start}', flush=True)
    write_index(meta_all, OUT / 'index.html')
    print(f'готово: {OUT / "index.html"}', flush=True)


if __name__ == '__main__':
    if '--html-only' in OPTS:
        regen_html_only()
    elif '--resnap' in OPTS:
        resnap_pngs()
    else:
        main()
