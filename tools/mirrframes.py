"""Какие кадры великанов рисуются зеркально: (банк, кадр) с частотой, по сценам."""
import sys, os, pathlib, collections
ST=sys.argv[1]; EDD=sys.argv[2]; L=int(sys.argv[3]); os.environ['IANNA_EDD']=EDD
sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); sys.path.insert(0,'tools/data'); import run_vec as rv; import build_edd as B
sym=rv.load_syms(pathlib.Path('build/ianna_vec.lst'))
keys=[]; cpu=rv.make_cpu(keys); rv.START=tuple(int(v) for v in ST.split(',')); rv.start_game(cpu,keys,sym)
DS=sym['drawSprite']; SRC=sym['vec_spr_src']; DIR=sym['vec_spr_dir']; PORT=sym['vec_spr_port']; mem=cpu.mem
two=B.BANK_2PLANE_BY_LEVEL.get(L,set())
banks=[(b,pg,base,lim) for b,pg,base,lim in B.LEVEL_BANKS[L]]
cnt=collections.Counter(); tot=collections.Counter()
keys.append('left')
for fr in range(360):
    if fr==120: keys.clear(); keys.append('right')
    if fr==240: keys.clear()
    while not cpu.halted:
        if cpu.pc==DS:
            src=mem[SRC]|(mem[SRC+1]<<8); pg=(mem[PORT]>>2)&3; d=mem[DIR]
            for b,bpg,base,lim in banks:
                if bpg==pg and base<=src<lim:
                    fb=288 if b in two else 576; k=(src-base)//fb
                    if b in two: tot[b]+=1
                    if d and b in two: cnt[(b,k)]+=1
        cpu.step()
    cpu.halted=False
    if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
by=collections.defaultdict(list)
for (b,k),n in sorted(cnt.items()): by[b].append(f'{k}×{n}')
for b in sorted(by): print(f'  банк {b}: зеркально {sum(n for (bb,k),n in cnt.items() if bb==b)} из {tot[b]} выводов; кадры: {" ".join(by[b])}')
