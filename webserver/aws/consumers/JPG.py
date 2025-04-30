import asyncio
import numpy as np
import cv2
import time
import os
from typing import List
from inference import ShmQueue
from .base import BaseConsumer

# Import ffmpeg
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)
import av

class JPG_TO_JPG_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue]):
        super().__init__(output_queue)
        self.frame_queue = frame_queue
    
    async def process_handler(self, np_array: np.ndarray):
        _, buffer = cv2.imencode(".jpg", np_array)
        frame_bytes = buffer.tobytes()

        timestamped_frame = (time.time(), frame_bytes)
        for q in self.frame_queue:
            if not q.full():
                q.put_nowait(timestamped_frame)


class JPG_TO_H264_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue], encode_queue: asyncio.Queue):
        super().__init__(output_queue) 
        self.frame_queue = frame_queue
        self.encode_queue = encode_queue
    
    async def process_handler(self, np_array: np.ndarray):
        if not self.encode_queue.full():
            self.encode_queue.put_nowait(np_array)
    
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
                
                if not isinstance(frame, cv2.typing.MatLike):
                    frame = np.frombuffer(frame, dtype=np.uint8)
                    frame_bgr = cv2.imdecode(frame, cv2.IMREAD_COLOR)
                    if frame_bgr is None:
                        continue
                else:
                    frame_bgr = frame

                img_yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV_I420)
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



