# server_mjpeg_display.py
import socket
import struct
import time
import cv2
import numpy as np

HOST = '0.0.0.0'
PORT = 8082

def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        more = sock.recv(size - len(data))
        if not more:
            raise ConnectionError("Socket closed")
        data += more
    return data

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
    server_sock.bind((HOST, PORT))
    server_sock.listen(1)
    print(f"Listening on {HOST}:{PORT}...")
    conn, addr = server_sock.accept()
    print(f"Connected by {addr}")

    frame_count = 0
    prev_time = time.monotonic()

    try:
        while True:
            # Receive 4-byte length prefix
            raw_len = recv_exact(conn, 4)
            pkt_len = struct.unpack('>I', raw_len)[0]

            # Receive JPEG data
            jpeg_data = recv_exact(conn, pkt_len)
            frame_count += 1
            now = time.monotonic()
            total_time = now - prev_time
            if total_time >= 1.0:
                fps = frame_count / total_time
                print(f"FPS: {fps:.2f}")
                frame_count = 0
                prev_time = now


            # Decode JPEG to image
            img_np = np.frombuffer(jpeg_data, dtype=np.uint8)
            img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

            if img is not None:
                cv2.imshow("MJPEG Video", img)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                print("Failed to decode frame")

    except (ConnectionError, KeyboardInterrupt):
        print("Stopping server...")

    finally:
        conn.close()
        cv2.destroyAllWindows()

'''
    Client Implementation
'''

'''
import av
import socket
import struct
import cv2

HOST = '192.168.18.48'  # Replace with your server IP
PORT = 8082
WIDTH, HEIGHT = 640, 480
JPEG_QUALITY = 50

# Open /dev/video0 using raw format (YUYV)
container = av.open(
    '/dev/video0',
    format='v4l2',
    options={
        'video_size': f'{WIDTH}x{HEIGHT}',
        'framerate': '30',
        'input_format': 'yuyv422',
    }
)

video_stream = next((s for s in container.streams if s.type == 'video'), None)
if video_stream is None:
    raise RuntimeError("No video stream found")

print("Starting capture and sending MJPEG frames...")

with socket.create_connection((HOST, PORT)) as sock:
    for frame in container.decode(video_stream):
        # Convert frame to BGR24 for OpenCV
        bgr = frame.to_ndarray(format='bgr24')

        # Encode as JPEG with custom quality
        ret, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ret:
            continue

        data = jpeg.tobytes()
        sock.sendall(struct.pack('>I', len(data)) + data)
'''