import cv2
import socket
import numpy as np
import time
import threading
import struct

# EC2
UDP_IP = '127.0.0.1'  # Replace with your EC2 IP
UDP_PORT = 9002
MAX_FRAME_SIZE = 60000  # Max safe UDP payload size

# UDP socket setup
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))  # Bind to receive data

def receiver_thread():
    """Thread to receive and display frames"""
    while True:
        try:
            data, _ = sock.recvfrom(MAX_FRAME_SIZE + 10) 
            timestamp = time.time()
            if len(data) < 8:
                continue 
            
            frame_time = struct.unpack("!d", data[:8])[0]

            if timestamp - frame_time > 0.1: 
                continue

            frame = cv2.imdecode(np.frombuffer(data[8:], np.uint8), cv2.IMREAD_COLOR)
            cv2.imshow('window', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        except Exception as e:
            print(f"Error: {e}")
            break

# Start receiver thread
recv_thread = threading.Thread(target=receiver_thread, daemon=True)
recv_thread.start()

# Wait for the thread to finish
recv_thread.join()  # This prevents the script from exiting immediately

print("Receiver thread has exited.")
