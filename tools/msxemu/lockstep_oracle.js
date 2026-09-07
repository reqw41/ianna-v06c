// lockstep_oracle.js — сторона ОРИГИНАЛА (MSX2, headless WebMSX) для локстеп-сверки с портом.
// Исполняет тот же сценарий клавиш, что tools/lockstep.py, и на каждом игровом тике пишет
// нормализованное состояние (спрайты, сущности, player_dead, current_levelx/y) в JSON.
//
//   node tools/msxemu/lockstep_oracle.js --level=2 --route=none:30,left:40 [--start=5,6]
//        [--hero=96,112] [--settle=10] --out=/путь/msx.json
//
// Как ловится тик. WebMSX headless умеет шагать только целыми кадрами, а тик игры — это
// mainloop: RunScripts -> CheckGravities -> RedrawScreen_part1 -> waitforVBlank(5 кадров) ->
// RedrawScreen_part2. Снимать состояние «в конце кадра» нельзя ни по какому признаку:
//  - сброс frames_noredraw стоит в КОНЦЕ тика, и в том же кадре обычно успевает начаться
//    RunScripts следующего — привязка плавает на тик от скорости кода;
//  - «первый halt за RunScripts» тоже не годится: на тике смены экрана ChangeScreen
//    перерисовывает экран дольше пяти кадров, frames_noredraw успевает дорасти до frames_lock,
//    и waitforVBlank уходит в vblank_done БЕЗ ЕДИНОГО halt — тик пропускается целиком.
// Поэтому снимок делается ВНУТРИ машины: в копии ROM единственный `call RunScripts` в mainloop
// подменён на переход в подпрограмму, дописанную в свободное ОЗУ (SNAPCODE). Она инкрементирует
// счётчик тиков TICKC и копирует SPDATA+ENTITY_DATA (224 Б, ровно как SaveCheckpoint) и блок
// игровых переменных в буфер SNAP, после чего уходит в RunScripts. Точка снимка — вход в
// RunScripts, ровно та же, что `cpu.pc == RunScripts` на порте; когда именно JS заметит смену
// TICKC, на содержимое снимка уже не влияет.
//
// Та же копия ROM патчит `random`: в оригинале это `ld a,r` (недетерминированно и невоспроизводимо
// на i8080), заменяется на A := randData += $4D — точно тот же патч, что --norand на порте.
// В момент синхронизации randData := 0 на обеих сторонах, дальше последовательности совпадают.
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '../..');
const M = require(path.join(ROOT, 'tools/msxemu/emu_ianna.js'));

// --- адреса MSX (build/msx2/ianna.sym, сборка из ref/msx2/src совпадает с релизным ROM по коду)
const A = {
  RunScripts: 0x443B, ChangeScreen: 0x4250, random: 0x4563,
  wait_till_read_loop: 0x7862, waitloop: 0x7B30,
  SPDATA: 0xEA0E, ENTITY_DATA: 0xEA8E,
  joystick_state: 0xEC48, level_width: 0xEC4C, frames_noredraw: 0xEC59, global_timer: 0xEC5F,
  current_levelx: 0xEC6F, current_levely: 0xEC70, player_dead: 0xEC71,
  current_level: 0xEC7A, screen_changed: 0xEC7C, randData: 0xEC85,
  intro_var: 0xECD4, number_screens: 0xECD5,
  VARS: 0xEC48,         // joystick_state.. — блок игровых переменных, копируется в снимок целиком
  VARSLEN: 72,          // по randData включительно
  TICKC: 0xECE0,        // свободное ОЗУ сразу за END_VARS ($ECDD); стек MSX живёт много выше
  SNAPCODE: 0xED00,     // подпрограмма снимка, дописывается в ОЗУ из JS
  SNAP: 0xED40,         // буфер снимка: 224 Б SPDATA+ENTITY_DATA, затем VARSLEN переменных
  HOOK: 0x456C,         // хвост тела random, освободившийся после патча ГПСЧ (9 Б)
};

function arg(name, def) {
  const p = process.argv.find(a => a.startsWith('--' + name + '='));
  return p === undefined ? def : p.slice(name.length + 3);
}
const LEVEL = parseInt(arg('level', '1'), 10);
const START = arg('start', null) ? arg('start').split(',').map(Number) : null;
const HERO = arg('hero', null) ? arg('hero').split(',').map(Number) : null;
const ROUTE = arg('route', 'none:30');
const SETTLE = parseInt(arg('settle', '10'), 10);
const OUT = arg('out', path.join(ROOT, 'build/lockstep_msx.json'));

// Маршрут "none:30,right:40,fire+right:30" -> массив множеств клавиш по тикам.
function parseRoute(r) {
  const out = [];
  for (const seg of r.split(',')) {
    const [k, n] = seg.split(':');
    const keys = k.split('+').filter(x => x !== 'none' && x !== '');
    for (let i = 0; i < parseInt(n, 10); i++) out.push(keys);
  }
  return out;
}
const PLAN = parseRoute(ROUTE);

// --- патченная копия ROM: детерминированный ГПСЧ + крючок счёта тиков
function makeRom() {
  const src = path.join(ROOT, 'ref/msx2_rom/ianna.rom');
  const rom = Buffer.from(fs.readFileSync(src));
  const off = a => a - 0x4000;                     // банк 0 лежит в начале файла, окно $4000..$7FFF
  const rd = A.randData;
  // random: ld a,(randData) / add a,$4D / ld (randData),a / ret  — тот же алгоритм, что --norand порта
  const rnd = [0x3A, rd & 0xFF, rd >> 8, 0xC6, 0x4D, 0x32, rd & 0xFF, rd >> 8, 0xC9];
  for (let i = 0; i < rnd.length; i++) rom[off(A.random) + i] = rnd[i];
  // крючок: jp SNAPCODE (сама подпрограмма — в ОЗУ, её кладёт installSnap до старта игры)
  const hook = [0xC3, A.SNAPCODE & 0xFF, A.SNAPCODE >> 8];
  for (let i = 0; i < hook.length; i++) rom[off(A.HOOK) + i] = hook[i];
  // единственный `call RunScripts` (в mainloop) -> call крючка
  const call = [0xCD, A.RunScripts & 0xFF, A.RunScripts >> 8];
  let found = [];
  for (let a = 0; a < 0x4000; a++)
    if (rom[a] === call[0] && rom[a + 1] === call[1] && rom[a + 2] === call[2]) found.push(a);
  if (found.length !== 1) throw new Error('ожидался ровно один call RunScripts, найдено ' + found.length);
  rom[found[0] + 1] = A.HOOK & 0xFF; rom[found[0] + 2] = A.HOOK >> 8;
  const dst = path.join(ROOT, 'build/ianna_lockstep.rom');
  fs.writeFileSync(dst, rom);
  return dst;
}

const e = new M();
e.loadCartridge(makeRom());

// Подпрограмма снимка — в ОЗУ (в ROM-банке 0 свободного места нет). Кладём сразу после включения:
// mainloop, из которого её зовут, запускается много позже — после меню, вступления и LoadLevel.
function installSnap() {
  const lo = a => a & 0xFF, hi = a => a >> 8;
  const code = [
    0xF5, 0xE5, 0xD5, 0xC5,                                   // push af,hl,de,bc
    0x21, lo(A.TICKC), hi(A.TICKC), 0x34,                     // ld hl,TICKC : inc (hl)
    0x21, lo(A.SPDATA), hi(A.SPDATA),                         // ld hl,SPDATA
    0x11, lo(A.SNAP), hi(A.SNAP),                             // ld de,SNAP
    0x01, 224, 0, 0xED, 0xB0,                                 // ld bc,224 : ldir
    0x21, lo(A.VARS), hi(A.VARS),                             // ld hl,joystick_state
    0x11, lo(A.SNAP + 224), hi(A.SNAP + 224),                 // ld de,SNAP+224
    0x01, A.VARSLEN, 0, 0xED, 0xB0,                           // ld bc,VARSLEN : ldir
    0xC1, 0xD1, 0xE1, 0xF1,                                   // pop bc,de,hl,af
    0xC3, lo(A.RunScripts), hi(A.RunScripts),                 // jp RunScripts
  ];
  for (let i = 0; i < code.length; i++) e.writeMem(A.SNAPCODE + i, code[i]);
  if (A.SNAPCODE + code.length > A.SNAP) throw new Error('SNAPCODE наехал на буфер');
}
installSnap();
const kb = e.W.room.keyboard;
const MK = { fire: 'Z', action: 'X', left: 'LEFT', right: 'RIGHT', up: 'UP', down: 'DOWN' };
let held = new Set();
function setKeys(k) {
  const want = new Set(k);
  for (const n of held) if (!want.has(n)) kb.processMSXKey(MK[n], false);
  for (const n of want) if (!held.has(n)) kb.processMSXKey(MK[n], true);
  held = want;
}
const cpu = e.m.cpu;
const pc = () => cpu.saveState().PC & 0xffff;
const rb = a => e.readMem(a, 1)[0];
const inWait = () => { const p = pc(); return p >= A.wait_till_read_loop && p < A.wait_till_read_loop + 8; };
function forceRet() {
  const st = cpu.saveState(); const sp = st.SP & 0xffff; const bus = e.m.bus;
  const ra = bus.read(sp) | (bus.read(sp + 1) << 8);
  st.PC = ra; st.SP = (sp + 2) & 0xffff; cpu.loadState(st); return ra;
}
function injectCall(addr, regs) {
  const st = cpu.saveState(); const bus = e.m.bus; const sp = (st.SP - 2) & 0xffff;
  bus.write(sp, st.PC & 0xff); bus.write((sp + 1) & 0xffff, (st.PC >> 8) & 0xff);
  st.SP = sp; st.PC = addr; st.Tn = 0; st.ai = false; st.p = 0;
  Object.assign(st, regs); cpu.loadState(st);
}

// --- пропуск титула и вступления
e.runFrames(60);
let got = false;
for (let i = 0; i < 8 && !got; i++) {
  setKeys(['fire']); e.runFrames(12); setKeys([]);
  for (let f = 0; f < 150 && !got; f++) { e.runFrames(1); const p = pc(); if (p >= A.waitloop && p < A.waitloop + 16) got = true; }
}
if (!got) { console.error('интро не поймано'); process.exit(1); }
e.writeMem(A.intro_var, rb(A.number_screens) - 1); forceRet();
e.writeMem(A.current_level, LEVEL - 1);   // до LoadLevel в begin_level
e.runFrames(300);

// --- снять сообщение стартового экрана (то же делает rv.Warmup на порте)
function dismiss(maxTries) {
  for (let k = 0; k < (maxTries || 16); k++) {
    if (!inWait()) break;
    setKeys(['fire']); e.runFrames(10); setKeys([]); e.runFrames(10);
  }
}
dismiss();
e.runFrames(60); dismiss();

// --- при --start: перейти на нужный экран инъекцией ChangeScreen
if (START) {
  const w = rb(A.level_width);
  e.writeMem(A.current_levelx, START[0]); e.writeMem(A.current_levely, START[1]);
  injectCall(A.ChangeScreen, { A: (START[1] * w + START[0]) & 0xff });
  e.runFrames(40); dismiss(); e.runFrames(12); dismiss();
}
if (HERO) { e.writeMem(A.SPDATA + 3, HERO[0]); e.writeMem(A.SPDATA + 4, HERO[1]); }

// --- точка синхронизации: обнулить ГПСЧ и счётчик тиков
e.writeMem(A.randData, 0); e.writeMem(A.randData + 1, 0);
e.writeMem(A.TICKC, 0);

// --- тик = изменение TICKC (крючок перед RunScripts). Сообщения снимаются «огнём» и на порте тоже.
let dismissedAt = [];
let tno = -1;
function tick(scenKeys) {
  const c0 = rb(A.TICKC);
  for (let f = 0; f < 1200; f++) {
    e.runFrames(1);
    if (rb(A.TICKC) !== c0) return true;   // снимок уже лежит в SNAP, снятый на входе в RunScripts
    if (inWait()) {                       // сообщение/«нажми огонь»: держим огонь, как rv.Warmup
      dismissedAt.push(tno + 1);
      setKeys(['fire']); e.runFrames(10); setKeys([]); e.runFrames(10);
      setKeys(scenKeys);
    }
  }
  return false;
}
function snap(t, keys) {
  const buf = e.readMem(A.SNAP, 224 + A.VARSLEN);
  const sp = buf.slice(0, 128), en = buf.slice(128, 224);
  const gv = a => buf[224 + (a - A.VARS)];
  const spr = [], ent = [];
  for (let i = 0; i < 16; i++) {
    const r = sp.slice(i * 8, i * 8 + 8); const a = r[0] | (r[1] << 8);
    spr.push(a === 0 ? null : [r[2] & 0x7f, Math.floor((a - 0x8000) / 384), r[3], r[4], (r[2] >> 7) & 1]);
  }
  for (let i = 0; i < 8; i++) {
    const r = en.slice(i * 12, i * 12 + 12); const p = r[0] | (r[1] << 8);
    const idx = (p >= A.SPDATA && p < A.SPDATA + 128) ? (p - A.SPDATA) / 8 : -1;
    ent.push(p === 0 ? null : [idx].concat(r.slice(2, 12)));
  }
  return { t, keys, spr, ent, pd: gv(A.player_dead), lx: gv(A.current_levelx), ly: gv(A.current_levely),
           gt: gv(A.global_timer) };
}

setKeys([]);
for (let i = 0; i < SETTLE; i++) if (!tick([])) { console.error('тик не пришёл (settle)'); process.exit(1); }
const ticks = [];
for (let k = 0; k < PLAN.length; k++) {
  setKeys(PLAN[k]);
  tno = k;
  if (!tick(PLAN[k])) { console.error('тик не пришёл на', k); break; }
  ticks.push(snap(k, PLAN[k]));
}
setKeys([]);
fs.writeFileSync(OUT, JSON.stringify({ side: 'msx', level: LEVEL, start: START, route: ROUTE, settle: SETTLE,
                                       dismissed: dismissedAt, ticks }, null, 0));
console.error('msx: тиков', ticks.length, 'снятых сообщений', dismissedAt.length);
