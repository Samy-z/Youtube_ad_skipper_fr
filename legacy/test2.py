import mss
import mss.tools
import pyscreeze
from PIL import Image


def screenshot_all_monitors():
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # monitor[0] is the full virtual screen
        sct_img = sct.grab(monitor)
        img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
        return img
        
def where_is_img(path, conf=0.9, grayscale=True):
    try:
        screen = screenshot_all_monitors()
        location = pyscreeze.locate(path, screen, confidence=conf, grayscale=grayscale)
        return str(location) if location else 'NotFound'
    except Exception as e:
        print(f"Error in where_is_img: {e}")
        return 'NotFound'

img = screenshot_all_monitors()
print("Captured screen size:", img.size)