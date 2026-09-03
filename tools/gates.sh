#!/bin/sh
# Гейт-стенд: собрать наборы 6 сцен и снять хэши/такты.
#   tools/gates.sh snap <каталог>     — собрать ROM+EDD по уровням 1,2,3,4,6 и сложить в каталог
#   tools/gates.sh cmp  <каталог>     — cmpbuild --norand 60 тиков по шести сценам из каталога
#   tools/gates.sh cyc  <каталог>     — abcyc: такты на тик по шести сценам
#   tools/gates.sh pool <каталог>     — poolstat: палитра, максимум слотов, пути блита
set -e
R="$(cd "$(dirname "$0")/.." && pwd)"
LEVELS="1 2 3 4 6"
SCENES="1:4,5 2:4,6 3:1,0 3:1,2 4:6,2 6:6,1"
case "$1" in
snap)
  D="$2"; mkdir -p "$D"
  for L in $LEVELS; do
    python3 "$R/tools/data/build_edd.py" --level=$L >/dev/null
    python3 "$R/tools/build_vec.py" >/dev/null
    cp "$R/build/ianna.rom" "$D/l$L.rom"; cp "$R/build/ianna_vec.lst" "$D/l$L.lst"; cp "$R/build/ianna.edd" "$D/l$L.edd"
  done ;;
cmp|cyc|pool)
  D="$2"
  SC="${3:-$SCENES}"
  for S in $SC; do
    L="${S%%:*}"; XY="${S#*:}"
    printf '  ур.%s %-4s ' "$L" "$XY"
    if [ "$1" = cmp ]; then
      python3 "$R/tools/cmpbuild.py" "$D/l$L.rom" "$D/l$L.lst" "$D/l$L.edd" "$XY" 60 --norand
    elif [ "$1" = pool ]; then
      python3 "$R/tools/poolstat.py" "$D/l$L.rom" "$D/l$L.lst" "$D/l$L.edd" "$XY" 60
    else
      python3 "$R/tools/abcyc.py" "$D/l$L.rom" "$D/l$L.lst" "$D/l$L.edd" "$XY" 60
    fi
  done ;;
esac
