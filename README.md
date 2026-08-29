# The Sword of Ianna → Вектор-06Ц

Порт движка MSX2-версии (RetroWorks, исходники github.com/fjpena/sword-of-ianna-msx2) на Вектор-06Ц.
Логика игры переводится из Z80-исходника автоматически (`tools/z80to8080.py`), платформенный слой
(`src/vec/`) написан заново. Разбор архитектуры — `ANALYSIS.md`.

## Сборка
- `./build.sh` — эталонная MSX2-сборка (pasmo/apultra), `build/msx2/ianna.rom`
- `python3 tools/data/build_edd.py` — образ квазидиска `build/ianna.edd` (тайлы, спрайты, карта уровня 1)
- `python3 tools/build_vec.py` — ROM Вектора `build/ianna.rom` (zasm `--8080` = гейт «только i8080»)
- `python3 tools/run_vec.py <кадров> [right:60,left:40] [out.png]` — headless-прогон + PNG

## Запуск в браузере
`cp build/ianna.rom ~/projects/vector06js/sword.rom; cp build/ianna.edd ~/projects/vector06js/sword.edd`
→ http://localhost:8000/?sword.rom&edd=sword.edd (имя НЕ должно начинаться с `i` — префикс режима).
Клавиши: стрелки, Z/пробел — удар, X — действие.
