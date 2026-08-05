import asyncio
import pyautogui
import time
import lib_screen_detection as lib

async def main(active_time_hrs=2, tick_rate=1): #tick_rate = 1 --> 1 tick/second
    
    if tick_rate > 0.0 and active_time_hrs > 0.0:
        print(f"Youtube Add Skipper Started on {str(time.ctime(int(time.time())))}.\nWill run for {active_time_hrs} hours at a tick_rate of {tick_rate} tick/second (1 tick every {(1/tick_rate)}s).\n")
        img_path = "./img/ignore_button.png"
        start_time = time.time()
        
        while (time.time() - start_time) < 3600*active_time_hrs:
            loop_restart_time = time.time()
            skip_button = lib.where_is_img(img_path, 0.8)
            if skip_button !='NotFound':
                print(f"{str(time.ctime(int(time.time())))}: Skip Button Found using file: {img_path} at location:{skip_button}")
                x, y = pyautogui.position()
                lib.click_box_middle_coordinates(skip_button)
                time.sleep(0.1)
                print(f"Return to old Mouse position: x={x}, y={y}\n")
                pyautogui.moveTo(x, y)                
                
            time.sleep((1/tick_rate)-(time.time()-loop_restart_time)) # Adjust the delay as needed to tick every 1 second
    else:
        print("Error at Launch: Time Parameters entered are Incorrect, please check how you casted active_time_hrs (must be > 0) and tick_rate (must be > 0)")
        
asyncio.run(main(active_time_hrs=6, tick_rate=0.25))
