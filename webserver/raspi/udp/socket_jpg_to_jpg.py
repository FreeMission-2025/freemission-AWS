import platform
import struct
import time

import requests
system = platform.system()

try:
    if system == 'Linux':
        import uvloop
        uvloop.install()
    elif system == 'Windows':
        import winloop
        winloop.install()
except ModuleNotFoundError:
    pass
except Exception as e:
    print(f"Error when installing loop: {e}")

import asyncio
import cv2
import contextlib
from zlib import crc32
''' 
    UDP Configuration
'''
EC2_UDP_IP = "127.0.0.1"
EC2_UDP_PORT = 8085
MAX_UDP_PACKET_SIZE = 1450  # Max safe UDP payload size
CAMERA_INDEX = 0             # Default camera index

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s B"       # | 4-byte marker | 3-byte frame_id | 1-byte chunk_index |
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

class UDPSender(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        # single method handles both ACKs and normal datagrams
        if len(data) == ACK_SIZE and data.startswith(ACK_MARKER):
            _, fid_bytes, chunk_idx = struct.unpack(ACK_FORMAT, data)
            key = (int.from_bytes(fid_bytes, 'big'), chunk_idx)
            print(f"ACK received: frame={key[0]} chunk={key[1]}")
        else:
            # any other inbound message
            print(f"Received from {addr}: {data!r}")

    def send(self, data: bytes):
        if self.transport:
            self.transport.sendto(data, (EC2_UDP_IP, EC2_UDP_PORT))

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")

''' Global Variable '''
frame_id_counter = 0

class VideoStream:
    def __init__(self, frame_queue:asyncio.Queue, src=0, desired_width=680,):
        api = cv2.CAP_MSMF if system =='Windows' else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(src, apiPreference=api)
        
        if not self.cap.isOpened():
            raise Exception("Error: Could not open webcam.")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self.ret, self.frame = self.cap.read()
        self.frame_queue = frame_queue
        self.desired_width = desired_width
        self.stopped = False
    
    async def start(self):
        self.running = True
        loop = asyncio.get_running_loop()

        while self.running:
            try:
                ret, frame = await loop.run_in_executor(None, self.cap.read)
                if not ret:
                    await asyncio.sleep(0.5)
                    continue

                #frame = cv2.resize(frame, (self.desired_width, int(frame.shape[0] * self.desired_width / frame.shape[1])))
                if self.frame_queue.full():
                    print("queue full, skipping frame")

                await self.frame_queue.put(frame.copy())
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"error at video_stream: {e}")
            
    def stop(self):
        self.stopped = True
        self.cap.release()

START_MARKER = b'\x01\x02\x7F\xED'  # 4-byte start marker
END_MARKER = b'\x03\x04\x7F\xED'    # 4-byte end marker

# Updated header format: 4s (marker), I (Time Stamp), 3s (frame_id), B (total_chunks), B (chunk_index), H (chunk_length), I (checksum)
HEADER_FORMAT = "!4s I 3s B B H I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = MAX_UDP_PACKET_SIZE - HEADER_SIZE - len(END_MARKER)

async def send_frame(protocol: UDPSender, encoded_frame: bytes):
    global frame_id_counter
    frame_id = frame_id_counter & 0xFFFF  # stay within 2 bytes
    frame_id_b = (frame_id & 0xFFFFFF).to_bytes(3, 'big')  # Stay within 3 bytes (24-bit)
    frame_id_counter += 1

    # Break frame into chunks
    total_chunks = (len(encoded_frame) + MAX_PAYLOAD_SIZE - 1) // MAX_PAYLOAD_SIZE
    time_ms = int(time.time() * 1000) % 0x100000000

    for chunk_index in range(total_chunks):
        start = chunk_index * MAX_PAYLOAD_SIZE
        end = start + MAX_PAYLOAD_SIZE
        chunk = encoded_frame[start:end]
        chunk_length = len(chunk)
        checksum = crc32(chunk)

        # | START_MARKER (4 bytes) | timestamp (4 bytes) | frame_id (3 bytes) | total_chunks (1 byte) | chunk_index (1 byte) | chunk_length (2 bytes) | crc32_checksum (4 bytes) |
        header = struct.pack(HEADER_FORMAT, START_MARKER, time_ms, frame_id_b, total_chunks, chunk_index, chunk_length, checksum)

        # Send the header + chunk + END_MARKER
        protocol.send(header + chunk + END_MARKER)

async def main():
    url = "http://localhost:80/reset_stream"
    headers = {"Content-Type": "application/json"}
    data = {
        "message": "INIT_STREAM",
        "auth": "BAYU"
    }
    response = requests.post(url, json=data, headers=headers)
    print(response.status_code)
    print(response.json())
    await asyncio.sleep(3)

    frame_queue = asyncio.Queue(maxsize=120)
    vs = VideoStream(frame_queue)

    capture_task = asyncio.create_task(vs.start())
    loop = asyncio.get_running_loop()

    # Create UDP Client / Sender endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSender(),
        remote_addr=(EC2_UDP_IP, EC2_UDP_PORT)
    )

    try:
        while True:
            try:
                frame = await frame_queue.get()
                if frame is None:
                    continue

                _, encoded_frame = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                encoded_frame = encoded_frame.tobytes()

                #print(len(encoded_frame))

                await send_frame(protocol, encoded_frame)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"error at main:142 : {e}")
    finally:
        capture_task.cancel()
        vs.stop()
        transport.close()
        cv2.destroyAllWindows()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await capture_task
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user. Exiting...")    