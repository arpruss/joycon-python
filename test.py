from time import sleep,time
from pyjoycon import JoyCon,get_R_id,IRRegisters

joycon_id = get_R_id()
r = IRRegisters()
r.defaults(mode=JoyCon.IR_POINTING)
r.pointingThreshold = 0
joycon = JoyCon(*joycon_id, ir_mode=JoyCon.IR_POINTING, ir_registers=r)

start = time()
count = 0

def update(j):
    global count
    count += 1
    if count % 30 == 0:
        print(count/(time()-start))
        print(j.get_ir_clusters())
        #r.read(joycon)
        #print(r)
    

joycon.register_update_hook(update)
while True:     
    sleep(0.1)


print(joycon.get_status())