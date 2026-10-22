#!/usr/bin/env python3
"""Покрытие кода ROM стендами: какие байты кода ни разу не исполнялись — кандидаты на удаление (место в ROM).

Обёртка: запускает любой стенд (spwatch, fddrt, measure_vec, rtcheck...) с его аргументами, перехватывает
I8080.step и помечает каждый исполненный адрес; в конце пишет битмап 64К в файл.
  python3 tools/coverage.py --out=build/cov/NAME.bin -- tools/spwatch.py <rom> <lst> <edd> X,Y --frames=3000 ...
Отчёт: объединяет битмапы, по листингу делит ROM на метки и файлы, печатает ни разу не исполненные
метки (только код: строки db/dw/ds считаются данными и в кандидаты не идут).
  python3 tools/coverage.py --report build/cov/*.bin [--lst=build/ianna_vec.lst] [--min=6] [--file=vec_vdp.asm]
Стенды кроют не всё (концовка, редкие ветки): каждый кандидат проверяется руками по именам и ссылкам."""
import sys, os, re, pathlib, runpy, atexit, collections

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
ROOT = pathlib.Path(__file__).resolve().parents[1]
def opt(name, default=None):
    return next((o[len(name) + 3:] for o in OPTS if o.startswith(f'--{name}=')), default)

if '--report' in OPTS:
    files = [a for a in sys.argv[1:] if not a.startswith('--')]
    hit = bytearray(65536)
    for f in files:
        b = pathlib.Path(f).read_bytes()
        for i in range(65536):
            if b[i]: hit[i] = 1
    lst = pathlib.Path(opt('lst', str(ROOT / 'build/ianna_vec.lst')))
    MIN = int(opt('min', '6')); ONLY = opt('file')
    # листинг: границы файлов, байты кода/данных по адресам, метки
    cur_file = '?'; is_code = bytearray(65536); is_data = bytearray(65536); owner = {}
    labels = {}       # адрес -> метка (первая)
    for line in lst.read_text(errors='replace').splitlines():
        m = re.search(r'; ======== (\S+) ========', line)
        if m: cur_file = m.group(1); continue
        if 'vars наверху ОЗУ' in line: break
        m = re.match(r'^([0-9A-F]{4}):\s+([A-Za-z_][A-Za-z_0-9.]*):', line) or \
            re.match(r'^([0-9A-F]{4}): [0-9A-F]+\s+(?:\[[^\]]*\]\s+)?([A-Za-z_][A-Za-z_0-9.]*):', line)
        if m:
            a = int(m.group(1), 16); labels.setdefault(a, m.group(2))
        m = re.match(r'^([0-9A-F]{4}): ([0-9A-F]+)\s+(?:\[[^\]]*\]\s+)?(.*)$', line)
        if not m: continue
        a = int(m.group(1), 16); n = len(m.group(2)) // 2; src = m.group(3)
        data = re.match(r'\s*(?:[A-Za-z_][\w.]*:)?\s*(db|dw|ds|defb|defw|defs|dz|dm)\b', src, re.I) is not None
        for i in range(a, min(a + n, 65536)):
            (is_data if data else is_code)[i] = 1; owner[i] = cur_file
    addrs = sorted(labels)
    import bisect
    def lab(a):
        k = bisect.bisect_right(addrs, a) - 1
        return labels[addrs[k]] if k >= 0 else '?'
    code_total = sum(is_code); code_hit = sum(1 for i in range(65536) if is_code[i] and hit[i])
    print(f'код в образе: {code_total} Б, исполнено {code_hit} Б ({100*code_hit/max(code_total,1):.1f} %); '
          f'данных {sum(is_data)} Б; битмапов {len(files)}')
    # ни разу не исполненные куски кода: непрерывные диапазоны, метка — по началу
    runs = []; i = 0
    while i < 65536:
        if is_code[i] and not hit[i]:
            j = i
            while j < 65536 and is_code[j] and not hit[j]: j += 1
            runs.append((i, j)); i = j
        else: i += 1
    byfile = collections.defaultdict(list)
    for a, b in runs:
        byfile[owner.get(a, '?')].append((a, b))
    for f, rs in sorted(byfile.items(), key=lambda kv: -sum(b - a for a, b in kv[1])):
        if ONLY and f != ONLY: continue
        tot = sum(b - a for a, b in rs)
        ftot = sum(1 for i in range(65536) if is_code[i] and owner.get(i) == f)
        print(f'\n== {f}: не исполнено {tot} Б из {ftot} Б кода, кусков {len(rs)}')
        for a, b in sorted(rs, key=lambda r: -(r[1] - r[0])):
            if b - a < MIN: continue
            print(f'   ${a:04X}-${b-1:04X} {b-a:4} Б  {lab(a)}' + (f' .. {lab(b-1)}' if lab(b-1) != lab(a) else ''))
    sys.exit(0)

# --- режим обёртки
OUT = opt('out')
if not OUT or '--' not in sys.argv: sys.exit(__doc__)
k = sys.argv.index('--'); target = sys.argv[k + 1]; args = sys.argv[k + 2:]
for p in (pathlib.Path.home() / 'projects/metalgear-v06c/tools', pathlib.Path.home() / 'projects/knightmare-v06c/tools', ROOT / 'tools'):
    sys.path.insert(0, str(p))
import emu8080
HIT = bytearray(65536)
_step = emu8080.I8080.step
def step(self):
    HIT[self.pc] = 1
    return _step(self)
emu8080.I8080.step = step
def dump():
    pathlib.Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(OUT).write_bytes(HIT)
    n = sum(1 for i in range(0x100, 0x6B00) if HIT[i])
    print(f'[coverage] {OUT}: исполнено адресов в ROM {n}', file=sys.stderr)
atexit.register(dump)
sys.argv = [target] + args
os.chdir(ROOT)
runpy.run_path(target, run_name='__main__')
