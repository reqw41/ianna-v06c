#!/bin/sh
# Сборка MSX2-версии The Sword of Ianna из ref/msx2/src в build/msx2.
# Инструменты: tools/bin (pasmo 0.5.5 из зеркала mkoloberdin/pasmo@stable,
# apack = обёртка над apultra (формат aPLib), fill16k из репо игры).
# Отличие от релизного ref/msx2_rom/ianna.rom: только банк 40 (музыка, другой
# aPLib-упаковщик) и таблица адресов музыки в банке 0 (24 байта).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$ROOT/tools/bin:$PATH"
rm -rf "$ROOT/build/msx2"
mkdir -p "$ROOT/build"
cp -R "$ROOT/ref/msx2/src" "$ROOT/build/msx2"
cd "$ROOT/build/msx2"
make 2>&1 | grep -v '^WARNING: Var' | grep -v '^pasmo\|^fill16k\|^apack\|^dd \|^cat \|records\|bytes transferred'
ls -l ianna.rom
