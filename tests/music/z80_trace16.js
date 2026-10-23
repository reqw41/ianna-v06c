const fs=require('fs'); const Z80=require(__dirname+'/../../tools/vendor/Z80.js');
const mem=new Uint8Array(0x10000); mem.set(fs.readFileSync('z80_drv.bin'),0xDDCC);
const src=__dirname+'/../../ref/msx2/src/';
mem.set(fs.readFileSync(src+'music-level1.mus'),0xC980); mem.set(fs.readFileSync(src+'iannafx.mus'),0xD980);
const sym=fs.readFileSync('z80_drv.sym','utf8'); const S={};
for (const m of sym.matchAll(/^(\S+)\s+EQU\s+([0-9A-F]+)H/gmi)) S[m[1]]=parseInt(m[2],16);
const want={}; for (const n of ['_atPlaySound','_atSound_calcFrequency','_atSound_getFrequency_manual','_atSound_getFrequency','_atSound_calcFrequency_noArp','PLY_PS_S_SoundOn','PLY_PS_Hard','PLY_PS_S_SecondByteNeeded']) if(S[n]!==undefined) want[S[n]]=n;
let frame=0;
const core={mem_read:a=>mem[a&0xffff], mem_write:(a,v)=>{mem[a&0xffff]=v&0xff;}, io_read:p=>0xff, io_write:(p,v)=>{ if((p&0xff)===0xff) frame++; }};
const cpu=new Z80(core); cpu.reset(); let s=cpu.getState(); s.pc=S['start']; cpu.setState(s);
let n=0; while(frame<17 && n<3000000){ const st=cpu.getState(); if(frame===16 && want[st.pc]) { const h=x=>x.toString(16).padStart(2,'0'); console.log(want[st.pc].padEnd(32),`HL=${h(st.h)}${h(st.l)} B=${h(st.b)} C=${h(st.c)} D=${h(st.d)} E=${h(st.e)} A=${h(st.a)} DE'=${h(st.d_prime)}${h(st.e_prime)} HL'=${h(st.h_prime)}${h(st.l_prime)}`);} cpu.run_instruction(); n++; }
