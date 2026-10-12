#!/usr/bin/env python3
"""Эталонная таблица скорости по тяжёлым сценам: стоя / ходьба туда-обратно / бой (measure_vec, --fixrand).

  python3 tools/bench_scenes.py --snap                 # собрать build/bench/lN.{rom,lst,edd} из текущего дерева
  python3 tools/bench_scenes.py [--out=build/bench/base.json]      # замер, таблица, запись в JSON
  python3 tools/bench_scenes.py --out=build/bench/x.json --cmp=build/bench/base.json   # замер и сравнение
  python3 tools/bench_scenes.py --show=x.json [--cmp=base.json]    # только таблица из готовых файлов
  [--dir=build/bench] [--jobs=8] [--scenes=2:4,6;4:5,0]

Порог принятия идеи ускорения: выигрыш >= 0,25 кадра/тик хотя бы на трети сцен (в любом режиме).
Герой в замере неуязвим (см. measure_vec): иначе великан убивает его и меряется экран конца игры.
"""
import sys, os, re, json, subprocess, pathlib, concurrent.futures

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPTS = [a for a in sys.argv[1:] if a.startswith('--')]
def opt(name, default=None):
    return next((o[len(name) + 3:] for o in OPTS if o.startswith(f'--{name}=')), default)
DIR = ROOT / opt('dir', 'build/bench')
JOBS = int(opt('jobs', '8'))
ROUTE = 'none:200,pace:240,fight:300'
MODES = ('none', 'pace', 'fight')
NAMES = {'none': 'стоя', 'pace': 'ходьба', 'fight': 'бой'}
THRESH = 0.25
EXTRA = opt('opts', '').split() if opt('opts') else []     # доп. ключи measure_vec, напр. --opts=--tail=spr

# (уровень, экран, кто там[, место героя px]) — место задано там, где штатное место уровня на этом экране
# висит в воздухе: герой падал на экран ниже или гиб, и мерилась не та сцена
SCENES = [
    (1, '4,5', 'мумии'), (1, '0,6', 'мумии×2', '112,32'),
    (2, '4,6', 'голем'), (2, '5,6', 'голем'),
    (3, '1,0', 'враги'), (3, '1,3', 'враги', '64,32'), (3, '5,6', 'огр'),
    (4, '5,0', 'демон'), (4, '6,2', 'минотавр'), (4, '5,4', 'минотавр'),
    (5, '6,0', 'голем'), (5, '1,8', 'голем'),
    (6, '6,1', 'враги'), (6, '4,2', 'огр'), (6, '6,0', 'минотавр'), (6, '2,5', 'огр', '112,32'),
    (8, '3,2', 'голем'), (8, '5,3', 'демон'),
    (9, '3,6', 'огр'),
]
if opt('scenes'):
    want = set(re.findall(r'(\d+):(\d+,\d+)', opt('scenes')))
    SCENES = [s for s in SCENES if (str(s[0]), s[1]) in want]


def snap():
    DIR.mkdir(parents=True, exist_ok=True)
    for n in range(1, 10):
        for _ in range(2):          # дважды: после смены ROM оверлеи в EDD устаревают
            for cmd in (['tools/data/build_edd.py', f'--level={n}'], ['tools/build_vec.py']):
                p = subprocess.run([sys.executable] + cmd, cwd=ROOT, capture_output=True, text=True)
                assert p.returncode == 0, (cmd, p.stdout[-600:] + p.stderr[-600:])
        for src, ext in (('ianna.rom', 'rom'), ('ianna_vec.lst', 'lst'), ('ianna.edd', 'edd')):
            (DIR / f'l{n}.{ext}').write_bytes((ROOT / 'build' / src).read_bytes())
        print(f'уровень {n}: снимок готов', flush=True)
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'src', 'tools/build_vec.py', 'tools/data', 'tools/z80to8080.py'],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (DIR / 'HEAD').write_text(head + (' +правки' if dirty else '') + '\n')


def measure(sc):
    lv, xy, name = sc[:3]
    env = dict(os.environ, IANNA_EDD=str(DIR / f'l{lv}.edd'))
    p = subprocess.run([sys.executable, 'tools/measure_vec.py', str(DIR / f'l{lv}.rom'), str(DIR / f'l{lv}.lst'),
                        f'--start={xy}', f'--route={ROUTE}', '--fixrand'] + EXTRA + ([f'--pos={sc[3]}'] if len(sc) > 3 else []),
                       cwd=ROOT, capture_output=True, text=True, env=env)
    out = p.stdout + p.stderr
    row = {}
    for m in re.finditer(r'^\s+(none|pace|fight)\s+\d+ кадров:.*?обычных тиков (\d+): ([\d.]+) кадра/тик.*?простой \(halt\) (\d+) %(.*)$',
                         out, re.M):
        tail = m.group(5)
        e = re.search(r'экран (\d+,\d+)', tail)
        row[m.group(1)] = {'fpt': float(m.group(3)), 'ticks': int(m.group(2)), 'idle': int(m.group(4)),
                           'screen': e.group(1) if e else '?', 'dead': 'погиб' in tail,
                           'msg': int((re.search(r'тиков с текстом (\d+)', tail) or [0, 0])[1]),
                           'loads': int((re.search(r'смен экрана (\d+)', tail) or [0, 0])[1])}
    if p.returncode != 0 or len(row) != len(MODES):
        row['err'] = out[-300:]
    return f'{lv}:{xy}', name, row


def note(xy, r):
    n = []
    if r['dead']: n.append('погиб')
    if r['screen'] != xy: n.append(f'ушёл на {r["screen"]}')
    if r['ticks'] < 15: n.append(f'тиков {r["ticks"]}')
    if r['msg']: n.append('текст')
    return n


def table(res, base=None):
    hdr = '| сцена | ' + ' | '.join(NAMES[m] for m in MODES) + ' | замечания |'
    print(hdr); print('|---|' + '---:|' * len(MODES) + '---|')
    won = 0; total = 0
    for key, v in res['scenes'].items():
        row = v['row']; xy = key.split(':')[1]
        if 'err' in row:
            print(f'| {key} {v["name"]} | ' + ' | '.join('—' for _ in MODES) + f' | ОШИБКА: {row["err"][-80:]!r} |'); continue
        cells = []; notes = []; best = 0.0
        for m in MODES:
            r = row[m]; c = f'{r["fpt"]:.2f}'
            b = base and base['scenes'].get(key, {}).get('row', {}).get(m)
            if b:
                d = b['fpt'] - r['fpt']; best = max(best, d); c += f' ({-d:+.2f})'
            cells.append(c)
            notes += [f'{NAMES[m]}: {x}' for x in note(xy, r)]
        if base: total += 1; won += best >= THRESH
        print(f'| {key} {v["name"]} | ' + ' | '.join(cells) + ' | ' + '; '.join(notes) + ' |')
    print(f'\nкадров на тик (меньше — быстрее; 5 = полная скорость, 10 тик/с); сборка {res.get("head", "?")}')
    if base:
        ok = total and won * 3 >= total
        print(f'сравнение с {base.get("head", "?")}: выигрыш >= {THRESH} кадра/тик на {won} из {total} сцен — '
              + ('порог пройден' if ok else 'порог НЕ пройден'))


if '--snap' in OPTS:
    snap(); sys.exit()
base = json.loads(pathlib.Path(opt('cmp')).read_text()) if opt('cmp') else None
if opt('show'):
    table(json.loads(pathlib.Path(opt('show')).read_text()), base); sys.exit()
res = {'head': (DIR / 'HEAD').read_text().strip() if (DIR / 'HEAD').exists() else '?', 'route': ROUTE, 'scenes': {}}
with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
    for key, name, row in ex.map(measure, SCENES):
        res['scenes'][key] = {'name': name, 'row': row}
        print(f'# {key} {name}: ' + (' / '.join(f'{row[m]["fpt"]:.2f}' for m in MODES) if 'err' not in row else 'ОШИБКА'), flush=True)
out = pathlib.Path(opt('out', str(DIR / 'base.json')))
out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(f'\nзаписано: {out}\n')
table(res, base)
