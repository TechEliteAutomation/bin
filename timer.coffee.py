import os
from datetime import datetime
import time
import subprocess

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def text_to_speech(text):
    if not text.strip():
        print(f"[{get_timestamp()}] ERROR: NO VALID INPUT DETECTED.")
        return
    
    try:
        with open(os.devnull, 'w') as DEVNULL:
            subprocess.run(['espeak', text], stderr=DEVNULL)
    except Exception as e:
        print(f"[{get_timestamp()}] SYSTEM FAILURE DETECTED: {e}")

def french_press_timer():
    steps = [
        (0,   "HOT WATER APPLIED TO COFFEE GROUNDS. STIR AND SEAL."),
        (65,  "REMOVE COVER. APPLY REMAINING WATER. STIR. RESEAL."),
        (175, "ENGAGE PLUNGER. EXTRACTION COMPLETE. CONSUME."),
    ]
    
    start_time = time.time()
    print(f"[{get_timestamp()}] SYSTEM ONLINE: TIMER ACTIVATED.")
    print(f"[{get_timestamp()}] {steps[0][1]}")
    text_to_speech(steps[0][1])
    
    next_step_index = 1
    
    while True:
        elapsed_seconds = int(time.time() - start_time)
        remaining_time = steps[next_step_index][0] - elapsed_seconds if next_step_index < len(steps) else 0
        
        print(f"[{get_timestamp()}] COUNTDOWN: {remaining_time} SECONDS UNTIL NEXT EVENT.", end='\r', flush=True)
        
        if next_step_index < len(steps) and elapsed_seconds >= steps[next_step_index][0]:
            print(f"\n[{get_timestamp()}] {steps[next_step_index][1]}")
            text_to_speech(steps[next_step_index][1])
            next_step_index += 1
            
        if elapsed_seconds >= 175:
            break
        
        time.sleep(1)
    
    print(f"[{get_timestamp()}] SYSTEM OFFLINE: TIMER COMPLETED.")

if __name__ == "__main__":
    french_press_timer()
