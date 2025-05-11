import platform
import os
import  queue
import socket
import time

system = platform.system()

def install_loop():
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

install_loop()

# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
if system == 'Windows' and os.path.exists(ffmpeg_bin):
    os.add_dll_directory(ffmpeg_bin)

import struct
import asyncio
import cv2
import contextlib
from zlib import crc32
''' 
    UDP Configuration
'''
EC2_UDP_IP = "127.0.0.1"
EC2_UDP_PORT = 8086
MAX_UDP_PACKET_SIZE = 60000  # Max safe UDP payload size
CAMERA_INDEX = 0             # Default camera index

''' Global Variable '''
frame_id_counter = 0

class UDPSender(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        sock: socket.socket = transport.get_extra_info('socket')

        default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"Default SO_sndbuf: {default_sndbuf} bytes")

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024 * 1024)

        new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"new SO_sndbuf: {new_sndbuf} bytes")

    def datagram_received(self, data, addr):
        print(f"Received from {addr}: ", data.decode())

    def send(self, data: bytes, addr):
        if self.transport:
            self.transport.sendto(data, addr)

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")


class VideoStream:
    def __init__(self, frame_queue:asyncio.Queue, src=0, desired_width=680,):
        api = cv2.CAP_MSMF if system =='Windows' else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(src, apiPreference=api)
        
        if not self.cap.isOpened():
            raise Exception("Error: Could not open webcam.")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.ret, self.frame = self.cap.read()
        self.frame_queue = frame_queue
        self.desired_width = desired_width
        self.running = True
    
    async def start(self):
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
                else:            
                    await self.frame_queue.put(frame.copy())
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"VideoStream start error: {e}")
        
        print("exited...")

    def stop(self):
        self.running = False
        self.cap.release()

async def encode_video(frame_queue: asyncio.Queue, encode_queue: asyncio.Queue):
    import av
    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = 1280
    encoder.height = 720
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 3000000  
    encoder.framerate = 30 
    encoder.options = {'tune': 'zerolatency'} 

    while True:
        try:
            frame = await frame_queue.get()

            img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
            encoded_packet = encoder.encode(video_frame) 

            if len(encoded_packet) == 0:
                continue

            encoded_packet_bytes = bytes(encoded_packet[0])
            if encode_queue.full():
                print("encode_queue full")
            else:
                await encode_queue.put(encoded_packet_bytes)
            await asyncio.sleep(0)
        except InterruptedError:
            break
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"error: {e}")
        
async def send_frame(protocol: UDPSender, encoded_frame: bytes, addr: tuple[str, int]):
    global frame_id_counter
    frame_id = frame_id_counter & 0xFFFF  # stay within 2 bytes
    frame_id_counter += 1

    # Break frame into chunks
    total_chunks = (len(encoded_frame) + MAX_UDP_PACKET_SIZE - 1) // MAX_UDP_PACKET_SIZE

    for chunk_index in range(total_chunks):
        start = chunk_index * MAX_UDP_PACKET_SIZE
        end = start + MAX_UDP_PACKET_SIZE
        chunk = encoded_frame[start:end]
        checksum = crc32(chunk)

        # Create header
        # Format: | frame_id (2 bytes) | total_chunks (1 byte) | chunk_index (1 byte) | crc32_checksum (4 bytes) |
        header = struct.pack("!HBBI", frame_id, total_chunks, chunk_index, checksum)

        protocol.send(header + chunk, addr)
        


async def main():
    frame_queue  = asyncio.Queue(maxsize=120)
    encode_queue = asyncio.Queue(maxsize=120)
    vs = VideoStream(frame_queue)

    capture_task = asyncio.create_task(vs.start())
    encode_task = asyncio.create_task(encode_video(frame_queue, encode_queue))

    loop = asyncio.get_running_loop()

    # Create UDP Client / Sender endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSender(),
        remote_addr=(EC2_UDP_IP, EC2_UDP_PORT)
    )

    frame_count = 0
    prev_time = time.monotonic()

    try:
        while True:
            try:
                encoded_frame = await encode_queue.get()
                await send_frame(protocol, encoded_frame, (EC2_UDP_IP, EC2_UDP_PORT))

                frame_count += 1
                now = time.monotonic()
                if now - prev_time >= 1.0:
                    fps = frame_count / (now - prev_time)
                    print(f"FPS: {fps:.2f}")
                    frame_count = 0
                    prev_time = now

                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"error {e}")
    finally:
        print("cancelling task......")
        encode_task.cancel()
        capture_task.cancel()
        vs.stop()
        transport.close()        
        cv2.destroyAllWindows()
    
        try:
            with contextlib.suppress(asyncio.CancelledError):
                print("awaiting encode_task")
                await encode_task
                print("encode_task ended")
            
                print("awaiting capture_task")
                await capture_task
                print("capture_task ended")
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        print("Program interrupted by user. Exiting...")
    