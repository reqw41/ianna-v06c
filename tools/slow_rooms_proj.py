#!/usr/bin/env python3
"""Таблица комнат <10 тик/с сейчас и проекция после dirty8 + регистровой музыки.

Для каждой сцены:
  * measure_vec — стоя / бег (кадра/тик, тик/с);
  * dirty8_est — потолок выигрыша т/тик;
  * музыка psgpack — фиксированная экономия ~0.28 кадра/тик (замер mus_reg_bench).

Проекция: кадр/тик' = max(5, кадр/тик − dirty8/FRAME − MUSIC_FR), тик/с' = 50/кадр/тик'.
Печатает только комнаты, где хотя бы один режим сейчас < 10 тик/с.

  python3 tools/slow_rooms_proj.py [каталог_snap=/tmp/ianna_gates_mus]
"""
import sys, os, re, subprocess, pathlib, collections

SNAP = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/ianna_gates_mus')
ROOT = pathlib.Path(__file__).resolve().parents[1]
FRAME = 59904.0
MUSIC_FR = 0.28          # ~17К т/тик / FRAME из mus_reg_bench
MUSIC_T = MUSIC_FR * FRAME

# великаны + известные тяжёлые из gates/ANALYSIS (уровни с snap)
SCENES = [
    (1, '4,5', 'мумии'),
    (1, '0,6', 'мумии×2'),
    (2, '4,6', 'голем'),
    (2, '5,6', 'голем'),
    (3, '1,0', 'враги'),
    (3, '1,2', 'враги'),
    (3, '5,6', 'огр'),
    (4, '5,0', 'демон'),
    (4, '6,2', 'минотавр'),
    (4, '5,4', 'минотавр'),
    (6, '6,1', 'враги'),
    (6, '4,2', 'огр'),
    (6, '6,0', 'минотавр'),
    (6, '2,5', 'огр'),
]

def run(cmd, timeout=180):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr

def measure(lv, xy):
    rom, lst, edd = SNAP / f'l{lv}.rom', SNAP / f'l{lv}.lst', SNAP / f'l{lv}.edd'
    if not rom.exists():
        return None
    env = os.environ.copy()
    env['IANNA_EDD'] = str(edd)
    cmd = [sys.executable, 'tools/measure_vec.py', str(rom), str(lst),
           f'--start={xy}', '--route=none:200,right:200', '--fixrand']
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, timeout=180)
    out = p.stdout + p.stderr
    rows = {}
    for m in re.finditer(
            r'^\s+(none|right)\s+\d+ кадров:.*?([\d.]+) кадра/тик \(([\d.]+) тик/с\)',
            out, re.M):
        rows[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    if p.returncode != 0 or not rows:
        return {'err': out[-400:]}
    return rows

def dirty8(lv, xy, ticks=40):
    rom, lst, edd = SNAP / f'l{lv}.rom', SNAP / f'l{lv}.lst', SNAP / f'l{lv}.edd'
    cmd = [sys.executable, 'tools/dirty8_est.py', str(rom), str(lst), str(edd), xy, str(ticks)]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    m = re.search(r'потолок выигрыша.*?:\s*([\d.]+)\s*т/тик\s*\(([\d.]+)%', out)
    r = re.search(r'покрытие.*?=\s*([\d.]+)%', out)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(r.group(1)) if r else None

def proj(frames, d8_t):
    saved = d8_t / FRAME + MUSIC_FR
    f2 = max(5.0, frames - saved)
    return f2, min(10.0, 50.0 / f2), saved

print(f'snap {SNAP}; MUSIC −{MUSIC_FR:.2f} кадра/тик (−{MUSIC_T:.0f} т); dirty8 = потолок',
      flush=True)
print(f'{"комната":16s} {"режим":6s} {"сейчас":>14s} {"dirty8":>10s} {"+музыка":>14s} {"Δ тик/с":>8s}',
      flush=True)

slow = []
for lv, xy, name in SCENES:
    if not (SNAP / f'l{lv}.rom').exists():
        print(f'  ур.{lv} ({xy}) {name}: нет snap — пропуск', flush=True)
        continue
    print(f'# ур.{lv} ({xy}) {name} …', flush=True)
    m = measure(lv, xy)
    if not m or 'err' in m:
        print(f'  ур.{lv} ({xy}) {name}: measure FAIL {(m or {}).get("err","")[:120]}', flush=True)
        continue
    d = dirty8(lv, xy)
    if not d:
        print(f'  ур.{lv} ({xy}) {name}: dirty8 FAIL', flush=True)
        continue
    d8_t, d8_pct, cover = d
    label = f'{lv}:({xy}) {name}'
    for mode in ('none', 'right'):
        if mode not in m:
            continue
        fr, tps = m[mode]
        if tps >= 10.0 - 1e-6:
            continue
        fr2, tps2, saved = proj(fr, d8_t)
        slow.append((label, mode, fr, tps, d8_t, cover, fr2, tps2, saved))
        print(f'{label:16s} {mode:6s} {fr:5.2f}к/{tps:4.1f}т/с  '
              f'{d8_t/1000:5.1f}Кт  {fr2:5.2f}к/{tps2:4.1f}т/с  {tps2-tps:+6.1f}',
              flush=True)

print()
print('Сводка (только <10 тик/с сейчас):')
print(f'| комната | режим | сейчас кадр/тик | тик/с | dirty8 | покрытие | после кадр/тик | тик/с |')
print(f'|---|---|---:|---:|---:|---:|---:|---:|')
for label, mode, fr, tps, d8_t, cover, fr2, tps2, saved in slow:
    print(f'| {label} | {mode} | {fr:.2f} | {tps:.1f} | {d8_t/1000:.0f}К т '
          f'({cover:.0f}%) | {cover:.0f}% | {fr2:.2f} | {tps2:.1f} |')
if not slow:
    print('(нет комнат <10 тик/с среди прогнанных)')
print()
print('Оговорки: dirty8 и музыка — потолки; память под psgpack не влезает; '
      'пул под 8×8 не переделан. Ур.5/8 (голем/демон) в этом snap нет.')
