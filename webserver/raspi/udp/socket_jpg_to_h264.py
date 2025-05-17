from collections import deque
import heapq
import platform
import socket
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
        sock: socket.socket = transport.get_extra_info('socket')
        
        loop = asyncio.get_event_loop()
        if sock is not None:        
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
    frame_id = frame_id_counter
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
        protocol.enqueue_chunk(frame_id, chunk_index, header + chunk + END_MARKER)

async def main():
    url = "http://127.0.0.1:80/reset_stream"
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

                _, encoded_frame = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
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