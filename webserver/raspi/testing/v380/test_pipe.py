import subprocess
import numpy as np
import cv2

width, height = 1280, 720
ffmpeg_cmd = [
    'ffmpeg',
    '-f', 'dshow',
    '-video_size', f'{width}x{height}',
    '-framerate', '30',
    '-i', 'video=V380 FHD Camera',
    '-pix_fmt', 'bgr24',
    '-f', 'rawvideo',
    'pipe:1'
]

proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

frame_size = width * height * 3  # 3 bytes per pixel for bgr24

try:
    while True:
        raw_frame = proc.stdout.read(frame_size)
        if len(raw_frame) < frame_size:
            break
        
        frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))
        cv2.imshow('V380 Camera (FFmpeg pipe)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    proc.terminate()
    cv2.destroyAllWindows()
