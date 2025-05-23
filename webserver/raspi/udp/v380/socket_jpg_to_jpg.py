import asyncio
import subprocess
from typing import AsyncGenerator
import av
from av import Packet
import socket
import struct
import time
import platform
from zlib import crc32
from av.video.frame import VideoFrame
import cv2
import requests

HOST = '192.168.18.48'
PORT = 8085
MAX_UDP_PACKET_SIZE = 1450  #
WIDTH, HEIGHT = 640, 480
JPEG_QUALITY = 50

# Custom protocol markers
START_MARKER = b'\x01\x02\x7F\xED'
END_MARKER   = b'\x03\x04\x7F\xED'

# Updated header format: 4s (marker), I (Time Stamp), 3s (frame_id), B (total_chunks), B (chunk_index), H (chunk_length), I (checksum)
HEADER_FORMAT = "!4s I 3s B B H I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = MAX_UDP_PACKET_SIZE - HEADER_SIZE - len(END_MARKER)

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s B"       # | 4-byte marker | 3-byte frame_id | 1-byte chunk_index |
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

frame_id_counter = 0

class UDPSender(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        sock:socket.socket = transport.get_extra_info('socket')
        
        if sock:
            default_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            print(f"Default SO_RCVBUF: {default_rcvbuf} bytes")
            print(f"Default SO_RCVBUF: {default_sndbuf} bytes")

            platforms = platform.system()
            original_rmem_max = 0
            original_wmem_max = 0

            if platforms == "Linux":
                original_rmem_max = subprocess.check_output(["sysctl", "net.core.rmem_max"]).decode().strip().split('=')[1]
                print(f"Original rmem_max: {original_rmem_max} bytes")
                print("Setting new rmem_max to 32 mb")
                subprocess.run(["sysctl", "-w", "net.core.rmem_max=33554432"], check=True)

                original_wmem_max = subprocess.check_output(["sysctl", "net.core.wmem_max"]).decode().strip().split('=')[1]
                print(f"Original wmem_max: {original_wmem_max} bytes")
                print("Setting new wmem_max to 32 mb")
                subprocess.run(["sysctl", "-w", "net.core.wmem_max=33554432"], check=True)


            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024 * 1024)

            if platforms == "Linux":
                if original_rmem_max != 0:
                    print("Restoring default value of rmem_max")
                    subprocess.run(["sysctl", "-w", f"net.core.rmem_max={original_rmem_max}"], check=True)
                if original_wmem_max != 0:
                    print("Restoring default value of wmem_max")
                    subprocess.run(["sysctl", "-w", f"net.core.wmem_max={original_wmem_max}"], check=True)

            new_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            print(f"new SO_RCVBUF: {new_rcvbuf} bytes")
            print(f"new new_sndbuf: {new_sndbuf} bytes")


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
            self.transport.sendto(data, (HOST, PORT))

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")

async def async_packet_generator(demuxer) -> AsyncGenerator[VideoFrame, None]:
    """Wrap blocking demux generator in async-friendly way."""
    for packet in demuxer:
        yield packet
        await asyncio.sleep(0)

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
        protocol.send(header + chunk + END_MARKER)

async def main():
    url = f"http://{HOST}:80/reset_stream"
    headers = {"Content-Type": "application/json"}
    data = {
        "message": "INIT_STREAM",
        "auth": "BAYU"
    }
    response = requests.post(url, json=data, headers=headers)
    print(response.status_code)
    print(response.json())
    await asyncio.sleep(3)

    # Open video device
    container = av.open(
        '/dev/video0', format='v4l2',
        options={
            'video_size': f'{WIDTH}x{HEIGHT}',
            'framerate': '30',
            'input_format': 'mjpeg',
        }
    )

    video_stream = next((s for s in container.streams if s.type == 'video'), None)
    if video_stream is None:
        raise RuntimeError("No video stream found")

    # Create UDP Client / Sender endpoint
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSender(),
        remote_addr=(HOST, PORT)
    )

    frame_count = 0
    prev_time = time.monotonic()
    frame_queue = asyncio.Queue()

    # Capture Task
    async def capture():
        try:
            async for packet in async_packet_generator(container.decode(video_stream)):
                # Convert to BGR24 for JPEG encoding
                bgr = packet.to_ndarray(format='bgr24')
                ret, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ret:
                    frame_queue.put_nowait(jpeg.tobytes())
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            return
        except asyncio.CancelledError:
            return

    capture_task = asyncio.create_task(capture())
    while True:
        try:
            # Convert to BGR24 for JPEG encoding
            encoded = await frame_queue.get()
            await send_frame(protocol, encoded_frame=encoded)

            # Print performance
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
        
    transport.close()
    capture_task.cancel()  
    container.close()      
    await asyncio.gather(capture_task)
    print("Shutdown complete.")
    
if __name__ == '__main__':
    try:
       asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted. Exiting.")
    except asyncio.CancelledError:
        print("Program interrupted. Exiting.")