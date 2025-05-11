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
import multiprocessing
import signal
''' 
    UDP Configuration
'''
EC2_UDP_IP = "127.0.0.1"
EC2_UDP_PORT = 8086
MAX_UDP_PACKET_SIZE = 60000  # Max safe UDP payload size
CAMERA_INDEX = 0             # Default camera index

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
    def __init__(self, frame_queue:multiprocessing.Queue, src=0, desired_width=680,):
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
    encoder.width = 1280
    encoder.height = 720
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 3000000  
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

            encoded_packet_bytes = bytes(encoded_packet[0])
            if not encode_queue.full():
                encode_queue.put_nowait(encoded_packet_bytes)
            else:
                print("encode_queue full")
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

    # Create UDP Client / Sender endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSender(),
        remote_addr=(EC2_UDP_IP, EC2_UDP_PORT)
    )

    frame_count = 0
    prev_time = time.monotonic()

    try:
        while keep_running:
            try:
                encoded_frame = await loop.run_in_executor(None, lambda: encode_queue.get(timeout=5))
                await send_frame(protocol, encoded_frame, (EC2_UDP_IP, EC2_UDP_PORT))

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
        transport.close()        
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
                print("awaiting capture_task")
                await capture_task
                print("capture_task ended")
                frame_queue.cancel_join_thread()
                encode_queue.cancel_join_thread()
                frame_queue.close()
                encode_queue.close()
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        print("Program interrupted by user. Exiting...")
    