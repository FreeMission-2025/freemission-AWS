from collections import deque
import heapq
import platform
import os
import  queue
import socket
import time
from typing import Optional
import requests

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
import multiprocessing
import signal
''' 
    TCP Configuration
'''
EC2_TCP_IP = "127.0.0.1"
EC2_TCP_PORT = 8088
CAMERA_INDEX = 0

''' Global Variable '''
frame_id_counter = 0

# Shutdown event
keep_running = True
def handle_exit_signal(signum, frame):
    print(f"\nReceived signal {signum}, shutting down...")
    global keep_running
    keep_running = False

signal.signal(signal.SIGINT, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)

class VideoStream:
    def __init__(self, frame_queue:multiprocessing.Queue, src=0, desired_width=680,):
        api = cv2.CAP_MSMF if system =='Windows' else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(src, apiPreference=api)
        
        if not self.cap.isOpened():
            raise Exception("Error: Could not open webcam.")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

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
                if not self.frame_queue.full():
                    self.frame_queue.put_nowait(frame.copy())
                else:
                    print("frame_queue full")
                    if not keep_running:
                        break

                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"VideoStream start error: {e}")
        
        print("exited...")

    def stop(self):
        self.running = False
        self.cap.release()

async def encode_video(frame_queue: multiprocessing.Queue, encode_queue: multiprocessing.Queue):
    import av
    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = 640
    encoder.height = 480
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 2000000  
    encoder.framerate = 30 
    encoder.options = {'tune': 'zerolatency'} 

    while True:
        try:
            frame = frame_queue.get()

            img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
            encoded_packet = encoder.encode(video_frame) 

            if len(encoded_packet) == 0:
                continue

            timestamp_us = int(encoded_packet[0].pts * encoded_packet[0].time_base * 1_000_000)
            frame_type = 1 if encoded_packet[0].is_keyframe else 0

            # Chunk Data: timestamp (8 byte) || frame_type (1 byte) || raw H.264  (N byte)
            packet_data = struct.pack(">QB", timestamp_us, frame_type) + bytes(encoded_packet[0])

            if not encode_queue.full():
                encode_queue.put_nowait(packet_data)
            else:
                print("encode_queue full")
        except InterruptedError:
            break
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"error: {e}")
            
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


def async_encode(frame_queue: multiprocessing.Queue, encode_queue: multiprocessing.Queue):
    install_loop()
    try:
        asyncio.run(encode_video(frame_queue, encode_queue))
    except KeyboardInterrupt:
        print("exiting...")
    except SystemExit:
        print("exiting...")


async def main():
    if system == 'Windows':
        multiprocessing.set_start_method('spawn')

    frame_queue  = multiprocessing.Queue(120)
    encode_queue = multiprocessing.Queue(120)
    vs = VideoStream(frame_queue)
    capture_task = asyncio.create_task(vs.start())

    encode_process = multiprocessing.Process(target=async_encode, args=(frame_queue,encode_queue))
    encode_process.start()

    loop = asyncio.get_running_loop()

    tcp.reader, tcp.writer = await asyncio.open_connection(EC2_TCP_IP, EC2_TCP_PORT)
    receive_task = asyncio.create_task(message_received())
    print("got connection")

    frame_count = 0
    prev_time = time.monotonic()

    try:
        while keep_running:
            try:
                encoded_frame = await loop.run_in_executor(None, lambda: encode_queue.get(timeout=5))
                await send_frame(encoded_frame)

                frame_count += 1
                now = time.monotonic()
                if now - prev_time >= 1.0:
                    fps = frame_count / (now - prev_time)
                    print(f"FPS: {fps:.2f}")
                    frame_count = 0
                    prev_time = now

                await asyncio.sleep(0)
            except queue.Empty:
                continue
            except asyncio.CancelledError:
                break
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        print("cancelling task......")
        capture_task.cancel()
        vs.stop()
        receive_task.cancel()
        tcp.writer.close()
        await tcp.writer.wait_closed()     
        cv2.destroyAllWindows()

        try:
            if encode_process.is_alive():
                os.kill(encode_process.pid, signal.SIGINT)
        except Exception as e:
            print(e)

        encode_process.join(2)
        if encode_process.is_alive():
            print("terminating encode_proccess")
            encode_process.terminate()
        encode_process.join(3)
        if encode_process.is_alive():
            print("killing encode_proccess")
            encode_process.kill()
        encode_process.join(2)

        try:
            with contextlib.suppress(asyncio.CancelledError):
                await capture_task
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")

        frame_queue.cancel_join_thread()
        encode_queue.cancel_join_thread()
        frame_queue.close()
        encode_queue.close()

        try:
            with contextlib.suppress(asyncio.CancelledError):
                await receive_task
        except Exception as e:
            print(f"Error occurred while canceling receive_task: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        print("Program interrupted by user. Exiting...")
    