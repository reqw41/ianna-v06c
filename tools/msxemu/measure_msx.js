// measure_msx.js — скорость ОРИГИНАЛА (MSX2, headless WebMSX) по сценам: кадров на тик стоя / ходьба / бой.
// Тот же крючок перед RunScripts, что в lockstep_oracle.js (счётчик тиков TICKC в патченной копии ROM),
// герой неуязвим (здоровье возвращается каждый кадр), сценарии клавиш по тикам — как FIGHT/pace у
// tools/measure_vec.py. Тики с сообщением («нажми огонь») в среднее не входят.
//   node tools/msxemu/measure_msx.js --level=<индекс current_level> [--start=x,y] [--hero=px,py]
//        [--ticks=40,48,60] [--settle=10]            -> JSON в stdout
const fs = require('fs'); const path = require('path');
const ROOT = path.resolve(__dirname, '../..');
const M = require(path.join(ROOT, 'tools/msxemu/emu_ianna.js'));
const A = { RunScripts: 0x443B, random: 0x4563, wait_till_read_loop: 0x7862, waitloop: 0x7B30,
  SPDATA: 0xEA0E, EPP: 0xEA8E, frames_lock: 0xEB5E, current_levelx: 0xEC6F, current_levely: 0xEC70,
  current_level: 0xEC7A, randData: 0xEC85, intro_var: 0xECD4, number_screens: 0xECD5, SaveCheckpoint: 0x427E,
  TICKC: 0xECE0, STARTF: 0xECE1, STARTX: 0xECE2, STARTY: 0xECE3, SNAPCODE: 0xED00, STARTHOOK: 0xED80, HOOK: 0x456C };
function arg(n, d) { const p = process.argv.find(a => a.startsWith('--' + n + '=')); return p === undefined ? d : p.slice(n.length + 3); }
const LEVEL = parseInt(arg('level', '0'), 10);
const START = arg('start', null) ? arg('start').split(',').map(Number) : null;
const HERO = arg('hero', null) ? arg('hero').split(',').map(Number) : null;
const TICKS = arg('ticks', '40,48,60').split(',').map(Number);
const SETTLE = parseInt(arg('settle', '10'), 10);
const FIGHT = [['fire','right'],[],['fire','up'],[],['fire','down'],[],['fire','left'],[],['right'],['right'],['left'],['left'],['up'],['down']];
const PACE = [['right'],['right'],['right'],['right'],['right'],['right'],['left'],['left'],['left'],['left'],['left'],['left']];
function makeRom() {
  const rom = Buffer.from(fs.readFileSync(path.join(ROOT, 'ref/msx2_rom/ianna.rom')));
  const off = a => a - 0x4000; const rd = A.randData;
  const rnd = [0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9];
  for (let i = 0; i < rnd.length; i++) rom[off(A.random) + i] = rnd[i];
  const hook = [0xC3, A.SNAPCODE & 0xFF, A.SNAPCODE >> 8];
  for (let i = 0; i < hook.length; i++) rom[off(A.HOOK) + i] = hook[i];
  const call = [0xCD, A.RunScripts & 0xFF, A.RunScripts >> 8]; let found = [];
  for (let a = 0; a < 0x4000; a++) if (rom[a] === call[0] && rom[a + 1] === call[1] && rom[a + 2] === call[2]) found.push(a);
  if (found.length !== 1) throw new Error('call RunScripts: ' + found.length);
  rom[found[0] + 1] = A.HOOK & 0xFF; rom[found[0] + 2] = A.HOOK >> 8;
  if (START) {
    const cs = [0xCD, A.SaveCheckpoint & 0xFF, A.SaveCheckpoint >> 8]; let n = 0;
    for (let a = 0; a < 0x4000; a++) if (rom[a] === cs[0] && rom[a + 1] === cs[1] && rom[a + 2] === cs[2]) { rom[a + 1] = A.STARTHOOK & 0xFF; rom[a + 2] = A.STARTHOOK >> 8; n++; }
    if (n === 0) throw new Error('call SaveCheckpoint не найден');
  }
  const dst = path.join(ROOT, 'build/ianna_measure_msx_' + process.pid + '.rom'); fs.writeFileSync(dst, rom); return dst;
}
const e = new M(); const romPath = makeRom(); e.loadCartridge(romPath); fs.unlinkSync(romPath);
const lo = a => a & 0xFF, hi = a => a >> 8;
// крючок: только счётчик тиков (без снимка — лишние такты не нужны)
const code = [0xE5, 0x21, lo(A.TICKC), hi(A.TICKC), 0x34, 0xE1, 0xC3, lo(A.RunScripts), hi(A.RunScripts)];
for (let i = 0; i < code.length; i++) e.writeMem(A.SNAPCODE + i, code[i]);
e.writeMem(A.TICKC, 0);
const sh = [0xF5, 0x3A, lo(A.STARTF), hi(A.STARTF), 0xA7, 0x28, 0x10, 0xAF, 0x32, lo(A.STARTF), hi(A.STARTF),
  0x3A, lo(A.STARTX), hi(A.STARTX), 0x32, lo(A.current_levelx), hi(A.current_levelx),
  0x3A, lo(A.STARTY), hi(A.STARTY), 0x32, lo(A.current_levely), hi(A.current_levely), 0xF1, 0xC3, lo(A.SaveCheckpoint), hi(A.SaveCheckpoint)];
for (let i = 0; i < sh.length; i++) e.writeMem(A.STARTHOOK + i, sh[i]);
const kb = e.W.room.keyboard; const MK = { fire: 'Z', action: 'X', left: 'LEFT', right: 'RIGHT', up: 'UP', down: 'DOWN' };
let held = new Set();
function setKeys(k) { const want = new Set(k); for (const n of held) if (!want.has(n)) kb.processMSXKey(MK[n], false); for (const n of want) if (!held.has(n)) kb.processMSXKey(MK[n], true); held = want; }
const cpu = e.m.cpu; const pc = () => cpu.saveState().PC & 0xffff; const rb = a => e.readMem(a, 1)[0];
const inWait = () => { const p = pc(); return p >= A.wait_till_read_loop && p < A.wait_till_read_loop + 8; };
function forceRet() { const st = cpu.saveState(); const sp = st.SP & 0xffff; const bus = e.m.bus; const ra = bus.read(sp) | (bus.read(sp + 1) << 8); st.PC = ra; st.SP = (sp + 2) & 0xffff; cpu.loadState(st); }
e.runFrames(60); let got = false;
for (let i = 0; i < 8 && !got; i++) { setKeys(['fire']); e.runFrames(12); setKeys([]); for (let f = 0; f < 150 && !got; f++) { e.runFrames(1); const p = pc(); if (p >= A.waitloop && p < A.waitloop + 16) got = true; } }
if (!got) { console.error('интро не поймано'); process.exit(1); }
e.writeMem(A.intro_var, rb(A.number_screens) - 1); forceRet();
e.writeMem(A.current_level, LEVEL);
if (START) { e.writeMem(A.STARTF, 1); e.writeMem(A.STARTX, START[0]); e.writeMem(A.STARTY, START[1]); }
let h0 = null; let msgTicks = 0;
function tick(keys) {      // -> кадров до следующего RunScripts, отрицательное = тик с сообщением
  const c0 = rb(A.TICKC); let msg = false;
  for (let f = 1; f < 1200; f++) {
    e.runFrames(1);
    if (h0 !== null && rb(A.EPP + 4) < h0) e.writeMem(A.EPP + 4, h0);
    if (rb(A.TICKC) !== c0) { if (held.has('fire') && !keys.includes('fire')) setKeys(keys); return msg ? -f : f; }
    if (inWait() && !held.has('fire')) { msg = true; setKeys(['fire']); }
  }
  return 0;
}
setKeys([]);
for (let i = 0; i < SETTLE; i++) if (!tick([])) { console.error('тик не пришёл (прогрев)'); process.exit(1); }
h0 = rb(A.EPP + 4);
if (HERO) { e.writeMem(A.SPDATA + 3, HERO[0]); e.writeMem(A.SPDATA + 4, HERO[1]); for (let i = 0; i < 3; i++) tick([]); }
const res = { level: LEVEL, start: START, hero: HERO, frames_lock: rb(A.frames_lock), modes: {} };
const plans = { none: () => [], pace: k => PACE[k % PACE.length], fight: k => FIGHT[k % FIGHT.length] };
['none', 'pace', 'fight'].forEach((m, mi) => {
  const fr = [], hist = {}; let msgs = 0;
  for (let k = 0; k < TICKS[mi]; k++) {
    const keys = plans[m](k); setKeys(keys); const f = tick(keys);
    if (f === 0) { console.error('тик не пришёл', m, k); break; }
    if (f < 0) { msgs++; continue; }
    fr.push(f); hist[f] = (hist[f] || 0) + 1;
  }
  const mean = fr.reduce((a, b) => a + b, 0) / Math.max(fr.length, 1);
  res.modes[m] = { ticks: fr.length, msg: msgs, fpt: +mean.toFixed(2), hist, screen: rb(A.current_levelx) + ',' + rb(A.current_levely) };
});
setKeys([]);
console.log(JSON.stringify(res));
