import asyncio
from fractions import Fraction
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

HOST = '16.78.8.232'
PORT = 8088
WIDTH, HEIGHT = 640, 480

# Custom protocol markers
START_MARKER = b'\x01\x02\x7F\xED'
END_MARKER   = b'\x03\x04\x7F\xED'
HEADER_FORMAT = "!4s I 3s I I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s"       # | 4-byte marker | 3-byte frame_id
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

def set_sock_props(writer: asyncio.StreamWriter):
    """Modify socket properties"""
    sock: socket.socket = writer.get_extra_info('socket')
    if sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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

   
async def async_packet_generator(demuxer) -> AsyncGenerator[Packet, None]:
    """Wrap blocking demux generator in async-friendly way."""
    for packet in demuxer:
        yield packet
        await asyncio.sleep(0)

def build_payload(encoded: bytes, frame_id: int) -> bytes:
    """Builds a complete message with header and markers."""
    frame_id_b = (frame_id & 0xFFFFFF).to_bytes(3, 'big')
    time_ms = int(time.time() * 1000) % 0x100000000
    checksum = crc32(encoded)
    chunk_length = len(encoded)
    header = struct.pack(HEADER_FORMAT, START_MARKER, time_ms, frame_id_b, chunk_length, checksum)
    return header + encoded + END_MARKER

async def message_received(reader: asyncio.StreamReader):
    while True:
        try:
            data = b''
            while len(data) < ACK_SIZE:
                chunk = await reader.read(ACK_SIZE - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed unexpectedly")
                data += chunk

            if data.startswith(ACK_MARKER) and len(data) == ACK_SIZE:
                _, fid_bytes = struct.unpack(ACK_FORMAT, data)
                frame_id = int.from_bytes(fid_bytes, 'big')
                print(f"ACK received for frame: {frame_id}")
            else:
                try:
                    print(f"Received data: {data.decode()!r}")
                except Exception as e:
                    print(f"error: {e}")

            await asyncio.sleep(0)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in message_received: {e}")
            continue


async def main():
    frame_id_counter = 0

    # Open video device
    container = av.open(
        '/dev/video0', format='v4l2',
        options={
            'video_size': f'{WIDTH}x{HEIGHT}',
            'framerate': '25',
            'input_format': 'h264', 'use_wallclock_as_timestamps': '1',
             '-an': ' ', 'fflags': '+genpts', 'avoid_negative_ts': 'make_zero',
            'copytb': '1', 'c': 'copy', 'f': 'h264',
        }
    )

    video_stream = next((s for s in container.streams if s.type == 'video'), None)
    if video_stream is None:
        raise RuntimeError("No video stream found")

    reader, writer = await asyncio.open_connection(HOST, PORT)
    set_sock_props(writer)
    print("Connected to server. Starting frame capture...")

    frame_count = 0
    prev_time = time.monotonic()
    frame_queue = asyncio.Queue()

    # Capture Task
    async def capture():
        time_base_backup = Fraction (1/1000000)
        pts_backup = 0
        try:
            async for packet in async_packet_generator(container.demux(video_stream)):
                if packet.stream.type == 'video':
                    if packet.pts is None:
                        packet.pts = pts_backup
                        pts_backup += 1
                    if packet.time_base is None:
                       packet.time_base = time_base_backup

                    frame_type = 1 if packet.is_keyframe else 0

                    # Structure: time_base.num (8) | time_base.den (8) | pts (8) | dts (8) | frame_type (1) | duration(4) | raw H.264 (N Byte)
                    nume = packet.time_base.numerator
                    denu = packet.time_base.denominator
                    pts  = packet.pts if packet.pts is not None else 0
                    dts  = packet.dts if packet.dts is not None else 0
                    duration = packet.duration if packet.duration is not None else 0

                    chunk = struct.pack(">QQqqBI", nume, denu, pts, dts, frame_type, duration)
                    packet_data = chunk + bytes(packet)
                    frame_queue.put_nowait(packet_data)
                
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            return
        except asyncio.CancelledError:
            return

    capture_task = asyncio.create_task(capture())
    recv_task = asyncio.create_task(message_received(reader))

    while True:
        try:
            # Convert to BGR24 for JPEG encoding
            encoded = await frame_queue.get()
            payload = build_payload(encoded, frame_id_counter)
            frame_id_counter += 1

            # Print performance
            frame_count += 1
            now = time.monotonic()

            # Send frame
            writer.write(payload)
            await writer.drain()

            if now - prev_time >= 1.0:
                fps = frame_count / (now - prev_time)
                print(f"FPS: {fps:.2f}")
                frame_count = 0
                prev_time = now
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            break
        
    for task in (capture_task, recv_task):
        task.cancel()
        await task
        
    await asyncio.gather(capture_task, recv_task)
    writer.close()
    await writer.wait_closed()
    container.close()
    print("Shutdown complete.")
    
if __name__ == '__main__':
    try:
       asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted. Exiting.")
    except asyncio.CancelledError:
        print("Program interrupted. Exiting.")