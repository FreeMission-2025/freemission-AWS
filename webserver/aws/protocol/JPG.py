import asyncio
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseProtocol
from inference import ShmQueue

class JPG_TO_JPG_PROTOCOL(BaseProtocol):
    def __init__(self, input_queue: ShmQueue | List[asyncio.Queue], inference_enabled = True ):
        super().__init__(inference_enabled)

        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if inference_enabled:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue
        else:
            assert isinstance(input_queue, list) and all(isinstance(q, asyncio.Queue) for q in input_queue), \
                "When inference is disabled, input_queue must be a list of asyncio.Queue instances."
            self.frame_queues = input_queue

    def handle_received_frame(self, full_frame: bytes):
        # Decode frame
        np_arr = np.frombuffer(full_frame, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print("Error: Failed to decode reassembled frame.")
            return
        
        if self.inference_enabled:
            self.loop.run_in_executor(None, lambda: self.input_queue.put(frame))
        else:
            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            timestamped_frame = (time.time(), frame_bytes)
            for q in self.frame_queues:
                if not q.full():
                    q.put_nowait(timestamped_frame)

class JPG_TO_H264_PROTOCOL(BaseProtocol):
    def __init__(self, input_queue: ShmQueue | asyncio.Queue, inference_enabled = True ):
        super().__init__(inference_enabled)

        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if inference_enabled:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue
        else:
            assert isinstance(input_queue, asyncio.Queue), \
                "When inference is disabled, input_queue must be a asyncio.Queue instances."
            self.encode_queue = input_queue

    def handle_received_frame(self, full_frame: bytes):
        if self.inference_enabled:
            np_arr = np.frombuffer(full_frame, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            self.loop.run_in_executor(None, lambda: self.input_queue.put(frame)) 
        else:
            if not self.encode_queue.full():
                self.encode_queue.put_nowait(full_frame)
