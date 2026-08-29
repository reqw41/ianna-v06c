
const fs=require('fs'); const Z80=require('/Users/boris/projects/knightmare-v06c/tools/vendor/Z80.js');
const mem=new Uint8Array(0x10000); mem.set(fs.readFileSync('z80_drv.bin'),0xDDCC);
const src='/Users/boris/projects/ianna-v06c/ref/msx2/src/'; mem.set(fs.readFileSync(src+'music-level1.mus'),0xC980); mem.set(fs.readFileSync(src+'iannafx.mus'),0xD980);
const core={mem_read:a=>mem[a&0xffff], mem_write:(a,v)=>{mem[a&0xffff]=v&0xff;}, io_read:p=>0xff, io_write:(p,v)=>{}};
const cpu=new Z80(core); cpu.reset(); let s=cpu.getState(); s.pc=58686; cpu.setState(s);
const out=[]; let n=0;
while(n<2e6 && out.length<6){ const st=cpu.getState(); if(st.pc===57024) out.push({at:'load',b:st.b,h:st.h,l:st.l,lut:[mem[57026+1],mem[57026+2]]}); if(st.pc===57053) out.push({at:'set',h:st.h,l:st.l}); cpu.run_instruction(); n++; }
console.log(JSON.stringify(out));
