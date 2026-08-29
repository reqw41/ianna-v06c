#!/bin/sh
# Запуск Ianna в Emu80 (Вектор-06Ц, ядро i8080).
#   tools/emu80_run.sh          — квазидисковая сборка: build/ianna.rom + build/ianna.edd
#   tools/emu80_run.sh --demo   — одиночный ROM build/ianna_demo.rom
# Образ квазидиска подаётся через --post-conf (ramDisk.fileName): штатный --edd на Векторе
# не работает (свойство ставится объекту vector.edd, а в конфиге он ramDisk).
# MCP-сервер экземпляра — порт 19783 (EMU80_MCP_PORT), чтобы не делить 19781 с чужими.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP=~/projects/emu80v4/Emu80qt-mcp.app/Contents/MacOS
TMP="${TMPDIR:-/tmp}/ianna_emu80"; mkdir -p "$TMP"
pkill -f "Emu80qt-mcp.*ianna" 2>/dev/null || true
if [ "$1" = "--demo" ]; then
  cp "$ROOT/build/ianna_demo.rom" "$TMP/ianna_demo.rom"
  ARGS="--run $TMP/ianna_demo.rom"
else
  cp "$ROOT/build/ianna.rom" "$TMP/ianna.rom"; cp "$ROOT/build/ianna.edd" "$TMP/ianna.edd"
  printf 'ramDisk.fileName = "%s"\n' "$TMP/ianna.edd" > "$TMP/ianna_post.conf"
  ARGS="--post-conf $TMP/ianna_post.conf --run $TMP/ianna.rom"
fi
cd "$APP"
QT_PLUGIN_PATH=/opt/homebrew/share/qt/plugins EMU80_MCP_PORT=19783 nohup ./Emu80qt-mcp --platform vector $ARGS >"$TMP/emu80.log" 2>&1 &
echo "Emu80 запущен: $ARGS (MCP порт 19783). Старт уровня: подождать сообщение, Z/пробел, стрелки."
