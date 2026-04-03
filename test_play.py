# Run this while YouTube Music is open with a search result visible.
# It will take a screenshot, try to find the Play button, and show you where.

import pyautogui
import time
import os
from PIL import Image

PLAY_BTN_IMG = r"D:\Projects\my_assistant\play_btn.png"

print("Switch to YouTube Music now — 4 seconds...")
time.sleep(4)

# Take screenshot
screenshot = pyautogui.screenshot()
screenshot.save(r"D:\Projects\my_assistant\debug_screen.png")
print("Screenshot saved as debug_screen.png")

# Try to find play button at different confidence levels
for conf in [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]:
    try:
        loc = pyautogui.locateOnScreen(PLAY_BTN_IMG, confidence=conf)
        if loc:
            print(f"FOUND at confidence {conf}: {loc}")
            center = pyautogui.center(loc)
            print(f"Center: {center}")
            pyautogui.click(center)
            print("Clicked!")
            break
    except Exception as e:
        print(f"Confidence {conf}: error — {e}")
else:
    print("Button NOT found at any confidence level.")
    print("Check debug_screen.png to see what the screen looks like.")