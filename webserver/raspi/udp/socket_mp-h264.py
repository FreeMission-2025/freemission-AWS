from collections import deque
import heapq
import platform
import os
import  queue
import socket
import time
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
    UDP Configuration
'''
EC2_UDP_IP = "127.0.0.1"
EC2_UDP_PORT = 8086
MAX_UDP_PACKET_SIZE = 1450  # Max safe UDP payload size
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

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s B"       # | 4-byte marker | 3-byte frame_id | 1-byte chunk_index |
ACK_SIZE      = struct.calcsize(ACK_FORMAT)


class UDPSender(asyncio.DatagramProtocol):
    def __init__(self, window_size=30, timeout=100):
        self.transport     = None
        self._send_queue   = deque()         # (fid, idx, packet)
        self._pending      = {}              # (fid,idx) -> (packet, last_send_ms)
        self._heap = []     # list of (next_retransmit_time_ms, fid, idx)
        self.window_size   = window_size
        self.timeout       = timeout
        self._window_task  = None
        self._resend_task  = None
        self._heap_task    = None
        self.loop          = asyncio.get_event_loop()
    
    async def _heap_maintenance(self):
        while True:
            try:
                await asyncio.sleep(30)
                print("heap_")
                now = time.time()
                await self._compact_heap()
                print(f"took {time.time() - now:.4f}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in _heap_maintenance: {e}")

    async def _compact_heap(self):
        self._heap = [(t, f, i) for (t, f, i) in self._heap if (f, i) in self._pending]
        await self.loop.run_in_executor(None, lambda: heapq.heapify(self._heap))

    def connection_made(self, transport):
        self.transport = transport
        loop = asyncio.get_event_loop()

        sock: socket.socket = transport.get_extra_info('socket')

        default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"Default SO_sndbuf: {default_sndbuf} bytes")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024 * 1024)
        new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"new SO_sndbuf: {new_sndbuf} bytes")

        if self._window_task is None:
            self._window_task = loop.create_task(self._window_sender())
        if self._resend_task is None:
            self._resend_task = loop.create_task(self._retransmitter())
        if self._heap_task is None:
            self._heap_task = loop.create_task(self._heap_maintenance())
        

    def send(self, data: bytes):
        """Send via preconfigured EC2_UDP_IP/PORT."""
        if self.transport:
            self.transport.sendto(data, (EC2_UDP_IP, EC2_UDP_PORT))

    def enqueue_chunk(self, fid: int, idx: int, packet: bytes):
        """Call this from your send_frame() instead of directly sending."""
        self._send_queue.append((fid, idx, packet))


    async def _window_sender(self):
        while True:
            try:
                # fill up to window_size
                while len(self._pending) < self.window_size and self._send_queue:
                    fid, idx, packet = self._send_queue.popleft()
                    self.send(packet)
                    now = int(time.time() * 1000)
                    self._pending[(fid, idx)] = (packet, now)
                    heapq.heappush(self._heap, (now + self.timeout, fid, idx))
                await asyncio.sleep(0.015)  # 1 ms tick
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"error at _window_sender {e}")

    async def _retransmitter(self):
        while True:
            try:
                now = int(time.time() * 1000)

                while self._heap:
                    next_time, fid, idx = self._heap[0]
                    if next_time > now:
                        break

                    heapq.heappop(self._heap)
                    key = (fid, idx)
                    if key in self._pending:
                        packet, last_send_time = self._pending[key]
                        elapsed = now - last_send_time
                        print(f"Retransmit frame={key[0]} chunk={key[1]} elapsed={elapsed}ms")

                        self.send(packet)
                        self._pending[key] = (packet, now)  # update send time
                        heapq.heappush(self._heap, (now + self.timeout, fid, idx))
                
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"error at _retransmitter {e}")

    def datagram_received(self, data: bytes, addr):
        # single method handles both ACKs and normal datagrams
        if len(data) == ACK_SIZE and data.startswith(ACK_MARKER):
            _, fid_bytes, chunk_idx = struct.unpack(ACK_FORMAT, data)
            key = (int.from_bytes(fid_bytes, 'big'), chunk_idx)
            if key in self._pending:
                del self._pending[key]
            #print(f"ACK received: frame={key[0]} chunk={key[1]}")
        else:
            # any other inbound message
            print(f"Received from {addr}: {data!r}")

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")
        if self._window_task:
            self._window_task.cancel()  
        if self._resend_task:
            self._resend_task.cancel()
        if self._heap_task:
            self._heap_task.cancel()



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

# Updated header format: 4s (marker), I (Time Stamp), 3s (frame_id), B (total_chunks), B (chunk_index), H (chunk_length), I (checksum)
HEADER_FORMAT = "!4s I 3s B B H I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = MAX_UDP_PACKET_SIZE - HEADER_SIZE - len(END_MARKER)

async def send_frame(protocol: UDPSender, encoded_frame: bytes):
    global frame_id_counter
    frame_id = frame_id_counter
    frame_id_b = (frame_id & 0xFFFFFF).to_bytes(3, 'big')  # Stay within 3 bytes (24-bit)
    frame_id_counter += 1

    # Break frame into chunks
    #print(len(encoded_frame))
    total_chunks = (len(encoded_frame) + MAX_PAYLOAD_SIZE - 1) // MAX_PAYLOAD_SIZE

    # Convert time to milliseconds and make sure it's an integer (for 4-byte format)
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
        protocol.enqueue_chunk(frame_id, chunk_index, header + chunk + END_MARKER)

        
        # Debugging: print out the unpacked header data
        '''        
        print(f"Start Marker: {START_MARKER}")
        print(f"Timestamp: {time_ms}")
        print(f"Frame ID (int): {int.from_bytes(frame_id, byteorder='big')}")
        print(f"Total Chunks: {total_chunks}")
        print(f"Chunk Index: {chunk_index}")
        print(f"Chunk Length: {chunk_length}")
        print(f"Checksum: {checksum}")
        print(f"End Marker: {END_MARKER}")
        '''
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

    url = "http://localhost:80/reset_stream"
    headers = {"Content-Type": "application/json"}
    data = {
        "message": "INIT_STREAM",
        "auth": "BAYU"
    }
    response = requests.post(url, json=data, headers=headers)
    print(response.status_code)
    print(response.json())

    await asyncio.sleep(5)

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
                await send_frame(protocol, encoded_frame)

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
    