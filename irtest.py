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
        b = cluster.brightness * 255 // 65535
        r = cluster.start[0],cluster.start[1],cluster.end[0]-cluster.start[0]+1,cluster.end[1]-cluster.start[1]+1
        pygame.draw.rect(screen, (b,b,b), pygame.Rect(*r))
        screen.set_at((int(cluster.cm[0]+0.5),int(cluster.cm[1]+0.5)),(255,0,0))
    pygame.display.flip()
    if count % 30 == 0:
        print(count/(time()-start))
#        print(j.get_status())
    

pygame.init()
screen = pygame.display.set_mode((240,320))
screen.fill((0,0,0))
pygame.display.flip()

joycon.register_update_hook(update)


while True:     
    for event in pygame.event.get():
        if event.type == pygame.QUIT: sys.exit()
    sleep(0.1)


print(joycon.get_status())