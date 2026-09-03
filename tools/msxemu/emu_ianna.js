// emu.js — переиспользуемый headless MSX-эмулятор (WebMSX в Node) с отладкой.
// Ядро для MCP-инструментов и копания кода игр. Требует jszip@2 + tools/msxjs/wmsx.js.
const fs = require('fs');
const B = '/Users/boris/projects/knightmare-v06c/tools/msxjs'; // ядро WebMSX и стабы берём из knightmare-v06c/tools/msxjs

function setupEnv() {
  console.log = (...a) => process.stderr.write(a.join(' ') + '\n');  // WebMSX логи → stderr (stdout = JSON-RPC MCP)
  console.info = console.log; console.warn = console.log;
  require(B + '/env.js');                         // window/document/canvas-стабы
  const loc={href:"http://localhost/",origin:"http://localhost",protocol:"http:",host:"localhost",hostname:"localhost",port:"",pathname:"/",search:"",hash:""};
  global.window.location=loc; global.location=loc;
  global.setInterval=()=>0; global.clearInterval=()=>{};
  // КЛЮЧ: setTimeout выполняем СИНХРОННО — WebMSX досылает вставку картриджа через setTimeout;
  // если занулить, powerOn стартует БЕЗ картриджа и bus.read отдаёт пустой слот/BIOS, а не наш ROM.
  global.setTimeout=(f)=>{ if(typeof f==="function"){ try{f()}catch(e){} } return 0; };
  global.window.setInterval=()=>0; global.window.clearInterval=()=>{}; global.window.setTimeout=global.setTimeout;
  global.JSZip = require(B + '/../../node_modules/jszip');   // v2 API
  const se = global.document.createElement('div');
  global.document.getElementById = () => se;
  global.WMSX = { SCREEN_ELEMENT_ID:'s', screenElement:se, MACHINE:process.env.MSX_MACHINE||'MSX2E', CARTRIDGE1_FORMAT:process.env.MSX_ROM_FORMAT||'ASCII16', AUTO_POWER_ON:true };
}

class MsxEmu {
  constructor() {
    setupEnv();
    require(B + '/wmsx.js');
    this.W = global.WMSX; this.w = global.wmsx;
    this.W.start();
    this.m = this.W.room.machine;
  }
  loadCartridge(romPath) {
    const bytes = new Uint8Array(fs.readFileSync(romPath));
    this.W.fileLoader.loadFromContent(romPath.split('/').pop(), bytes, undefined, 0, true, false, process.env.MSX_ROM_FORMAT||'ASCII16'); // 7-й аргумент = формат маппера
    this.m = this.W.room.machine;
    if (this.m.powerOff) this.m.powerOff();
    this.m.powerOn();
    // BIOS мапит слот картриджа в окно $4000 не сразу: до ~300 кадров bus.read($4xxx)
    // отдаёт пустой слот/BIOS. Прогреваем, чтобы чтения ROM были корректны.
    this.runFrames(400);
    return true;
  }
  runFrames(n) { for (let i=0;i<n;i++) this.m.videoClockPulse(); }
  readMem(addr, len=1) { const o=[]; for(let i=0;i<len;i++) o.push(this.m.bus.read((addr+i)&0xffff)); return o; }
  readVram(addr, len=1) { const v=this.m.vdp; const o=[]; for(let i=0;i<len;i++){ o.push(v.getByte ? v.getByte(addr+i) : (v.vram?v.vram[addr+i]:0)); } return o; }
  readRegs() { try { return this.m.cpu.saveState(); } catch(e){ return {err:e.message}; } }
  writeMem(addr, val) { this.m.bus.write(addr & 0xffff, val & 0xff); }
  // Вызвать подпрограмму игры: выставить регистры (regs: {A,DE,HL,...}), PC=addr,
  // прогнать тактами до возврата на sentinel. Возвращает true если вернулась.
  // Вставить call addr в текущую точку игры (возврат туда, где стояли), не останавливая кадры/прерывания.
  injectCall(addr, regs = {}) {
    const cpu = this.m.cpu, bus = this.m.bus;
    const st = cpu.saveState(); const sp = (st.SP - 2) & 0xffff;
    bus.write(sp, st.PC & 0xff); bus.write((sp + 1) & 0xffff, (st.PC >> 8) & 0xff);
    st.SP = sp; st.PC = addr; st.Tn = 0; st.ai = false; st.p = 0;
    Object.assign(st, regs); cpu.loadState(st);
  }
  callSub(addr, regs = {}, { sp = 0xf000, sentinel = 0xf200, maxCyc = 8000000 } = {}) {
    const cpu = this.m.cpu, bus = this.m.bus;
    bus.write(sentinel & 0xffff, 0x76);            // HALT на sentinel: RET сюда -> PC замрёт
    const st = cpu.saveState();
    bus.write((sp - 1) & 0xffff, (sentinel >> 8) & 0xff);
    bus.write((sp - 2) & 0xffff, sentinel & 0xff);
    st.SP = (sp - 2) & 0xffff; st.PC = addr; st.IFF1 = 0; st.IFF2 = 0;
    // сброс конвейера Z80 WebMSX: иначе доисполнится уже выбранная инструкция (halt/jr) по новому PC
    st.Tn = 0; st.ai = false; st.p = 0;
    Object.assign(st, regs);
    cpu.loadState(st);
    let c = 0;
    while (c < maxCyc) {
      cpu.busClockPulses(8); c += 8;
      if ((cpu.saveState().PC & 0xffff) === sentinel) return true;
    }
    return false;
  }
  // нажать клавишу: jsKey как в DOM (например '1','ArrowRight'). Удержать hold кадров, отпустить.
  key(jsKey, hold=8) {
    const kb = this.W.room.keyboard;
    kb.processKey(jsKey, true); this.runFrames(hold); kb.processKey(jsKey, false); this.runFrames(4);
  }
  // setDir = ряд 8 матрицы (Montezuma читает readKeyboardPort(8)): UP=b0,LEFT=b4,DOWN=b5,RIGHT=b7, активный LOW.
  _ensureKbdHook() {
    if (this._kbHooked) return;
    const h = this.W.room.controllersHub;
    this._kb8 = 0xff;
    const orig = h.readKeyboardPort.bind(h);
    h.readKeyboardPort = (r) => (r === 8 ? this._kb8 : orig(r));
    this._kbHooked = true;
  }
  setDir({up=false, down=false, left=false, right=false} = {}) {
    this._ensureKbdHook();
    let b = 0xff;
    if (up) b &= ~(1<<0); if (left) b &= ~(1<<4); if (down) b &= ~(1<<5); if (right) b &= ~(1<<7);
    this._kb8 = b;
  }
  screenshot() { try { return this.m.getScreenCapture(); } catch(e){ return null; } }
}
module.exports = MsxEmu;

// самотест: node emu.js <rom>
if (require.main === module) {
  const e = new MsxEmu();
  const rom = process.argv[2] || (B+'/../../km.rom');
  e.loadCartridge(rom);
  e.runFrames(600);
  const mem = e.readMem(0xe000, 8);
  console.log("САМОТЕСТ emu.js: e000-e007 =", mem.map(b=>b.toString(16)).join(' '));
  const nz = e.readMem(0xe000,0x200).filter(b=>b!==0xff).length;
  console.log("RAM e000-e1ff не-ff байт:", nz, nz>0?"-> ИГРА РАБОТАЕТ":"-> не запустилась");
  const regs = e.readRegs();
  console.log("регистры CPU (ключи):", regs?Object.keys(regs).slice(0,12).join(','):'нет');
}
