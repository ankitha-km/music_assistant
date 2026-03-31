# Run this script WHILE YouTube Music is open on the search results page
# It will tell you the exact coordinates of where your mouse is
# Hover your mouse over the Play button and wait 5 seconds

import pyautogui
import time

print("Move your mouse to the Play button on YouTube Music...")
print("You have 5 seconds...")
for i in range(5, 0, -1):
    print(f"{i}...")
    time.sleep(1)

x, y = pyautogui.position()
print(f"\nPlay button is at: x={x}, y={y}")
print("Copy these numbers and tell me!")