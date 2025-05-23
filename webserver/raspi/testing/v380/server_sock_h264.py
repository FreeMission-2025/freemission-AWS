# server_decoder_display.py
import os
import socket

# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
if os.path.exists(ffmpeg_bin):
    os.add_dll_directory(ffmpeg_bin)

import socket
import struct
import av
import cv2
import numpy as np

HOST = '0.0.0.0'
PORT = 8082

def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        more = sock.recv(size - len(data))
        if not more:
            raise ConnectionError("Socket closed")
        data += more
    return data


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
    server_sock.bind((HOST, PORT))
    server_sock.listen(1)
    print(f"Listening on {HOST}:{PORT}...")
    conn, addr = server_sock.accept()
    print(f"Connected by {addr}")

    codec = av.CodecContext.create('h264', 'r')

    try:
        while True:
            # Read 4-byte packet length
            raw_len = recv_exact(conn, 4)
            pkt_len = struct.unpack('>I', raw_len)[0]

            # Read the actual packet
            pkt_data = recv_exact(conn, pkt_len)

            print(f"length:{len(pkt_data)}")

            packet = av.packet.Packet(pkt_data)
            frames = codec.decode(packet)

            for frame in frames:
                img = frame.to_ndarray(format='bgr24')
                cv2.imshow('Video', img)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    raise KeyboardInterrupt

    except (KeyboardInterrupt, ConnectionError):
        print("Stopping...")
    finally:
        conn.close()
        cv2.destroyAllWindows()

'''
    Client Implementation
'''

'''
from fractions import Fraction
import socket
import struct
import av
import av.utils

HOST = '192.168.18.48'
PORT = 8082

input_container = av.open(
    '/dev/video0',
    format='v4l2',
    options={
        'video_size': '1280x720',
        'framerate': '25',
        'input_format': 'h264',
        'use_wallclock_as_timestamps': '1',
        'fflags': '+genpts',
        'avoid_negative_ts': 'make_zero',
        'copytb': '1',
        'c': 'copy',
        'f': 'h264',
    }
)

video_stream = None
for stream in input_container.streams:
    if stream.type == 'video':
        video_stream = stream
        break

if video_stream:
    print(f"Codec name: {video_stream.codec_context.name}")
    print(f"Codec long name: {video_stream.codec_context.codec.long_name}")
else:
    print("No video stream found.")


frame_index = 0

with socket.create_connection((HOST, PORT)) as sock:
    for packet in input_container.demux(video_stream):
        if packet.stream.type == 'video':
            packet_b = bytes(packet)
            print(f"pts: {packet.pts},dts: {packet.dts}, time_base: {packet.time_base},dur: {packet.duration}, fps:{1 / (packet.duration * packet.time_base)}, {packet_b[:10].hex()}")
            length = len(packet_b)
            # Send length prefix (4 bytes) followed by raw H264 packet
            sock.sendall(struct.pack('>I', length) + packet_b)

input_container.close()
'''
