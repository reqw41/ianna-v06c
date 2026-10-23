# Утилиты сборки

| файл | что это | откуда | лицензия |
|---|---|---|---|
| `sjasm` | ассемблер с ключом `--8080` (только команды i8080) | собрать из исходников sjasm и положить сюда; в git не входит | — |
| `apultra` | упаковщик в формате aPLib (наборы уровней, слайды) | [emmanuel-marty/apultra](https://github.com/emmanuel-marty/apultra) v1.4.8, сборка для macOS arm64 | zlib |
| `apack` | обёртка `apack in out` → `apultra` (имя, которое ждёт Makefile оригинала) | этот репозиторий | Apache 2.0 |
| `fill16k` | добивка образа до 16 КБ для эталонной MSX2-сборки (`build.sh`) | `tools/` оригинала [fjpena/sword-of-ianna-msx2](https://github.com/fjpena/sword-of-ianna-msx2) | Apache 2.0 |
| `pasmo` | ассемблер Z80: эталонная MSX2-сборка и сверка плеера (`tests/music`) | [pasmo.speccy.org](http://pasmo.speccy.org/); в git не входит, собрать и положить сюда | GPL |

`apultra` и `fill16k` собраны под macOS arm64. На другой системе соберите их из исходников и положите
сюда под теми же именами.
