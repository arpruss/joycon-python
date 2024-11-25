from time import sleep
import pyjoycon
#from pyjoycon import JoyCon, get_R_id

joycon_id = pyjoycon.get_R_id()
joycon = pyjoycon.JoyCon(*joycon_id, ir_mode=pyjoycon.JOYCON_IR_CLUSTERING)

joycon.register_update_hook(lambda j : print(j.get_status()))
while True: sleep(0.1)


#print(joycon.get_status())