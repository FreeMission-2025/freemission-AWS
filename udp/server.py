import socket
import time

# UDP PORT for Raspi Communication
UDP_IP = '0.0.0.0'
UDP_PORT = 9000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

# UDP PORT for Receiver Client Communication . 
# Change according to Receiver IP
CLIENT_IP = '127.0.0.1' 
CLIENT_PORT = 9002

sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("UDP server running...")
while True:
    try:
        data, addr = sock.recvfrom(65507)
        print(f"Received {len(data)} bytes from {addr}")

        sock2.sendto(data, (CLIENT_IP, CLIENT_PORT))

        print(f"Echoed back to {CLIENT_IP}")

    except Exception as e:
        print(f"Error: {e}")
