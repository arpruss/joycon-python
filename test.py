from time import sleep,time
import pyjoycon

joycon_id = pyjoycon.get_R_id()
joycon = pyjoycon.JoyCon(*joycon_id, ir_mode=pyjoycon.JOYCON_IR_CLUSTERING)

def update(j):
    print(j.get_ir_clusters())
    

joycon.register_update_hook(update)
while True:     
    sleep(0.1)


print(joycon.get_status())