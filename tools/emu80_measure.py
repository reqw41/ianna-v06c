#!/usr/bin/env python3
"""Замер частоты ISR в Emu80 при беге героя (диагностика потери кадровых прерываний).
Запускает tools/emu80_run.sh, ждёт сообщение, нажимает Z, зажимает «вправо»/«влево» и
сравнивает прирост FrameCounter с приростом cpu_ticks (Emu80 считает их на 3.125 МГц:
62592 тактов/кадр -> 50.0 Гц норма). Выборка под debug_break, чтобы пара (ticks, счётчики)
была согласованной. Заодно печатает счётчик halt бюджета DI (vec_bud_halts).
Адреса ячеек — из build/ianna_vec.lst (FrameCounter, vec_bud_halts).
  python3 tools/emu80_measure.py [--norestart]
"""
import json, re, subprocess, sys, time, urllib.request
PORT = 19783
def sym(name):
    for line in open("build/ianna_vec.lst", encoding="utf-8", errors="replace"):
        m = re.match(r"([0-9A-F]{4}):.*\b" + name + r":", line)
        if m: return int(m.group(1), 16)
    raise SystemExit("нет символа " + name)
FC, HALTS = sym("FrameCounter"), sym("vec_bud_halts")
def mcp(tool, args=None):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": tool, "arguments": args or {}}}).encode()
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}/mcp", req,
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    d = urllib.request.urlopen(r, timeout=8).read().decode()
    return json.loads(d[d.find('{'):])["result"]["content"][0]["text"]
def rd16(addr):
    h = json.loads(mcp("mem_read", {"addr": addr, "len": 2}))["hex"]
    return int(h[0:2], 16) | (int(h[2:4], 16) << 8)
def sample():
    mcp("debug_break")
    r = (json.loads(mcp("cpu_state"))["cpu_ticks"], rd16(FC), rd16(HALTS))
    mcp("emu_run")
    return r
def run(label, keys, secs):
    if keys: mcp("kbd_send", {"action": "down", "keys": keys})
    t0, f0, h0 = sample(); time.sleep(secs); t1, f1, h1 = sample()
    if keys: mcp("kbd_send", {"action": "up", "keys": keys})
    dt = (t1 - t0) / 3.125e6; df = (f1 - f0) & 0xFFFF; dh = (h1 - h0) & 0xFFFF
    print(f"{label}: {dt:.2f} с, ISR {df} -> {df/dt:.1f} Гц, halt бюджета {dh} ({dh/dt:.1f}/с)")
if __name__ == "__main__":
    if "--norestart" not in sys.argv:
        subprocess.run(["sh", "tools/emu80_run.sh"], check=True, capture_output=True)
        time.sleep(3); run("экран сообщения", None, 4); time.sleep(7)
        mcp("kbd_send", {"action": "down", "keys": ["z"]}); time.sleep(0.2); mcp("kbd_send", {"action": "up", "keys": ["z"]}); mcp("kbd_reset"); time.sleep(1.5)  # press с duration оставлял Z зажатой
    run("стоя", None, 4)
    run("бег вправо", ["right"], 6)
    run("бег влево", ["left"], 6)
