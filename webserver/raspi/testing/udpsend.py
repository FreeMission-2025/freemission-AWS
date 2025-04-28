import asyncio
import os
import re
import subprocess
from typing import Optional, Pattern

# Configuration
UDP_IP = "127.0.0.1"
UDP_PORT = 8085
MAX_UDP_PACKET_SIZE = 65507  # Max safe UDP payload size
CAMERA_INDEX = 0  # Default camera index

class UDPSender(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def send(self, data: bytes, addr):
        if self.transport:
            self.transport.sendto(data, addr)

    def error_received(self, exc):
        print(f"Error received: {exc}")

    def connection_lost(self, exc):
        print("Connection closed")


async def stream_video_udp():
    loop = asyncio.get_running_loop()

    # Create UDP sender endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSender(),
        remote_addr=(UDP_IP, UDP_PORT)
    )

    ffmpeg_path = os.path.join("C:", "ffmpeg", "bin", "ffmpeg.exe")
    device_name = 'USB2.0 FHD UVC WebCam'

    ffmpeg_command = [
        ffmpeg_path,
        '-f', 'dshow',
        '-i', f'video={device_name}',
        '-s', '1280x720',
        '-c:v', 'libx264',
        '-tune', 'zerolatency',
        '-r', '30',
        '-b:v', '3M',
        '-an',
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'high',
        '-level', '4',
        '-f', 'h264',
        '-'
    ]

    try:
        encoder_process = await asyncio.create_subprocess_exec(
            *ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )
    except FileNotFoundError:
        print("FFmpeg not found.")
        return
    except Exception as e:
        print(f"Failed to start ffmpeg: {e}")
        return

    complete_frame_data = b''
    nal_start_code_pattern: Pattern[bytes] = re.compile(b'\x00\x00\x00\x01')

    while True:
        try:
            new_encoded_data: bytes = await encoder_process.stdout.read(607200)
        except Exception as e:
            print(f"Read error: {e}")
            break

        if not new_encoded_data:
            print("FFmpeg stopped producing output.")
            break

        matches = list(nal_start_code_pattern.finditer(new_encoded_data))
        if not matches:
            complete_frame_data += new_encoded_data
            continue

        for idx, match in enumerate(matches):
            nal_type = new_encoded_data[match.end()] & 0x1F

            if idx == 0 and match.start() != 0:
                complete_frame_data += new_encoded_data[:match.start()]

            if complete_frame_data:
                if nal_type == 1:
                    if len(complete_frame_data) <= MAX_UDP_PACKET_SIZE:
                        protocol.send(complete_frame_data, (UDP_IP, UDP_PORT))
                        print(f"Sent frame: {len(complete_frame_data)} bytes")
                    else:
                        print(f"Frame too large: {len(complete_frame_data)} bytes — skipping.")

                    complete_frame_data = b''

            # Accumulate next chunk
            if idx == len(matches) - 1:
                complete_frame_data += new_encoded_data[match.start():]
            else:
                next_start = matches[idx + 1].start()
                complete_frame_data += new_encoded_data[match.start():next_start]

        await asyncio.sleep(0)

    encoder_process.terminate()
    transport.close()
    print("Streaming ended.")

asyncio.run(stream_video_udp())
