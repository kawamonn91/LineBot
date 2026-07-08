import cv2
import time

for idx in [0, 1]:
    print(f"--- Testing index {idx} ---")
    cap = cv2.VideoCapture(idx) # try default API first
    if not cap.isOpened():
        print(f"Cannot open index {idx}")
        continue
    
    # Try reading 5 frames
    for i in range(5):
        ret, frame = cap.read()
        if ret:
            print(f"Success frame {i} from index {idx}!")
            cv2.imwrite(f"test_cam_{idx}.jpg", frame)
            break
        else:
            print(f"Failed to read frame {i}")
        time.sleep(0.5)
    cap.release()
