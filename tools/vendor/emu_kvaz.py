#!/usr/bin/env python3
"""I8080 + КВАЗИДИСК (порт $10) — надстройка над emu8080 из knightmare-v06c.

Раскладка байта порта $10 (по vector06js src/memory.js control_write):
  б0-1 = страница для ОКОН, б2-3 = страница для СТЕКА, б4 = режим стека,
  б5 = окно $A000-$DFFF, б6 = окно $8000-$9FFF, б7 = окно $E000-$FFFF
Стековый доступ (push/pop/call/ret) достаёт ВСЕ 64К выбранной страницы,
окна — только $8000-$FFFF. Итого 4 страницы = 256К.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emu8080 import I8080


class I8080Kvaz(I8080):
    def __init__(self):
        super().__init__()
        self.kvaz = bytearray(4 * 65536)   # 4 страницы по 64К
        self.kv_cw = 0
        self._kv_apply(0)

    def _kv_apply(self, w8):
        self.kv_cw = w8
        self.kv_stack_mode = (w8 & 0x10) != 0
        self.kv_map_mode = w8 & 0xE0
        self.kv_page_map = (w8 & 3) * 65536
        self.kv_page_stack = ((w8 & 0x0C) >> 2) * 65536

    def kv_out(self, port, val):
        """Вызывать из out_handler основного скрипта при port==0x10."""
        self._kv_apply(val)

    def _kv_addr(self, a, stackrq=False):
        """-> (это_квазидиск, смещение)"""
        if self.kv_stack_mode and stackrq:
            return True, self.kv_page_stack + a
        m = self.kv_map_mode
        if m:
            if (m & 0x20) and 0xA000 <= a <= 0xDFFF:
                return True, self.kv_page_map + a
            if (m & 0x40) and 0x8000 <= a <= 0x9FFF:
                return True, self.kv_page_map + a
            if (m & 0x80) and 0xE000 <= a <= 0xFFFF:
                return True, self.kv_page_map + a
        return False, a

    # --- обычный доступ (ld a,(nn), ld (hl),a и т.д.) ---
    def rb(self, a):
        a &= 0xFFFF
        kv, off = self._kv_addr(a)
        return self.kvaz[off] if kv else self.mem[a]

    def wb(self, a, v):
        a &= 0xFFFF
        kv, off = self._kv_addr(a)
        if kv:
            self.kvaz[off] = v & 0xFF
        else:
            self.mem[a] = v & 0xFF

    # --- фетч кода: тоже через окно! ---
    # Базовый fetch читает self.mem напрямую, и код, лежащий в окне
    # квазидиска, не исполнялся бы вовсе (процессор полз бы nop-ами по нулям).
    # На железе M1-чтение — обычное чтение памяти и проходит через маппинг.
    def fetch(self):
        op = self.rb(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return op

    # --- стековый доступ (push/pop/call/ret) ---
    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self._swb(self.sp, (v >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self._swb(self.sp, v & 0xFF)

    def pop(self):
        lo = self._srb(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        hi = self._srb(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        return lo | (hi << 8)

    def _srb(self, a):
        a &= 0xFFFF
        kv, off = self._kv_addr(a, stackrq=True)
        return self.kvaz[off] if kv else self.mem[a]

    def _swb(self, a, v):
        a &= 0xFFFF
        kv, off = self._kv_addr(a, stackrq=True)
        if kv:
            self.kvaz[off] = v & 0xFF
        else:
            self.mem[a] = v & 0xFF

    def load_edd(self, path):
        """Залить образ квазидиска (.edd, до 256К)."""
        data = pathlib.Path(path).read_bytes()
        self.kvaz[:len(data)] = data
        return len(data)


def main():
    """Прогон тест-ROM разведки: печатает вердикт по каждому тесту."""
    import re
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'build/kvaztest.rom'
    lst_path = sys.argv[2] if len(sys.argv) > 2 else 'build/kvaztest.lst'
    cpu = I8080Kvaz()
    data = pathlib.Path(rom_path).read_bytes()
    cpu.mem[0x100:0x100+len(data)] = data
    cpu.pc = 0x100
    cpu.out_handler = lambda p, v: cpu.kv_out(p, v) if p == 0x10 else None
    cpu.in_handler = lambda p: 0xFF if p in (2, 0x0E) else 0

    # адрес results из листинга
    sym = {}
    for line in pathlib.Path(lst_path).read_text(errors='replace').splitlines():
        m = re.match(r'^(\w+)\s+=\s+\$([0-9A-Fa-f]{4})', line)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)

    for _ in range(2_000_000):
        cpu.step()
        if cpu.pc == sym.get('hang', -1):
            break
    names = ['T0 окно A000: изоляция от VRAM', 'T1 окно A000: чтение назад',
             'T2 четыре страницы независимы', 'T3 окно 8000-9FFF',
             'T4 окно E000-FFFF', 'T5 СТЕК: нижняя половина страницы',
             'T6 страница стека != страницы окна', 'T7 объём 4x64K = 256K']
    res = sym['results']
    ok = True
    for i, n in enumerate(names):
        v = cpu.mem[res + i]
        print(f'{"ПРОШЁЛ" if v else "ПРОВАЛ"}  {n}')
        ok &= bool(v)
    print('ИТОГ:', 'все тесты прошли' if ok else 'ЕСТЬ ПРОВАЛЫ')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
