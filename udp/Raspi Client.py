import cv2
import socket
import numpy as np
import time
import threading
import struct

# EC2
UDP_IP = '127.0.0.1'  # Replace with your EC2 IP
UDP_PORT = 9000
MAX_FRAME_SIZE = 60000  # Max safe UDP payload size

# Camera settings (reduce resolution for better performance)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
cap.set(cv2.CAP_PROP_FPS, 25)

# UDP socket setup
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
last_frame_time = time.time()
current_frame = None
frame_lock = threading.Lock()

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Compress frame (adjust quality as needed)
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        
         # 8-byte double in network byte order
        header = struct.pack("!d", time.time())
        packet = header + buffer.tobytes()
        
        # Split into chunks if needed (rarely necessary with 640x360)
        if len(packet) > MAX_FRAME_SIZE:
            continue 
            
        sock.sendto(packet, (UDP_IP, UDP_PORT))
    
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
except Exception as e:
    print(f"Error: {e}")
finally:
    cap.release()
    sock.close()
    cv2.destroyAllWindows()