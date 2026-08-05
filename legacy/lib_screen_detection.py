import pyautogui
import time
import pyscreeze
import warnings
import numpy as np
import re

## Visual Identifyers

def is_img_on_screen(path, conf, grayscale=True):
  try:
    pyscreeze.locateOnScreen(path, confidence=conf, grayscale=grayscale)
    return 1
  except pyscreeze.ImageNotFoundException:
    return 0

def where_is_img(path, conf, grayscale=True):
  try:
    r = pyscreeze.locateOnScreen(path, confidence=conf, grayscale=grayscale)
    return str(r)
  except pyscreeze.ImageNotFoundException:
    return 'NotFound'


def click_box_middle_coordinates(box_statement):
    if box_statement=='NotFound':
        return 0
    #Input example (string): "Box(left=np.int64(949), top=np.int64(492), width=22, height=26)"
    try:
        # Use regular expressions to extract the coordinates and dimensions
        match = re.search(r"left=np\.int64\((\d+)\), top=np\.int64\((\d+)\), width=(\d+), height=(\d+)", box_statement)
        if match:
            left = int(match.group(1))
            top = int(match.group(2))
            width = int(match.group(3))
            height = int(match.group(4))

            # Calculate the middle coordinates
            x = left + width // 2
            y = top + height // 2
            
            
            pyautogui.moveTo(x, y)
            time.sleep(0.5)
            pyautogui.click(x, y)
            return 1
        else:
            return 0  # Return None if the input string doesn't match the expected format
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0