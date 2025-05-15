import asyncio
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseTCP
from inference import ShmQueue
from utils.logger import Log
from constants import INFERENCE_ENABLED

class JPG_TO_JPG_TCP(BaseTCP):
    def __init__(self, input_queue: ShmQueue | List[asyncio.Queue]):
        super().__init__()

        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if INFERENCE_ENABLED:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue
        else:
            assert isinstance(input_queue, list) and all(isinstance(q, asyncio.Queue) for q in input_queue), \
                "When inference is disabled, input_queue must be a list of asyncio.Queue instances."
            self.frame_queues = input_queue

    def handle_received_frame(self, full_frame: bytes, frame_id: int):
        np_arr = np.frombuffer(full_frame, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print("Error: Failed to decode reassembled frame.")
            return
        
        if INFERENCE_ENABLED:
            self.loop.run_in_executor(None, lambda: self.input_queue.put(frame, frame_id))
        else:
            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            timestamped_frame = (time.time(), frame_bytes)
            for q in self.frame_queues:
                if not q.full():
                    q.put_nowait(timestamped_frame)
