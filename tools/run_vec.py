#!/usr/bin/env python3
"""Headless-прогон ianna.rom (Вектор-06Ц) на emu_kvaz (i8080 + квазидиск) с рендером PNG.

  run_vec.py <кадров> [маршрут] [out.png]
  маршрут: "none" | "left" | "right:100,none:20,left:50" (клавиши: up/down/left/right/fire/action)
Печатает состояние игрока (entity/sprite), PC и такты.
"""
import sys, re, os, pathlib
sys.path.insert(0, str(pathlib.Path.home() / 'projects/metalgear-v06c/tools'))
sys.path.insert(0, str(pathlib.Path.home() / 'projects/knightmare-v06c/tools'))
from emu_kvaz import I8080Kvaz as I8080

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEY_ROW0 = {'down': 0x80, 'right': 0x40, 'up': 0x20, 'left': 0x10}
KEY_ROW7 = {'fire': 0x80, 'z': 0x04, 'action': 0x01}
KEY_ROW5 = {'h': 0x01, 'j': 0x04}   # H — пауза, J — джукбокс меню

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

DEMO = '--demo' in sys.argv
if DEMO: sys.argv.remove('--demo')
START = None   # --start=sx,sy: стартовый экран уровня (патчится при входе в game)
for a in list(sys.argv):
    if a.startswith('--start='):
        START = tuple(int(v) for v in a[8:].split(',')); sys.argv.remove(a)
ROM_NAME = 'ianna_demo' if DEMO else 'ianna'

def make_cpu(keys):
    cpu = I8080()
    # --- ВГ93: чтение секторов из образа дискеты (IANNA_FDD). Без этого дискетная ветка — загрузка
    # уровня и переход между уровнями — headless вообще не проверялась: зависание образа ловилось
    # только руками в эмуляторе. Геометрия 80x2x5x1024, адреса портов инвертированы, как на Векторе.
    fdd_path = os.environ.get('IANNA_FDD')
    fdd = pathlib.Path(fdd_path).read_bytes() if fdd_path and pathlib.Path(fdd_path).exists() else None
    st = {'trk': 0, 'sec': 1, 'side': 0, 'buf': b'', 'pos': 0, 'busy': False}
    cur = [0xFF]

    if not DEMO:
        cpu.load_edd(pathlib.Path(os.environ.get('IANNA_EDD', ROOT / 'build/ianna.edd')))
    # При дискетном прогоне ROM берём ИЗ ОБРАЗА: build_fdd прошивает в него таблицу дорожек уровней
    # (vfl_dirtab), а в build/ianna.rom она нулевая — загрузчик решал бы, что набора на дискете нет.
    rom = fdd[0x80:0x80+32512] if fdd else (ROOT / f'build/{ROM_NAME}.rom').read_bytes()  # в образе ROM лежит за дескриптором ($80)
    cpu.mem[0x100:0x100+len(rom)] = rom
    cpu.pc = 0x100
    # Оверлей меню лежит только в наборе уровня 1 (на уровнях 2+ его место отдано банкам спрайтов).
    # Стенды запускают набор любого уровня напрямую, поэтому, если меню в наборе нет, вызов фазы
    # меню из ROM заменяем пустышкой — иначе игра уходит по $8440 в мусор и не стартует.
    patch_menu(cpu)
    def fdd_seek_read():
        off = ((st['trk'] * 2 + st['side']) * 5 + (st['sec'] - 1)) * 1024
        st['buf'] = fdd[off:off + 1024] if fdd and off + 1024 <= len(fdd) else b'\x00' * 1024
        st['pos'] = 0; st['busy'] = True
    # ВИ53 счётчик 0 — секундомер фазы кадра (vec_phase/vec_budget/сброс пула ждут луч по нему). Без
    # модели порт отдавал константу, и любое ожидание «пока луч пройдёт» крутилось вечно (2026-09-04).
    # Время здесь — счётчик инструкций: ~8 тактов Вектора на инструкцию = 4 тика ВИ53 (1.5 МГц).
    pit = {'reload': 0, 'latched': None, 'wr': 0, 'rd': 0}
    # IANNA_PITSCALE (проценты, по умолчанию 100) — стендовая ручка «луч идёт быстрее/медленнее
    # кода». Меняет ТОЛЬКО фазу луча, код и логика те же. Нужна, чтобы отличить настоящее
    # расхождение рендера от законной фазовой чувствительности пула: сброс сам решает, что вывести
    # сейчас, а что позади луча, и на некоторых тиках VRAM у одной и той же сборки при разной фазе
    # отличается (tools/cmpticks.py --phase).
    pit_scale = int(os.environ.get('IANNA_PITSCALE', 100))
    def pit_val():
        return (0xFFFF - (((cpu.icount - pit['reload']) * 4 * pit_scale // 100) & 0xFFFF)) & 0xFFFF
    def out_handler(port, val):
        if port == 0x03: cur[0] = val
        elif port == 0x10: cpu.kv_out(port, val)
        elif port == 0x08:
            if val == 0: pit['latched'] = pit_val(); pit['rd'] = 0
        elif port == 0x0B:
            if pit['wr'] == 0: pit['wr'] = 1
            else: pit['wr'] = 0; pit['reload'] = cpu.icount
        elif port == 0x1C: st['side'] = 0 if (val & 4) else 1   # бит 2 инвертирован (проверено сверкой с образом)
        elif port == 0x1A: st['trk'] = val
        elif port == 0x19: st['sec'] = val
        elif port == 0x1B:
            if val == 0x00: st['trk'] = 0; st['busy'] = False          # RESTORE
            elif val == 0x58: st['trk'] += 1; st['busy'] = False       # STEP-IN с обновлением трека
            elif val == 0x80: fdd_seek_read()                           # READ SECTOR
    def in_handler(port):
        if port == 0x0B:
            v = pit['latched'] if pit['latched'] is not None else pit_val()
            if pit['rd'] == 0: pit['rd'] = 1; return v & 0xFF
            pit['rd'] = 0; pit['latched'] = None; return v >> 8
        if port == 0x1B:                    # статус: бит0 BUSY, бит1 DRQ
            return (0x03 if st['busy'] and st['pos'] < len(st['buf']) else 0x00)
        if port == 0x18:                    # данные
            if st['pos'] < len(st['buf']):
                v = st['buf'][st['pos']]; st['pos'] += 1
                if st['pos'] >= len(st['buf']): st['busy'] = False
                return v
            return 0
        if port == 0x1A: return st['trk']
        # Эхо регистра сектора — по нему mb_fdc_ok (menu_ram) решает, есть ли дисковод. Без эха
        # фаза меню и все слайды (интро, концовка, титры) headless не шли вовсе: оверлей считал,
        # что дисковода нет, и уходил сразу в игру. Отвечаем ТОЛЬКО когда образ дискеты подан:
        # стенды без него (cmpbuild, gates) на «дисковод есть» повисли бы в меню.
        if port == 0x19: return st['sec'] if fdd else 0xFF
        if port == 0x02:
            v = 0xFF
            if cur[0] == 0xFE:
                for k in keys:
                    if k in KEY_ROW0: v &= ~KEY_ROW0[k] & 0xFF
            if cur[0] == 0xDF:
                for k in keys:
                    if k in KEY_ROW5: v &= ~KEY_ROW5[k] & 0xFF
            if cur[0] == 0x7F:
                for k in keys:
                    if k in KEY_ROW7: v &= ~KEY_ROW7[k] & 0xFF
            return v
        return 0xFF
    cpu.out_handler = out_handler
    cpu.in_handler = in_handler
    return cpu

_start_done = [False]
STEP_BUDGET = 13000   # инструкций на кадр без halt (прерывание должно прийти и в busy-loop wait_till_read).
                      # Для сверки СБОРОК между собой ставьте ~400000: иначе обычный кадр обрывается по числу
                      # инструкций, более быстрый код получает прерывание в другой точке, и логика двух сборок
                      # расходится без всякой ошибки (ловилось как «разные снимки после замены exx»)
def run_frames(cpu, n, budget=None, sym=None):
    if budget is None: budget = STEP_BUDGET
    """кадр = до HALT или ~13000 инструкций (~60К тактов), затем RST7 если EI —
    как на железе: прерывание приходит и в busy-loop (wait_till_read)."""
    for _ in range(n):
        c = 0
        while not cpu.halted and c < budget:
            if START and sym and not _start_done[0] and cpu.pc == sym['SaveCheckpoint']:
                cpu.mem[sym['current_levelx']] = START[0]; cpu.mem[sym['current_levely']] = START[1]; _start_done[0] = True
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie:
            cpu.ie = False
            cpu.push(cpu.pc)
            cpu.pc = 0x38

class Warmup:
    """Прогрев до старта игры (общий для стендов): первый RunScripts + 60 кадров. Сообщение уровня
    (action_string печатает текст ~200 кадров по кусочку панели за halt, потом крутится в wait_till_read)
    снимается автоматически: увидев action_string, ждём wait_till_read, держим fire до следующего RunScripts.
    Дольше 60 кадров без сообщения ждать нельзя — на экранах без него игра идёт сразу (враг убьёт героя)."""
    def __init__(self, sym, keys, after=60):
        self.RS = sym['RunScripts']; self.WT = sym.get('wait_till_read', -1); self.AS = sym.get('action_string', -1)
        self.keys = keys; self.after = after; self.first = None; self.msg = False; self.in_wait = False
    def step(self, pc, fr):
        """Вызывать на каждой инструкции (pc до шага, fr — номер кадра). True = прогрев окончен."""
        if pc == self.RS:
            if self.first is None: self.first = fr
            if self.in_wait: self.keys.clear(); self.in_wait = False; self.msg = False
        elif pc == self.AS: self.msg = True
        elif pc == self.WT and not self.in_wait: self.keys.append('fire'); self.in_wait = True
        return self.first is not None and fr - self.first >= self.after and not self.msg and not self.in_wait
def patch_menu(cpu):
    """Оверлей меню лежит только в наборе уровня 1; стенды запускают набор любого уровня напрямую,
    поэтому, если меню в наборе нет, вызов фазы меню из ROM глушим — иначе игра уходит по $8440
    в мусор и не стартует. Зовут make_cpu и measure_vec (он грузит ROM сам)."""
    if DEMO: return
    mo = ROOT / 'build/menu_ovl.bin'
    head = mo.read_bytes()[:16] if mo.exists() else b''
    if head and bytes(cpu.kvaz[3*65536 + 0x8440: 3*65536 + 0x8450]) != head:
        syms = load_syms(ROOT / 'build/ianna_vec.lst')
        mp = syms.get('vec_menu_phase')
        if mp:
            call = bytes((0xCD, mp & 0xFF, mp >> 8))
            for a in range(0x100, 0x8000 - 3):
                if bytes(cpu.mem[a:a+3]) == call: cpu.mem[a:a+3] = b'\x00\x00\x00'

def start_game(cpu, keys, sym, max_frames=1500):
    w = Warmup(sym, keys); done = False
    for fr in range(max_frames):
        c = 0
        while not cpu.halted and c < STEP_BUDGET:
            pc = cpu.pc
            if START and not _start_done[0] and pc == sym['SaveCheckpoint']:
                cpu.mem[sym['current_levelx']] = START[0]; cpu.mem[sym['current_levely']] = START[1]; _start_done[0] = True
            if w.step(pc, fr): done = True
            cpu.step(); c += 1
        cpu.halted = False
        if cpu.ie: cpu.ie = False; cpu.push(cpu.pc); cpu.pc = 0x38
        if done: break
    keys.clear(); run_frames(cpu, 10, sym=sym)
    assert done, 'игра не стартовала'
def dump_state(cpu, sym):
    ent = sym.get('ENTITY_DATA'); spd = sym.get('SPDATA')
    if ent is None: return
    e = cpu.mem[ent:ent+12]
    print('  player entity: spr=%04x script=%d pos=%d energy=%d state=%d anim=%d' % (e[0] | (e[1] << 8), e[2], e[3], e[4], e[5], e[6]))
    e1 = cpu.mem[ent+12:ent+24]
    if e1[0] | e1[1]:
        print('  enemy1 entity: spr=%04x script=%d pos=%d energy=%d state=%d anim=%d type=%02x' % (e1[0] | (e1[1] << 8), e1[2], e1[3], e1[4], e1[5], e1[6], e1[10]))
        s1 = cpu.mem[spd+8:spd+16]
        print('  sprite1: addr=%04x type=%02x x=%d y=%d' % (s1[0] | (s1[1] << 8), s1[2], s1[3], s1[4]))
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
    sym = load_syms(ROOT / f'build/{ROM_NAME}_vec.lst')
    keys = set()
    cpu = make_cpu(keys)
    segs = [(k, int(n)) for k, n in (s.split(':') for s in route.split(','))] if ':' in route else [(route, frames)]
    total = 0
    try:
        for k, n in segs:
            keys.clear(); keys.update(x for x in k.split('+') if x != 'none')
            run_frames(cpu, n, sym=sym)
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
