#!/usr/bin/env python3
"""Мёртвый код ROM статически: достижимость меток по листингу. Метка жива, если на неё есть ссылка из живого
кода или данных (jp/call/ld hl,метка/dw метка), либо живой код «проваливается» в неё (предыдущая команда —
не безусловный jp/ret). Корни: $0100 (vec_start), метки, на которые ссылаются оверлеи и RAM-блобы (меню,
пауза, загрузчик банков, wpn_load, fgc), и то, что перечислено в --roots. Покрытие стендами (coverage.py)
говорит «не исполнялось», этот отчёт — «недостижимо вовсе»: такое можно удалять без оглядки на редкие ветки.
  python3 tools/deadcode.py [--lst=build/ianna_vec.lst] [--min=4] [--roots=a,b] [--file=vec_vdp.asm]"""
import sys, re, pathlib, collections, bisect

OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
ROOT = pathlib.Path(__file__).resolve().parents[1]
def opt(name, default=None):
    return next((o[len(name) + 3:] for o in OPTS if o.startswith(f'--{name}=')), default)
LST = pathlib.Path(opt('lst', str(ROOT / 'build/ianna_vec.lst'))); MIN = int(opt('min', '4')); ONLY = opt('file')

# --- листинг -> строки кода: (адрес, длина, текст, файл), метки по адресам, символы (equ) — не блоки
lines = []; labels = collections.OrderedDict(); cur_file = '?'; equs = set()
for line in LST.read_text(errors='replace').splitlines():
    m = re.search(r'; ======== (\S+) ========', line)
    if m: cur_file = m.group(1); continue
    if 'vars наверху ОЗУ' in line: break
    m = re.match(r'^([0-9A-F]{4}):\s+([A-Za-z_][A-Za-z_0-9.]*):', line) or \
        re.match(r'^([0-9A-F]{4}): [0-9A-F]+\s+(?:\[[^\]]*\]\s+)?([A-Za-z_][A-Za-z_0-9.]*):', line)   # метка на строке с байтами (данные)
    if m:
        a = int(m.group(1), 16); labels.setdefault(a, []).append(m.group(2))
    m = re.match(r'^([0-9A-F]{4}):\s+([A-Za-z_][A-Za-z_0-9.]*)\s+equ\b', line, re.I)
    if m: equs.add(m.group(2))
    m = re.match(r'^([0-9A-F]{4}): ([0-9A-F]+)\s+(?:\[[^\]]*\]\s+)?(.*)$', line)
    if m:
        src = m.group(3).split(';')[0]
        lines.append((int(m.group(1), 16), len(m.group(2)) // 2, src.strip(), cur_file))
name2addr = {}
for a, ns in labels.items():
    for n in ns: name2addr[n] = a
# блоки: от метки до следующей метки (по адресам строк кода)
addrs = sorted(labels)
def block_of(a):
    k = bisect.bisect_right(addrs, a) - 1
    return addrs[k] if k >= 0 else None
blocks = collections.OrderedDict((a, []) for a in addrs)
for a, n, src, f in lines:
    b = block_of(a)
    if b is not None: blocks[b].append((a, n, src, f))
ident = re.compile(r'[A-Za-z_][A-Za-z_0-9.]*')
def refs(src):
    body = re.sub(r'^\s*[A-Za-z_][\w.]*:', '', src)                   # метка в начале строки — не ссылка
    body = re.sub(r"'[^']*'|\"[^\"]*\"", '', body)                   # строки
    return [w for w in ident.findall(body) if w in name2addr and w not in equs]
def uncond_end(src):
    s = src.strip().lower()
    return bool(re.match(r"(jp|jmp)\s+[a-z_][\w.]*\s*$", s) or re.match(r"(ret\s*$|jp\s*\(hl\)\s*$|pchl\s*$)", s))
# --- корни
roots = set()
roots.add(block_of(0x100))
for f in ['menu_ovl.asm', 'pause_ovl.asm', 'menu_ram.asm']:
    p = ROOT / 'build' / f
    if p.exists():
        for w in ident.findall(re.sub(r';.*', '', p.read_text(errors='replace'))):
            if w in name2addr: roots.add(name2addr[w])
for f in ['wpn_load.asm', 'fdd_banks.asm', 'fgc_ovl.asm', 'vec_fdd.asm', 'zp_blit2m.asm', 'arkos_hot.asm']:
    p = ROOT / 'src/vec' / f
    if p.exists():
        for w in ident.findall(re.sub(r';.*', '', p.read_text(errors='replace'))):
            if w in name2addr: roots.add(name2addr[w])
for w in (opt('roots') or '').split(','):
    if w in name2addr: roots.add(name2addr[w])
# --- достижимость
live = set(); stack = list(roots)
while stack:
    b = stack.pop()
    if b in live or b is None: continue
    live.add(b)
    ls = blocks.get(b, [])
    for a, n, src, f in ls:
        for w in refs(src):
            t = name2addr[w]
            if t not in live: stack.append(block_of(t))
    # провал в следующий блок
    if ls:
        last = ls[-1][2]
        if not uncond_end(last):
            k = addrs.index(b) + 1
            if k < len(addrs) and addrs[k] not in live: stack.append(addrs[k])
    else:
        k = addrs.index(b) + 1
        if k < len(addrs) and addrs[k] not in live: stack.append(addrs[k])
# --- отчёт: мёртвые блоки кода (данные db/dw тоже показываем, помечая)
dead = []
for b in addrs:
    if b in live: continue
    ls = blocks[b]
    if not ls: continue
    size = sum(n for _, n, _, _ in ls)
    isdata = all(re.match(r'\s*(?:[A-Za-z_][\w.]*:)?\s*(db|dw|ds|defb|defw|defs|dz|dm)\b', s, re.I) for _, _, s, _ in ls)
    dead.append((b, size, ls[0][3], isdata))
tot_code = sum(n for _, n, _, _ in lines)
dead_code = sum(s for _, s, _, d in dead if not d); dead_data = sum(s for _, s, _, d in dead if d)
print(f'код+данные в образе {tot_code} Б; недостижимо: кода {dead_code} Б, данных {dead_data} Б; корней {len(roots)}')
byfile = collections.defaultdict(list)
for b, s, f, d in dead: byfile[f].append((b, s, d))
for f, rs in sorted(byfile.items(), key=lambda kv: -sum(s for _, s, _ in kv[1])):
    if ONLY and f != ONLY: continue
    print(f'\n== {f}: недостижимо {sum(s for _, s, _ in rs)} Б, блоков {len(rs)}')
    # склеить соседние мёртвые блоки
    rs.sort(); runs = []
    for b, s, d in rs:
        if runs and runs[-1][0] + runs[-1][1] == b and runs[-1][2] == d: runs[-1][1] += s; runs[-1][3].append(labels[b][0])
        else: runs.append([b, s, d, [labels[b][0]]])
    for b, s, d, ns in sorted(runs, key=lambda r: -r[1]):
        if s < MIN: continue
        print(f'   ${b:04X} {s:4} Б {"данные " if d else ""}{ns[0]}' + (f' .. {ns[-1]} ({len(ns)})' if len(ns) > 1 else ''))
