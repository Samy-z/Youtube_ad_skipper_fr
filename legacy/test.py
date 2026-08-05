import asyncio
import pyautogui
import time
import datetime
import os
import lib_screen_detection as lib

async def main():
    
    img_path = "youtube_add_skipper/img/ignore_button_fr.png"
    start_time = time.time()
    
    
    
    while (time.time() - start_time) < 300:
        restart_time = time.time()
        a = lib.where_is_img("./img/ignore_button_fr.png", 0.9)
        if a !='NotFound':
            x, y = pyautogui.position()
            print(a)
            print("Button Detected with conf: 0.9")
            print(f"Mouse position: x={x}, y={y}")
        print(time.time()-restart_time)            
        
        time.sleep(1) # Adjust the delay as needed
        
asyncio.run(main())
