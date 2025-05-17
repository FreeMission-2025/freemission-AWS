import asyncio
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseUDP
from inference import ShmQueue
from utils.logger import Log

class JPG_TO_JPG_PROTOCOL(BaseUDP):
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

    def handle_received_frame(self, full_frame: bytes, frame_id: int):
        # Decode frame
        np_arr = np.frombuffer(full_frame, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print("Error: Failed to decode reassembled frame.")
            return
        
        if self.inference_enabled:
            self.loop.run_in_executor(None, lambda: self.input_queue.put(frame, frame_id))
        else:
            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            timestamped_frame = (time.time(), frame_bytes)
            for q in self.frame_queues:
                if not q.full():
                    q.put_nowait(timestamped_frame)

class JPG_TO_H264_PROTOCOL(BaseUDP):
    def __init__(self, input_queue: ShmQueue | asyncio.Queue, ordered_queue: asyncio.Queue, inference_enabled = True ):
        super().__init__(inference_enabled)

        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None
        self.ordered_queue = ordered_queue

        if inference_enabled:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue
        else:
            assert isinstance(input_queue, asyncio.Queue), \
                "When inference is disabled, input_queue must be a asyncio.Queue instances."
            self.encode_queue = input_queue

        assert isinstance(ordered_queue, asyncio.Queue), "ordered_queue must be a asyncio.Queue instances."

    def handle_received_frame(self, full_frame: bytes, frame_id):
        '''
        if self.inference_enabled:
            np_arr = np.frombuffer(full_frame, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if not self.ordered_queue.full():
                self.ordered_queue.put_nowait((frame_id, frame))
            #self.loop.run_in_executor(None, lambda: self.input_queue.put(frame, frame_id)) 
        else:
            if not self.encode_queue.full():
                self.encode_queue.put_nowait(full_frame)        
        '''
        if not self.ordered_queue.full():
            self.ordered_queue.put_nowait((frame_id, full_frame))

    @staticmethod
    async def _producer(jpg_queue: asyncio.Queue, input_queue: ShmQueue):
        assert isinstance(jpg_queue, asyncio.Queue), "jpg_queue must be a asyncio.Queue instances."
        assert isinstance(input_queue, ShmQueue), "input_queue must be a ShmQueue instances."

        loop = asyncio.get_event_loop()

        while True:
            try:
                encoded_packet_bytes, frame_id = await jpg_queue.get()
                np_arr = np.frombuffer(encoded_packet_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                await loop.run_in_executor(None, lambda: input_queue.put(frame, frame_id))
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                Log.exception(f"error at decode_video: {e}")
        



