from time import sleep,time
from pyjoycon import JoyCon,get_R_id,IRRegisters

joycon_id = get_R_id()
r = IRRegisters()
mode = JoyCon.IR_IMAGE
r.defaults(mode)
r.pointingThreshold = 0
joycon = JoyCon(*joycon_id, ir_mode=mode, ir_registers=r)#JoyCon.IR_POINTING

start = time()
count = 0

def update(j):
    global count
    count += 1
    if count % 30 == 0:
        print(count/(time()-start))
        #print(j.get_status())
        #r.read(joycon)
        #print(r)
    

joycon.register_update_hook(update)
while True:     
    sleep(0.1)


print(joycon.get_status())