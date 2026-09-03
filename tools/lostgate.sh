#!/bin/sh
# Потерянные прерывания по шести сценам: tools/lostgate.sh <каталог со сборками>
R="$(cd "$(dirname "$0")/.." && pwd)"
D="$1"
for S in 1:4,5 2:4,6 3:1,0 3:1,2 4:6,2 6:6,1; do
  L="${S%%:*}"; XY="${S#*:}"
  echo "ур.$L $XY:"
  IANNA_EDD="$D/l$L.edd" python3 "$R/tools/measure_vec.py" "$D/l$L.rom" "$D/l$L.lst" --start="$XY" --fixrand --frames=600 2>&1 | grep -E 'потеряно прерываний|потери по функциям'
done
