import asyncio
import os
import struct
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseProtocol
from inference import ShmQueue
from utils.logger import Log
from constants import FFMPEG_DIR
from utils.ffmpeg_helper import get_decoder, is_keyframe

# Import ffmpeg
if os.path.exists(FFMPEG_DIR):
    os.add_dll_directory(FFMPEG_DIR)
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

    async def decode(self, decoder_name: str, device_type: str | None = None):
        if self.input_queue is not None:
            await self.__decode_to_shm(self.input_queue, self.decode_queue, self.inference_enabled, self.loop, decoder_name, device_type)
        elif self.frame_queues is not None:
            await self.__decode_to_frame(self.frame_queues, self.decode_queue, self.inference_enabled, self.loop, decoder_name, device_type)
        else:
            raise ValueError("Input Queue not supported. Pass correct type of input_queue in H264_TO_JPG_PROTOCOL")
        
    @staticmethod
    async def __decode_to_shm(input_queue: ShmQueue, decode_queue: asyncio.Queue,  inference_enabled: bool, loop: asyncio.AbstractEventLoop, decoder_name: str, device_type: str | None):
        if not inference_enabled:
            raise ValueError("Inference must be enabled")

        decoder = get_decoder(decoder_name, device_type)
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
                #await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")

    @staticmethod
    async def __decode_to_frame(frame_queues: List[asyncio.Queue], decode_queue: asyncio.Queue,  inference_enabled: bool, loop: asyncio.AbstractEventLoop, decoder_name: str, device_type: str | None):
        if inference_enabled:
            raise ValueError("Inference must be disabled")
        
        decoder = get_decoder(decoder_name, device_type)
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
                
                #await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")


class H264_TO_H264_PROTOCOL(BaseProtocol):
    def __init__(self, input_queue: ShmQueue | List[asyncio.Queue], decode_queue: asyncio.Queue | None,  inference_enabled = True):
        super().__init__(inference_enabled)
        
        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if self.inference_enabled:
            assert isinstance(input_queue, ShmQueue), \
                "When inference is enabled, input_queue must be a ShmQueue instance."
            self.input_queue = input_queue

            assert isinstance(decode_queue, asyncio.Queue), \
            "decode_queue must be a asyncio.Queue instances."
            self.decode_queue = decode_queue
        else:
            assert isinstance(input_queue, list) and all(isinstance(q, asyncio.Queue) for q in input_queue), \
                "When inference is disabled, input_queue must be a list of asyncio.Queue instances."
            self.frame_queues = input_queue
        
    def handle_received_frame(self, full_frame: bytes):
        if self.inference_enabled:
            if not self.decode_queue.full():
                self.decode_queue.put_nowait(full_frame)
        else:
            timestamp_us = int(time.time() * 1_000_000)
            frame_type = 1 if is_keyframe(full_frame) else 0
            packet_data = struct.pack(">QB", timestamp_us, frame_type) + full_frame

            timestamped_frame = (time.time(), packet_data)
            for q in self.frame_queues:
                if not q.full():
                    q.put_nowait(timestamped_frame)

    async def decode(self, decoder_name: str, device_type: str | None = None):
        if not self.inference_enabled:
            raise ValueError("Inference must be enabled")

        decoder = get_decoder(decoder_name, device_type)
        while True:
            try:
                encoded_packet_bytes = await self.decode_queue.get()

                packet = av.packet.Packet(encoded_packet_bytes)
                #start = time.perf_counter()
                decoded_video_frames = await self.loop.run_in_executor(None, lambda: decoder.decode(packet)) 
                #print(f"dec: {time.perf_counter() - start:.4f}s")

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray()
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                await self.loop.run_in_executor(None, lambda: self.input_queue.put(bgr_frame))
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")
        



