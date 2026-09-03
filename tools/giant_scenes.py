#!/usr/bin/env python3
"""Сцены с «великанами» (враги из двух банков-половин: голем, огр, минотавр, демон).

Читает карты уровней (ref/msx2/src/levelN.map), распаковывает экраны и смотрит блок объектов
экрана (CURRENT_SCREEN_OBJECTS = смещение 360 в распакованном экране):
  [0] скрипт игрока, далее по 6 Б: враг 1, враг 2, объекты 1..5 — (id, тип, X стайл, Y стайл, ...).
Типы врагов: 20 скелет .. 27 голем, 28 огр, 29 минотавр, 30 демон, 31 «вторичный» (вторая
половина великана — занимает слот врага 2).

  python3 tools/giant_scenes.py [уровень ...]
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/data'))
from level_tools import parse_level
from aplib import depack

GIANT = {27: 'голем', 28: 'огр', 29: 'минотавр', 30: 'демон'}
SRC = pathlib.Path(__file__).resolve().parents[1] / 'ref/msx2/src'


def scan(lv):
    f = SRC / f'level{lv}.map'
    if not f.exists():
        return None
    info = parse_level(list(f.read_bytes()))
    w = info['w']
    out = []
    for i, sc in enumerate(info['screens']):
        dec, _ = depack(sc, 0)
        if len(dec) < 373:
            continue
        o = dec[360:403]
        slots = [(1, o[1], o[2], o[3], o[4])]
        if o[2] != 31:                     # «вторичный» враг занимает и второй слот
            slots.append((2, o[7], o[8], o[9], o[10]))
        for k, oid, t, ex, ey in slots:
            if t in GIANT:
                out.append((i, i % w, i // w, GIANT[t], k, ex, ey))
    return info, out


def main():
    lvs = [int(a) for a in sys.argv[1:]] or list(range(1, 10))
    for lv in lvs:
        r = scan(lv)
        if not r:
            continue
        info, found = r
        print(f'уровень {lv} ({info["w"]}x{info["h"]}, экранов {info["n"]}): '
              f'{len(found)} сцен с великанами')
        for i, x, y, nm, k, ex, ey in found:
            print(f'  экран {i:2d} = ({x},{y})  враг{k} {nm}  стайл ({ex},{ey})')


if __name__ == '__main__':
    main()
