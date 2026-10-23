// Оракул: удар мечом на MSX2-оригинале (headless WebMSX). node sword_oracle.js <left|right|up|down>
// Пишет VRAM в scratchpad/msx_<kind>_NN.vram по тику (6 кадров NTSC); vram2png.py <vram> <png> <page>.
// Грабли, найденные 2026-09-03:
//  - клавиши игры: Z = огонь, X = действие (пробел НЕ опрашивается), стрелки — GTSTCK;
//  - нажимать через keyboard.processMSXKey('Z'|'X'|'LEFT'|...); перехват hub.readKeyboardPort
//    (даже прозрачный) ломает опрос в меню — showmenu_waitrelease виснет;
//  - ждать только покадрово (runFrames): busClockPulses без VDP не даёт прерываний, ISR не
//    обновляет joystick_state;
//  - титул -> «JUGAR» одним нажатием; вступление пропускается: в waitloop_loop intro_var :=
//    number_screens-1 и принудительный ret; стартовый экран уровня 1 = (0,1);
//  - на старте два сообщения, каждое закрывается «огнём» (wait_till_read).
const M=require(__dirname+'/emu_ianna.js'); const fs=require('fs');
const S='/private/tmp/claude-501/-Users-boris/6043f58d-525e-4e56-9451-1177913a730d/scratchpad/';
const KIND=process.argv[2]||'left';
const e=new M(); e.loadCartridge(__dirname+'/../../ref/msx2_rom/ianna.rom');
const kb=e.W.room.keyboard; const MK={fire:'Z',action:'X',left:'LEFT',right:'RIGHT',up:'UP',down:'DOWN'}; let held=new Set();
function setKeys(k){ const want=new Set(k); for(const n of held) if(!want.has(n)) kb.processMSXKey(MK[n],false); for(const n of want) if(!held.has(n)) kb.processMSXKey(MK[n],true); held=want; }
const cpu=e.m.cpu; const pc=()=>cpu.saveState().PC&0xffff;
function runInRange(lo,hi,frames){ for(let i=0;i<frames;i++){ e.runFrames(1); const p=pc(); if(p>=lo&&p<hi) return true; } return false; }
function forceRet(){ const st=cpu.saveState(); const sp=st.SP&0xffff; const bus=e.m.bus; const ra=bus.read(sp)|(bus.read(sp+1)<<8); st.PC=ra; st.SP=(sp+2)&0xffff; cpu.loadState(st); return ra; }
e.runFrames(60);
let inWait=false;
for(let i=0;i<8&&!inWait;i++){ setKeys(['fire']); e.runFrames(12); setKeys([]); inWait=runInRange(0x7b30,0x7b40,150); console.error('нажатие',i,'PC',pc().toString(16),'waitloop',inWait); }
if(inWait){ const ns=e.m.bus.read(0xECD5); e.writeMem(0xECD4,ns-1); const ra=forceRet(); console.error('intro_var:=',ns-1,'возврат на',ra.toString(16)); }
e.runFrames(300); const started=e.readMem(0xEC6F,2);
e.runFrames(120);
console.error('старт:',started,'levelxy=',e.readMem(0xEC6F,2),'FrameCounter',e.readMem(0xEB52,2),'PC',pc().toString(16));
function dump(tag){ let page=-1; try{ const v=e.m.vdp; const regs=v.register||v.registers||(v.saveState&&v.saveState().register); if(regs) page=(regs[2]>>5)&1; }catch(x){} const n=0x10000; const buf=Buffer.alloc(n); for(let i=0;i<n;i++) buf[i]=e.readVram(i,1)[0]; fs.writeFileSync(S+`msx_${tag}.vram`,buf); return page; }
// закрыть стартовое сообщение, повернуться влево, достать меч
for(let k=0;k<6;k++){ setKeys(['fire']); e.runFrames(30); setKeys([]); e.runFrames(30); console.error('fire',k,'PC',pc().toString(16)); }
setKeys(['left']); e.runFrames(12); setKeys([]); e.runFrames(30);
console.error('перед X: PC',pc().toString(16),'ent',JSON.stringify(e.readMem(0xEA8E,12)));
setKeys(['action']); const js=new Set(); for(let k=0;k<36;k++){ e.runFrames(1); js.add(e.readMem(0xEC48,1)[0]); } setKeys([]); e.runFrames(24);
console.error('во время X joystick_state:',[...js].join(','),'после: PC',pc().toString(16),'ent',JSON.stringify(e.readMem(0xEA8E,12)));
let pages=[]; pages.push([0,dump(`${KIND}_00`)]);
setKeys(['fire',...KIND.split('+')]);
for(let i=1;i<=10;i++){ e.runFrames(6); pages.push([i,dump(`${KIND}_${String(i).padStart(2,'0')}`)]); if(i==3) setKeys([]); }
console.log(JSON.stringify(pages));
