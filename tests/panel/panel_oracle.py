# Оракул кэша панели (гейт): python3 tests/panel/panel_oracle.py [rom lst tag] из корня репо.
# Оракул кэша панели: в контрольных точках принудительно перерисовать всю панель
# (кэш := $FF, call draw_score_status) и сверить VRAM панели до/после. Совпало => кэш ничего не пропустил.
import sys, pathlib
ARGV=sys.argv[1:]; sys.argv=[sys.argv[0]]; sys.path.insert(0,'tools'); import run_vec as rv
sys.argv=[sys.argv[0]]+ARGV
ROUTE=[('none',60),('right',60),('fire',10),('none',30),('fire',10),('none',30),('right',40),('fire',10),('none',40),('left',60),('none',60),('right',80),('fire',10),('none',50)]
def panel_vram(cpu):
    out=bytearray()
    for base in (0x8000,0xA000,0xC000,0xE000):
        for x in range(32):
            col=base+x*256
            out+=bytes(cpu.mem[col+32:col+64])   # y 160..191 -> L 63..32
    return bytes(out)
def forced_redraw(cpu,sym):
    st=(cpu.pc,cpu.sp,cpu.a,cpu.b,cpu.c,cpu.d,cpu.e,cpu.h,cpu.l,cpu.f if hasattr(cpu,'f') else None,cpu.ie,cpu.halted)
    if 'vec_pc_char' in sym:
        for i in range(224): cpu.mem[sym['vec_pc_char']+i]=0xFF
    cpu.sp=0x7F00; cpu.push(0x0000); cpu.pc=sym['draw_score_status']; cpu.halted=False; cpu.ie=False
    n=0
    while cpu.pc!=0 and n<400000:
        if cpu.halted:   # halt бюджета DI внутри блита панели: «прерывание пришло» — счётчик кадра обнулён
            cpu.halted=False
            if 'vec_bud_used' in sym: cpu.mem[sym['vec_bud_used']]=0
        cpu.step(); n+=1
    assert cpu.pc==0, 'draw_score_status не вернулся'
    cpu.pc,cpu.sp,cpu.a,cpu.b,cpu.c,cpu.d,cpu.e,cpu.h,cpu.l=st[:9]
    if st[9] is not None: cpu.f=st[9]
    cpu.ie,cpu.halted=st[10],st[11]
    cpu.halted=False
    if cpu.ie:
        cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38   # как run_frames: прерывание после halt
ROM=sys.argv[1] if len(sys.argv)>1 else 'build/ianna.rom'; LST=sys.argv[2] if len(sys.argv)>2 else 'build/ianna_vec.lst'; TAG=sys.argv[3] if len(sys.argv)>3 else 'new'
def run(start):
    rv.START=start; rv._start_done[0]=False
    keys=[]; cpu=rv.make_cpu(keys); sym=rv.load_syms(pathlib.Path(LST))
    rom=open(ROM,'rb').read(); cpu.mem[0x100:0x100+len(rom)]=rom; cpu.pc=0x100
    rv.start_game(cpu, keys, sym)
    bad=0
    for i,(k,n) in enumerate(ROUTE):
        keys.clear()
        if k!='none': keys.append(k)
        rv.run_frames(cpu,n,sym=sym)
        # дорисовать хвост ожидания: в оригинале панель докрашивается в кадрах ожидания — дадим 6 кадров покоя
        keys.clear(); rv.run_frames(cpu,14,sym=sym)   # куски панели рисуются по одному за halt ожидания — дать дорисовать все
        # до безопасной точки: halt в waitforVBlank (окно квазидиска закрыто, SP свой)
        n=0; HALT=sym['waitforvblank_halt_go']
        while n<2000000:
            if cpu.halted:
                if cpu.pc==HALT+1: break          # halt цикла ожидания: окно закрыто, SP свой, vec_blit_ret не жив
                cpu.halted=False                  # halt бюджета внутри блита — прерывание «пришло», идём дальше
                if 'vec_bud_used' in sym: cpu.mem[sym['vec_bud_used']]=0
                if cpu.ie: cpu.ie=False; cpu.push(cpu.pc); cpu.pc=0x38
            cpu.step(); n+=1
        assert cpu.halted, 'нет halt'
        before=panel_vram(cpu); pal=list(cpu.mem[sym['vec_palette']:sym['vec_palette']+16]); img0=bytes(cpu.mem[0x8000:0x10000]); forced_redraw(cpu,sym); after=panel_vram(cpu)
        if before!=after:
            rv.render(img0,pal,f'build/oracle_{TAG}_{i}_before.png'); rv.render(bytes(cpu.mem[0x8000:0x10000]),pal,f'build/oracle_{TAG}_{i}_after.png')
            print('   score_semaphore =',cpu.mem[sym['score_semaphore']],'player_dead =',cpu.mem[sym['player_dead']])
            pos=[(i//(32*32), (i//32)%32, 223-(32+i%32)) for i in range(len(before)) if before[i]!=after[i]]
            print('   расхождения (плоскость, колонка x/8, y):', pos[:24])
            print('   кэш шкал:', [cpu.mem[sym['vec_pc_meter']+j] for j in range(64)] if 'vec_pc_meter' in sym else '-')
            ent=sym['ENTITY_DATA']; print('   игрок: энергия',cpu.mem[ent+4],'state',cpu.mem[ent+5],'exp',cpu.mem[sym['player_experience']])
        ent=sym['ENTITY_DATA']
        diff=sum(1 for a,b in zip(before,after) if a!=b)
        print(f'старт {start} точка {i} ({k}): энергия {cpu.mem[ent+4]}, враг {cpu.mem[ent+12+4]}, байт панели изменилось при полной перерисовке: {diff}')
        bad+=diff>0
    return bad
b=run((3,1))+run(None)
print('ИТОГ: точек с расхождением', b)
