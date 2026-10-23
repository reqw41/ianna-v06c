
const fs=require('fs'); const Z80=require(__dirname+'/../../tools/vendor/Z80.js');
const mem=new Uint8Array(0x10000); mem.set(fs.readFileSync('z80_drv.bin'),0xDDCC);
const src=__dirname+'/../../ref/msx2/src/'; mem.set(fs.readFileSync(src+'music-level1.mus'),0xC980); mem.set(fs.readFileSync(src+'iannafx.mus'),0xD980);
const cells=JSON.parse(process.argv[2]); const start=parseInt(process.argv[3]);
let frame=0; const dumps=[];
const core={mem_read:a=>mem[a&0xffff], mem_write:(a,v)=>{mem[a&0xffff]=v&0xff;}, io_read:p=>0xff,
 io_write:(p,v)=>{ if((p&0xff)===0xff){ const d={}; for(const [n,[a,o,l]] of Object.entries(cells)) d[n]=Array.from(mem.slice(a+o,a+o+l)); dumps.push(d); frame++; } }};
const cpu=new Z80(core); cpu.reset(); let s=cpu.getState(); s.pc=start; cpu.setState(s);
let n=0; while(frame<3 && n<5e6){ cpu.run_instruction(); n++; }
console.log(JSON.stringify(dumps));
