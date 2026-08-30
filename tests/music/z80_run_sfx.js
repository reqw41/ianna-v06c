const fs=require('fs'); const Z80=require('/Users/boris/projects/knightmare-v06c/tools/vendor/Z80.js');
const mem=new Uint8Array(0x10000);
mem.set(fs.readFileSync('z80_drv_sfx.bin'),0xDDCC);
const src='/Users/boris/projects/ianna-v06c/ref/msx2/src/';
mem.set(fs.readFileSync(src+(process.env.SONG||'music-level1.mus')),0xC980); mem.set(fs.readFileSync(src+'iannafx.mus'),0xD980);
const sym=fs.readFileSync('z80_drv_sfx.sym','utf8'); const m=sym.match(/^start\s+EQU\s+([0-9A-F]+)H/mi); const start=parseInt(m[1],16);
const frames=[[]]; let reg=null; let halted=false;
const core={mem_read:a=>mem[a&0xffff], mem_write:(a,v)=>{mem[a&0xffff]=v&0xff;}, io_read:p=>0xff,
  io_write:(p,v)=>{p&=0xff; if(p===0xa0) reg=v; else if(p===0xa1) frames[frames.length-1].push([reg,v]); else if(p===0xff) frames.push([]);}};
const cpu=new Z80(core); cpu.reset(); let s=cpu.getState(); s.pc=start; cpu.setState(s);
let n=0; while(n<20_000_000){ const st=cpu.getState(); if(st.halted){break;} if(mem[st.pc]===0x76){halted=true;break;} cpu.run_instruction(); n++; }
console.log('halted',halted,'кадров',frames.length-1,'инстр',n);
fs.writeFileSync('z80_stream_sfx.json',JSON.stringify(frames.slice(0,-1)));
for (const i of [0,1,2,10,50,100]) console.log(i, JSON.stringify(frames[i].slice(0,14)));
