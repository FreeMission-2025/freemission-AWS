import asyncio
import struct
import time
from typing import Any, List

import cv2
import numpy as np
from zlib import crc32
import os

# Import ffmpeg
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)
import av

class DecodeVideo():
    ''' FFMPEG pyAV decoder'''
    def __init__(self,decode_queue: asyncio.Queue, frame_queue: List[asyncio.Queue]):
        self.decode_queue = decode_queue
        self.frame_queue = frame_queue

    async def decode (self):
        decoder = av.CodecContext.create('h264', 'r')
        loop = asyncio.get_running_loop()

        while True:
            try:
                if not self.decode_queue.empty():
                    encoded_packet_bytes = await self.decode_queue.get()
                else:
                    await asyncio.sleep(0.005)
                    continue

                packet = av.packet.Packet(encoded_packet_bytes)

                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 

                if len(decoded_video_frames) > 0:
                    decoded_video_frame = decoded_video_frames[0]
                    decoded_frame = decoded_video_frame.to_ndarray()
                    bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)
                    success, jpeg_encoded = cv2.imencode('.jpg', bgr_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if not success:
                        print("Failed to encode JPEG")
                        continue
                    
                    frame_bytes = jpeg_encoded.tobytes()
                    timestamped_frame = (time.time(), frame_bytes)

                    for q in self.frame_queue:
                        if not q.full():
                            q.put_nowait(timestamped_frame)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"error at decode_video: {e}")
    

class H264_TO_JPG_Protocol(asyncio.DatagramProtocol):
    ''' Base Class for Non Blocking UDP communication from Raspberry PI to AWS EC2 Server'''

    def __init__(self, decode_queue: asyncio.Queue):
        self.transport = None
        self.decode_queue = decode_queue
        self.frames_in_progress = {}

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

        print(f"UDP connection established")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        try:
            # Clean up old frames
            self.cleanup_old_frames(time.time())

            # Parse header
            frame_id, total_chunks, chunk_index, checksum = struct.unpack("!HBBI", data[:8])
            chunk_data = data[8:]

            computed_crc32 = crc32(chunk_data)
            if computed_crc32 != checksum:
                print(f"Checksum mismatch for {frame_id}, chunk {chunk_index}")

            if frame_id not in self.frames_in_progress:
                self.frames_in_progress[frame_id] = {
                    'chunks': [None] * total_chunks,
                    'received': 0,
                    'start_time': time.time(),
                }

            frame_entry = self.frames_in_progress[frame_id]
            if frame_entry['chunks'][chunk_index] is None:
                frame_entry['chunks'][chunk_index] = chunk_data
                frame_entry['received'] += 1

            if frame_entry['received'] == total_chunks:
                # All chunks received
                full_frame = b"".join(frame_entry['chunks'])

                # Cleanup
                del self.frames_in_progress[frame_id]

                if not self.decode_queue.full():
                    self.decode_queue.put_nowait(full_frame)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"Error in datagram_received: {e}")

    def cleanup_old_frames(self, now):
        """ Remove frames that are too old (>400ms) """
        TIMEOUT = 0.4  # 400ms
        expired_ids = [fid for fid, entry in self.frames_in_progress.items() if now - entry['start_time'] > TIMEOUT]
        
        for fid in expired_ids:
            print(f"Frame {fid} timeout. Discarded")
            del self.frames_in_progress[fid]


    def error_received(self, exc: Exception):
        print(f"Error received: {exc}")

    def connection_lost(self, exc: Exception):
        print("Closing connection")

class H264_TO_H264_Protocol(asyncio.DatagramProtocol):
    ''' Base Class for Non Blocking UDP communication from Raspberry PI to AWS EC2 Server'''

    def __init__(self, frame_queue: List[asyncio.Queue]):
        self.transport = None
        self.frame_queue = frame_queue
        self.frames_in_progress = {}


    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

        print(f"UDP connection established")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        try:
            # Clean up old frames
            self.cleanup_old_frames(time.time())

            # Parse header
            frame_id, total_chunks, chunk_index, checksum = struct.unpack("!HBBI", data[:8])
            chunk_data = data[8:]

            computed_crc32 = crc32(chunk_data)
            if computed_crc32 != checksum:
                print(f"Checksum mismatch for {frame_id}, chunk {chunk_index}")

            if frame_id not in self.frames_in_progress:
                self.frames_in_progress[frame_id] = {
                    'chunks': [None] * total_chunks,
                    'received': 0,
                    'start_time': time.time(),
                }

            frame_entry = self.frames_in_progress[frame_id]
            if frame_entry['chunks'][chunk_index] is None:
                frame_entry['chunks'][chunk_index] = chunk_data
                frame_entry['received'] += 1

            if frame_entry['received'] == total_chunks:
                # All chunks received
                full_frame = b"".join(frame_entry['chunks'])
                timestamped_frame = (time.time(), full_frame)

                # Cleanup
                del self.frames_in_progress[frame_id]
            
                for q in self.frame_queue:
                    if not q.full():
                        q.put_nowait(timestamped_frame)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"Error in datagram_received: {e}")

    def cleanup_old_frames(self, now):
        """ Remove frames that are too old (>400ms) """
        TIMEOUT = 0.4  # 400ms
        expired_ids = [fid for fid, entry in self.frames_in_progress.items() if now - entry['start_time'] > TIMEOUT]
        
        for fid in expired_ids:
            print(f"Frame {fid} timeout. Discarded")
            del self.frames_in_progress[fid]


    def error_received(self, exc: Exception):
        print(f"Error received: {exc}")

    def connection_lost(self, exc: Exception):
        print("Closing connection")
