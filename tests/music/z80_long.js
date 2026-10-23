// Длинный прогон Z80-плеера: поток регистров AY по кадрам, поиск периода песни, оценка размера.
const fs=require('fs'); const Z80=require(__dirname+'/../../tools/vendor/Z80.js');
const mem=new Uint8Array(0x10000);
mem.set(fs.readFileSync('z80_drv_long.bin'),0xDDCC);
const src=__dirname+'/../../ref/msx2/src/';
const song=process.argv[2]||'music-level1.mus'; const NF=+(process.argv[3]||30000);
mem.set(fs.readFileSync(src+song),0xC980); mem.set(fs.readFileSync(src+'iannafx.mus'),0xD980);
const sym=fs.readFileSync('z80_drv_long.sym','utf8'); const m=sym.match(/^start\s+EQU\s+([0-9A-F]+)H/mi); const start=parseInt(m[1],16);
// драйвер делает фиксированное число кадров: патчим? — вместо этого ловим halt и продолжаем вызывать atPlay сами
const frames=[]; let cur=new Array(14).fill(0); let reg=null;
const core={mem_read:a=>mem[a&0xffff], mem_write:(a,v)=>{mem[a&0xffff]=v&0xff;}, io_read:p=>0xff,
  io_write:(p,v)=>{p&=0xff; if(p===0xa0) reg=v; else if(p===0xa1){ if(reg<14) cur[reg]=v; } else if(p===0xff){ frames.push(cur.slice()); }}};
const cpu=new Z80(core); cpu.reset(); let s=cpu.getState(); s.pc=start; cpu.setState(s);
let n=0; while(frames.length<NF && n<400_000_000){ const st=cpu.getState(); if(mem[st.pc]===0x76){ break; } cpu.run_instruction(); n++; }
console.log(song,'кадров получено',frames.length,'(драйвер остановился на halt:',frames.length<NF,')');
// период: ищем p такой, что frames[i]==frames[i+p] для всех i в [start0, len-p)
function eq(a,b){for(let k=0;k<14;k++) if(a[k]!==b[k]) return false; return true;}
let period=null; const L=frames.length;
for(let p=50;p<L/2;p++){ let ok=true; for(let i=Math.floor(L/2);i<L-p;i+=1){ if(!eq(frames[i],frames[i+p])){ok=false;break;} } if(ok){period=p;break;} }
console.log('период (кадров):',period, period?`= ${(period/50).toFixed(1)} с`:'');
const P=period||L;
// размер: сырой 14*P; дельта: маска 2 байта + изменившиеся регистры
let delta=0, changes=0; let prev=new Array(14).fill(-1);
for(let i=0;i<P;i++){ let c=0; for(let k=0;k<14;k++) if(frames[i][k]!==prev[k]){c++;} delta+=2+c; changes+=c; prev=frames[i]; }
const zlib=require('zlib'); const raw=Buffer.from(frames.slice(0,P).flat()); const z=zlib.deflateSync(raw,{level:9}).length;
console.log(`сырой 14*P = ${14*P} Б; дельта (маска+значения) = ${delta} Б (в среднем ${(changes/P).toFixed(2)} рег./кадр); deflate = ${z} Б`);
