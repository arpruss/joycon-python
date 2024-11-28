import pygame
import sys
from time import sleep,time
from pyjoycon import JoyCon,get_R_id,IRRegisters

mode = JoyCon.IR_POINTING

joycon_id = get_R_id()
r = IRRegisters()
r.defaults(mode)
if mode == JoyCon.IR_POINTING:
    r.pointingThreshold = 0
joycon = JoyCon(*joycon_id, ir_mode=mode, ir_registers=r)

start = time()
count = 0

def update(j):
    global count,screen
    count += 1
    for event in pygame.event.get():
        if event.type == pygame.QUIT: sys.exit()
    screen.fill((0,0,0))
    for cluster in j.get_ir_clusters():
        print(cluster)
        b = cluster["brightness"] * 255 // 65535
        pygame.draw.rect(screen, (b,b,b), pygame.Rect(cluster["x_start"],cluster["y_start"],cluster["x_end"]-cluster["x_start"],cluster["y_end"]-cluster["y_start"]))
        #pygame.draw.rect(screen, pygame.Rect(cluster["x_start"],cluster["y_start"],cluster["x_end"],cluster["y_end"]))
    pygame.display.flip()
    
#         return { "brightness": brightness, "pixels": pixels, "cm_x_64": cm_x_64, "cm_y_64": cm_y_64, "x_start": x_start,
#            "x_end": x_end, "y_start": y_start, "y_end": y_end }
    if count % 30 == 0:
        print(count/(time()-start))
#        print(j.get_status())
    

pygame.init()
screen = pygame.display.set_mode((320,240))

joycon.register_update_hook(update)


while True:     
    for event in pygame.event.get():
        if event.type == pygame.QUIT: sys.exit()
    sleep(0.1)


print(joycon.get_status())