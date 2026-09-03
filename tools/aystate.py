#!/usr/bin/env python3
"""Оракул звука по СОСТОЯНИЮ: сравнить два дампа tools/aydump.py --out не как потоки записей, а как
состояние регистров AY в конце каждого вызова плеера. Нужен, когда плеер пропускает записи, не
меняющие регистр: звук тот же, поток другой. R13 — исключение: каждая запись перезапускает
огибающую, поэтому её записи сравниваются как поток (число, порядок, значения).
  python3 tools/aystate.py <дамп A> <дамп B>"""
import sys, collections
def load(path):
    calls = collections.defaultdict(list)
    for line in open(path):
        c, r, v = (int(x) for x in line.split()); calls[c].append((r, v))
    return calls
def fold(calls, ncalls):
    """Состояние после КАЖДОГО номера вызова (и без записей тоже — иначе пропуски сдвигают индексы)."""
    state = [None]*14; out = []; r13 = []
    for c in range(ncalls + 1):
        for r, v in calls.get(c, ()):
            if r == 13: r13.append((c, v))
            elif r < 13: state[r] = v
        out.append((c, tuple(state[:13])))
    return out, r13
LA, LB = (load(p) for p in sys.argv[1:3]); n = max(max(LA), max(LB))
A, B = fold(LA, n), fold(LB, n)
bad = [(a, b) for a, b in zip(A[0], B[0]) if a != b]
print(f'вызовов {len(A[0])}/{len(B[0])}; состояний R0..R12 разошлось: {len(bad)}; R13 потоки {"совпали" if A[1]==B[1] else "РАЗОШЛИСЬ"} ({len(A[1])}/{len(B[1])} записей)')
for a, b in bad[:5]: print('  вызов', a[0], 'A', a[1], 'B', b[1])
sys.exit(0 if not bad and A[1]==B[1] and len(A[0])==len(B[0]) else 1)
