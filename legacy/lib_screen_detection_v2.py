import pyautogui
import time
import mss
import cv2
import numpy as np
from PIL import Image

def screenshot_all_monitors():
    """Capture a screenshot of the entire virtual screen (all monitors combined)."""
    with mss.mss() as sct:
        # The first monitor is the virtual screen that spans all monitors
        monitor = sct.monitors[0]  # This will capture all connected monitors
        sct_img = sct.grab(monitor)
        img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
        return img

def resize_image_independently(path, min_width_scale=0.5, max_width_scale=1.5, width_step=0.05,
                                min_height_scale=0.5, max_height_scale=1.5, height_step=0.05):
    """Resize the image independently in width and height to test various combinations."""
    img = cv2.imread(path)  # Read the image with OpenCV
    resized_images = []
    
    w, h = img.shape[1], img.shape[0]  # Initial dimensions

    # Loop over width scaling
    for w_scale in np.arange(min_width_scale, max_width_scale, width_step):
        new_w = int(w * w_scale)
        
        # Loop over height scaling independently
        for h_scale in np.arange(min_height_scale, max_height_scale, height_step):
            new_h = int(h * h_scale)
            
            resized_img = cv2.resize(img, (new_w, new_h))  # Resize the image
            resized_images.append(resized_img)
    
    return resized_images

def where_is_img(path, conf=0.9, grayscale=True):
    """Locate an image on all connected monitors using a single screenshot of the entire virtual screen."""
    try:
        # Capture the full virtual screen (all monitors combined)
        screen = screenshot_all_monitors()

        # Resize the image dynamically with independent width and height
        resized_images = resize_image_independently(path)
        
        # Convert the full screenshot to an OpenCV format (numpy array)
        screen_np = np.array(screen)

        # Check all resized versions of the image
        for resized_img in resized_images:
            # Convert the resized image to a format pyautogui understands (PIL)
            resized_pil_img = Image.fromarray(cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB))
            
            # Use pyautogui's locate function to find the image in the screenshot
            location = pyautogui.locate(resized_pil_img, screen, grayscale=grayscale, confidence=conf)
            
            if location:
                return location  # Return the location (coordinates) found

        return 'NotFound'
    
    except Exception as e:
        print(f"Error in where_is_img: {e}")
        return 'NotFound'


def click_box_middle_coordinates(box_statement):
    """Click the center of the located image's bounding box."""
    if box_statement == 'NotFound':
        return 0
    try:
        # Extract the location (left, top, width, height)
        left, top, width, height = box_statement
        # Calculate the middle coordinates
        x = left + width // 2
        y = top + height // 2

        # Move the cursor and click at the computed position
        pyautogui.moveTo(x, y)
        time.sleep(0.5)
        pyautogui.click(x, y)
        return 1
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0


# Example usage of dynamically resizing in width and height independently
location = where_is_img("button.png")
if location != 'NotFound':
    click_box_middle_coordinates(location)
else:
    print("Button not found!")
