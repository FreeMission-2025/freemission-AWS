import asyncio
import cv2
import os
import numpy as np
import time
from typing import List
from inference import ShmQueue
from .base import BaseConsumer
from utils.logger import Log
from constants import FFMPEG_DIR, SHOW_FPS

# Import ffmpeg
if os.path.exists(FFMPEG_DIR):
    os.add_dll_directory(FFMPEG_DIR)
import av

class H264_TO_JPG_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue]):
        super().__init__(output_queue)
        self.frame_queue = frame_queue
        self.frame_count = 0
        self.prev_time = time.monotonic()

    async def process_handler(self, np_array: np.ndarray):
        _, buffer = cv2.imencode(".jpg", np_array, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        frame_bytes = buffer.tobytes()

        timestamped_frame = (time.time(), frame_bytes)
        for q in self.frame_queue:
            if not q.full():
                q.put_nowait(timestamped_frame)
        
        if SHOW_FPS:
            self.frame_count += 1
            now = time.monotonic()
            total_time = now - self.prev_time
            if total_time >= 1.0:
                fps = self.frame_count / total_time
                print(f"FPS: {fps:.2f}")
                self.frame_count = 0
                self.prev_time = now

class H264_TO_H264_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue], encode_queue: asyncio.Queue):
        super().__init__(output_queue)
        self.frame_queue = frame_queue
        self.encode_queue = encode_queue
        self.frame_count = 0
        self.prev_time = time.monotonic()

    async def process_handler(self, np_array: np.ndarray):
        if not self.encode_queue.full():
            self.encode_queue.put_nowait(np_array)
    
    async def encode(self):
        encoder = av.CodecContext.create('libx264', 'w')
        encoder.width = 1280
        encoder.height = 720
        encoder.pix_fmt = 'yuv420p'
        encoder.bit_rate = 3000000  
        encoder.framerate = 30 
        encoder.options = {'tune': 'zerolatency'} 

        while True:
            try:
                frame_bgr = await self.encode_queue.get()

                img_yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV_I420)
                video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')

                #start = time.perf_counter()
                encoded_packet = await self.loop.run_in_executor(None, lambda: encoder.encode(video_frame))
                #print(f"enc: {time.perf_counter() - start:.4f}s")

                if len(encoded_packet) == 0:
                    continue
                
                timestamped_frame = (time.time(), bytes(encoded_packet[0]))
                for q in self.frame_queue:
                    if not q.full():
                        q.put_nowait(timestamped_frame)

                if SHOW_FPS:
                    self.frame_count += 1
                    now = time.monotonic()
                    total_time = now - self.prev_time
                    if total_time >= 1.0:
                        fps = self.frame_count / total_time
                        print(f"FPS: {fps:.2f}")
                        self.frame_count = 0
                        self.prev_time = now

                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                Log.exception(f"error at encode: {e}")
    



