import asyncio
import numpy as np
import cv2
import time
from typing import List
from inference import ShmQueue
from .base import BaseConsumer
from utils.logger import Log


class H264_TO_JPG_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue]):
        super().__init__(output_queue)
        self.frame_queue = frame_queue

    async def process_handler(self, np_array: np.ndarray):
        _, buffer = cv2.imencode(".jpg", np_array, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        frame_bytes = buffer.tobytes()

        timestamped_frame = (time.time(), frame_bytes)
        for q in self.frame_queue:
            if not q.full():
                q.put_nowait(timestamped_frame)

class H264_TO_H264_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue]):
        super().__init__(output_queue)
        self.frame_queue = frame_queue

    async def process_handler(self, np_array: np.ndarray):
        raise NotImplementedError("Not Implemented")


