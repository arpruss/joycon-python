from time import sleep,time
from pyjoycon import Joycon,get_R_id

joycon_id = get_R_id()
joycon = pyjoycon.JoyCon(*joycon_id, ir_mode=Joycon.IR_POINTING)

start = time()
count = 0

def update(j):
    global count
    count += 1
    if count % 30 == 0:
        print(count/(time()-start))
        print(j.get_ir_clusters())
    

joycon.register_update_hook(update)
while True:     
    sleep(0.1)


print(joycon.get_status())