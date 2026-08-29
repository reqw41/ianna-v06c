// Запуск ROM Ianna в headless WebMSX (MSX2, ASCII16): регистры, переменные, дамп VRAM.
// node run_ianna.js <rom> [frames] [vram_out]
const M=require(__dirname+'/emu_ianna.js'); const fs=require('fs');
const rom=process.argv[2], frames=+(process.argv[3]||600), out=process.argv[4];
const e=new M(); e.loadCartridge(rom); e.runFrames(frames);
const r=e.readRegs(); console.error('PC=%s SP=%s HL=%s IX=%s', r.PC.toString(16), r.SP.toString(16), r.HL.toString(16), r.IX.toString(16));
const hx=a=>a.map(b=>b.toString(16).padStart(2,'0')).join(' ');
console.error('FrameCounter(eb52):', hx(e.readMem(0xeb52,2)), ' ROMBank1(ec43):', hx(e.readMem(0xec43,1)), ' menu(ecb9..):', hx(e.readMem(0xecb9,6)), ' music_addr(c980):', hx(e.readMem(0xc980,8)));
const v=e.m.vdp; let st=null; try{ st=v.saveState(1);}catch(x){}
if(st){ const regs=st.register||st.registers; if(regs) console.error('VDP R0-R9:', Array.from(regs).slice(0,10).map(x=>x.toString(16)).join(' ')); console.error('vram len:', st.vram? (st.vram.length||'?') : 'нет ключа vram; ключи: '+Object.keys(st).join(',')); }
if(out){ const n=0x20000; const buf=Buffer.alloc(n); for(let i=0;i<n;i++) buf[i]=e.readVram(i,1)[0]; fs.writeFileSync(out,buf); console.error('VRAM записан:',out); }
