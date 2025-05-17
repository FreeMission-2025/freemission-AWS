from dataclasses import dataclass
import platform
import socket
import struct
import time
from typing import Optional

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
    TCP Configuration
'''
EC2_TCP_IP = "127.0.0.1"
EC2_TCP_PORT = 8087
CAMERA_INDEX = 0


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

# Updated header format: 4s (marker), I (Time Stamp), 3s (frame_id), I (chunk_length), I (checksum)
HEADER_FORMAT = "!4s I 3s I I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s"       # | 4-byte marker | 3-byte frame_id
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

class protocol:
    def __init__(self):
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
tcp = protocol()

async def message_received():
    while True:
        try:
            data = await tcp.reader.read(7)

            # single method handles both ACKs and normal datagrams
            if len(data) == ACK_SIZE and data.startswith(ACK_MARKER):
                _, fid_bytes = struct.unpack(ACK_FORMAT, data)
                key = int.from_bytes(fid_bytes, 'big')
                print(f"ACK received: frame={key}")
            else:
                print(f"Received : {data.decode()!r}")
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"error at videmessage_receivedo_stream: {e}")

async def send_frame(encoded_frame: bytes):
    global frame_id_counter
    frame_id = frame_id_counter
    frame_id_b = (frame_id & 0xFFFFFF).to_bytes(3, 'big')  # Stay within 3 bytes (24-bit)
    frame_id_counter += 1

    chunk_length = len(encoded_frame)
    time_ms = int(time.time() * 1000) % 0x100000000
    checksum = crc32(encoded_frame)

    # | START_MARKER (4 bytes) | timestamp (4 bytes) | frame_id (3 bytes) | chunk_length (4 bytes) | crc32_checksum (4 bytes) |
    header = struct.pack(HEADER_FORMAT, START_MARKER, time_ms, frame_id_b, chunk_length, checksum)

    # Send the header + chunk + END_MARKER
    tcp.writer.write(header + encoded_frame + END_MARKER)
    await tcp.writer.drain()

async def main():
    frame_queue = asyncio.Queue(maxsize=120)
    vs = VideoStream(frame_queue)

    capture_task = asyncio.create_task(vs.start())

    tcp.reader, tcp.writer = await asyncio.open_connection(EC2_TCP_IP, EC2_TCP_PORT, flags=socket.TCP_NODELAY)
    sock:socket.socket = tcp.writer.get_extra_info('socket')
    
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tcp_nodelay = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        print(f"TCP_NODELAY after setting: {tcp_nodelay}")

        # Set send and receive buffer sizes on both client and server
        bufsize = 32 * 1024 * 1024  # 32MB

        default_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"Default SO_RCVBUF: {default_rcvbuf}")
        print(f"Default SO_SNDBUF: {default_sndbuf}")

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, bufsize)

        new_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"New SO_RCVBUF: {new_rcvbuf}")
        print(f"New SO_SNDBUF: {new_sndbuf}")
    else:
        print("Could not get socket from writer")    

    receive_task = asyncio.create_task(message_received())
    print("got connection")
    try:
        while True:
            try:
                frame = await frame_queue.get()
                if frame is None:
                    continue

                _, encoded_frame = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                encoded_frame = encoded_frame.tobytes()

                #print(len(encoded_frame))
                await send_frame(encoded_frame)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"error at main:142 : {e}")
    finally:
        capture_task.cancel()
        vs.stop()
        receive_task.cancel()
        tcp.writer.close()
        await tcp.writer.wait_closed()
        cv2.destroyAllWindows()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await capture_task
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await receive_task
        except Exception as e:
            print(f"Error occurred while canceling receive_task: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user. Exiting...")    