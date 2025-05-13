import cv2
import socket
import numpy as np

# Configuration
UDP_IP = "127.0.0.1"  # Replace with your EC2 public IP
UDP_PORT = 8085  # The port EC2 will listen on for video data
MAX_UDP_PACKET_SIZE = 65507  # Maximum UDP payload size
CAMERA_INDEX = 0  # Default camera index (0 for Raspberry Pi's default camera)

# Set up UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Initialize the camera
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()
#cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920) 640
#cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080) 480


print("Capturing video and sending it to EC2 as fast as possible...")

try:
    while True:
        # Capture frame
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture image.")
            break

        # Encode the frame to JPEG with lower quality
        _, encoded_frame = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        encoded_frame = encoded_frame.tobytes()

        # Split the encoded frame into chunks and send
        for i in range(0, len(encoded_frame), MAX_UDP_PACKET_SIZE):
            chunk = encoded_frame[i:i + MAX_UDP_PACKET_SIZE]
            sock.sendto(chunk, (UDP_IP, UDP_PORT))

except KeyboardInterrupt:
    print("Stream stopped by user.")

finally:
    # Release resources
    cap.release()
    sock.close()
    print("Camera and socket released.")