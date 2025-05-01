import asyncio
import os
import av.packet
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseProtocol
from inference import ShmQueue
from utils.logger import Log

# Import ffmpeg
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)
import av
from av.packet import Packet

class H264_TO_JPG_PROTOCOL(BaseProtocol):
    def __init__(self, input_queue: ShmQueue | List[asyncio.Queue], decode_queue: asyncio.Queue,  inference_enabled = True):
        super().__init__(inference_enabled)

        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if self.inference_enabled:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue
        else:
            assert isinstance(input_queue, list) and all(isinstance(q, asyncio.Queue) for q in input_queue), \
                "When inference is disabled, input_queue must be a list of asyncio.Queue instances."
            self.frame_queues = input_queue
        
        assert isinstance(decode_queue, asyncio.Queue), \
            "decode_queue must be a asyncio.Queue instances."
        self.decode_queue = decode_queue


    def handle_received_frame(self, full_frame: bytes):
        if not self.decode_queue.full():
            self.decode_queue.put_nowait(full_frame)

    async def decode(self):
        if self.input_queue is not None:
            await self.__decode_to_shm(self.input_queue, self.decode_queue, self.inference_enabled, self.loop)
        elif self.frame_queues is not None:
            await self.__decode_to_frame(self.frame_queues, self.decode_queue, self.inference_enabled, self.loop)
        else:
            raise ValueError("Input Queue not supported. Pass correct type of input_queue in H264_TO_JPG_PROTOCOL")
        
    @staticmethod
    async def __decode_to_shm(input_queue: ShmQueue, decode_queue: asyncio.Queue,  inference_enabled: bool, loop: asyncio.AbstractEventLoop):
        if not inference_enabled:
            raise ValueError("Inference must be enabled")

        decoder = av.CodecContext.create('h264', 'r')
        while True:
            try:
                encoded_packet_bytes = await decode_queue.get()

                packet = av.packet.Packet(encoded_packet_bytes)
                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray()
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                await loop.run_in_executor(None, lambda: input_queue.put(bgr_frame))
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")

    @staticmethod
    async def __decode_to_frame(frame_queues: List[asyncio.Queue], decode_queue: asyncio.Queue,  inference_enabled: bool, loop: asyncio.AbstractEventLoop):
        if inference_enabled:
            raise ValueError("Inference must be disabled")
        
        decoder = av.CodecContext.create('h264', 'r')
        while True:
            try:
                encoded_packet_bytes = await decode_queue.get()

                packet = av.packet.Packet(encoded_packet_bytes)
                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray()
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                success, jpeg_encoded = cv2.imencode('.jpg', bgr_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if not success:
                    Log.warning("Failed to encode JPEG")
                    continue
                
                frame_bytes = jpeg_encoded.tobytes()
                timestamped_frame = (time.time(), frame_bytes)

                for q in frame_queues:
                    if not q.full():
                        q.put_nowait(timestamped_frame)
                
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")


class H264_TO_H264_PROTOCOL(BaseProtocol):
    def handle_received_frame(self, full_frame: bytes):
        raise NotImplementedError("Not yet implemented")



