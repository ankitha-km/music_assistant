# Run this while YouTube Music is open on a search results page.
# It will press Tab keys one by one so you can see which tab lands on Play.
# Watch your screen and press Ctrl+C when you see the Play button highlighted.

import pyautogui
import time

print("Switch to your browser NOW — you have 4 seconds...")
time.sleep(4)

pyautogui.hotkey("ctrl", "l")   # focus address bar
time.sleep(0.3)
pyautogui.press("escape")
time.sleep(0.3)

for i in range(1, 20):
    pyautogui.press("tab")
    time.sleep(0.6)   # slow enough to watch
    print(f"Tab {i} pressed — is Play button highlighted?")

print("Done! Tell me which Tab number highlighted the Play button.")