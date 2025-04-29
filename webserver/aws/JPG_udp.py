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

class JPG_TO_JPG_PROTOCOL(asyncio.DatagramProtocol):
    ''' Base Class for Non Blocking UDP communication from Raspberry PI to AWS EC2 Server'''

    def __init__(self, frame_queue: List[asyncio.Queue] ):
        self.transport = None
        self.frame_queue = frame_queue
        self.frames_in_progress = {}

        # Wheter we allow partial frames to be processed with null bytes, then try to decode. 
        # or straight up discard
        self.ALLOW_PARTIAL = True

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

                # Decode frame
                np_arr = np.frombuffer(full_frame, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if frame is None:
                    print("Error: Failed to decode reassembled frame.")
                    return

                _, buffer = cv2.imencode(".jpg", frame)
                frame_bytes = buffer.tobytes()

                timestamped_frame = (time.time(), frame_bytes)
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

class EncodeVideo():
    ''' FFMPEG pyAV encoder'''
    def __init__(self,encode_queue: asyncio.Queue, frame_queue: List[asyncio.Queue]):
        self.encode_queue = encode_queue
        self.frame_queue = frame_queue

    async def encode (self):
        encoder = av.CodecContext.create('libx264', 'w')
        encoder.width = 1280
        encoder.height = 720
        encoder.pix_fmt = 'yuv420p'
        encoder.bit_rate = 3000000  
        encoder.framerate = 30 
        encoder.options = {'tune': 'zerolatency'} 
        loop = asyncio.get_running_loop()

        while True:
            try:
                if not self.encode_queue.empty():
                    frame = await self.encode_queue.get()
                else:
                    await asyncio.sleep(0)
                    continue

                if frame is None:
                    continue

                np_array = np.frombuffer(frame, dtype=np.uint8)
                img_bgr = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

                if img_bgr is None:
                    continue

                img_yuv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YUV_I420)
                video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
                encoded_packet = await loop.run_in_executor(None, lambda: encoder.encode(video_frame))

                if len(encoded_packet) == 0:
                    continue
                
                timestamped_frame = (time.time(), bytes(encoded_packet[0]))
                for q in self.frame_queue:
                    if not q.full():
                        q.put_nowait(timestamped_frame)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"error at encode: {e}")
    

class JPG_TO_H264_PROTOCOL(asyncio.DatagramProtocol):
    ''' Base Class for Non Blocking UDP communication from Raspberry PI to AWS EC2 Server'''

    def __init__(self, encode_queue: asyncio.Queue ):
        self.transport = None
        self.encode_queue = encode_queue
        self.frames_in_progress = {}

        # Wheter we allow partial frames to be processed with null bytes, then try to decode. 
        # or straight up discard
        self.ALLOW_PARTIAL = True

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

                if not self.encode_queue.full():
                    self.encode_queue.put_nowait(full_frame)
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
