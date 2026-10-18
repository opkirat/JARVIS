import subprocess
import pyautogui
import time

url = "https://app.crowdmark.com/sign-in/waterloo"

# Open Chrome
subprocess.Popen(["open", "-a", "Google Chrome", url])

# Wait for website
time.sleep(3)

# Click button
pyautogui.click(740, 570)