import asyncio
from fractions import Fraction
import os
import struct
import cv2
import time
from typing import List, Optional
import numpy as np
from .base import BaseTCP
from inference import ShmQueue
from utils.logger import Log
from constants import FFMPEG_DIR, INFERENCE_ENABLED
from utils.ffmpeg_helper import get_decoder, is_keyframe

# Import ffmpeg
if os.path.exists(FFMPEG_DIR):
    os.add_dll_directory(FFMPEG_DIR)
import av
from av.packet import Packet


class H264_TO_JPG_TCP(BaseTCP):
    def __init__(self, decode_queue: asyncio.Queue):
        super().__init__()
        
        assert isinstance(decode_queue, asyncio.Queue), \
            "decode_queue must be a asyncio.Queue instances."
        self.decode_queue = decode_queue


    def handle_received_frame(self, full_frame: bytes, frame_id):
        if not self.decode_queue.full():
            self.decode_queue.put_nowait((full_frame, frame_id))

    @staticmethod
    async def decode(input_queue: ShmQueue | List[asyncio.Queue], decode_queue: asyncio.Queue, decoder_name: str, device_type: str | None = None):
        if INFERENCE_ENABLED:
            assert isinstance(input_queue, ShmQueue), "When inference is enabled, input_queue must be a ShmQueue instance."
            input_queue = input_queue
        else:
            assert isinstance(input_queue, list) and all(isinstance(q, asyncio.Queue) for q in input_queue), "When inference is disabled, input_queue must be a list of asyncio.Queue instances."
            frame_queues = input_queue
        assert isinstance(decode_queue, asyncio.Queue), "decode_queue must be a asyncio.Queue instances."

        loop = asyncio.get_event_loop()
        if isinstance(input_queue, ShmQueue):
            await H264_TO_JPG_TCP.__decode_to_shm(input_queue, decode_queue, loop, decoder_name, device_type)
        elif isinstance(input_queue, list):
            await H264_TO_JPG_TCP.__decode_to_frame(frame_queues, decode_queue, loop, decoder_name, device_type)
        else:
            raise ValueError("Input Queue not supported. Pass correct type of input_queue in H264_TO_JPG_PROTOCOL")
    
    @staticmethod
    def __unpack_packet(packet_data: bytes):
        timestamp_us, frame_type = struct.unpack(">QB",  packet_data[:9])
        return timestamp_us, frame_type, packet_data[9:]   
    
    @staticmethod
    async def __decode_to_shm(input_queue: ShmQueue, decode_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, decoder_name: str, device_type: str | None):
        if not INFERENCE_ENABLED:
            raise ValueError("Inference must be enabled")

        decoder = get_decoder(decoder_name, device_type)
        time_base = (Fraction(1, 30)) * 1_000_000 

        while True:
            try:
                encoded_packet_bytes, frame_id = await decode_queue.get()
                timestamp_us, frame_type, packet_data = H264_TO_JPG_TCP.__unpack_packet(encoded_packet_bytes)

                packet = Packet(packet_data)
                packet.is_keyframe = True if frame_type == 1 else False
                packet.pts = round(timestamp_us / time_base)
                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame:av.VideoFrame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                await loop.run_in_executor(None, lambda: input_queue.put(bgr_frame, frame_id))
                #await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")

    @staticmethod
    async def __decode_to_frame(frame_queues: List[asyncio.Queue], decode_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, decoder_name: str, device_type: str | None):
        if INFERENCE_ENABLED:
            raise ValueError("Inference must be disabled")
        
        decoder = get_decoder(decoder_name, device_type)
        time_base = (Fraction(1, 30)) * 1_000_000 

        while True:
            try:
                encoded_packet_bytes, _ = await decode_queue.get()

                timestamp_us, frame_type, packet_data = H264_TO_JPG_TCP.__unpack_packet(encoded_packet_bytes)

                packet = Packet(packet_data)
                packet.is_keyframe = True if frame_type == 1 else False
                packet.pts = round(timestamp_us / time_base)
                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame:av.VideoFrame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
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

class H264_TO_H264_TCP(BaseTCP):
    def __init__(self, input_queue: ShmQueue | List[asyncio.Queue], decode_queue: asyncio.Queue | None):
        super().__init__()
        
        self.input_queue: Optional[ShmQueue] = None
        self.frame_queues: Optional[list[asyncio.Queue]] = None

        if INFERENCE_ENABLED:
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

    @staticmethod
    def __unpack_packet(packet_data: bytes):
        timestamp_us, frame_type = struct.unpack(">QB",  packet_data[:9])
        return timestamp_us, frame_type, packet_data[9:]   
    
    def handle_received_frame(self, full_frame: bytes, frame_id):
        if INFERENCE_ENABLED:
            if not self.decode_queue.full():
                self.decode_queue.put_nowait((full_frame, frame_id))
        else:
            timestamped_frame = (time.time(), full_frame)
            for q in self.frame_queues:
                if not q.full():
                    q.put_nowait(timestamped_frame)        

    @staticmethod
    async def decode(decode_queue: asyncio.Queue , input_queue: ShmQueue, decoder_name: str, device_type: str | None = None):
        assert isinstance(decode_queue, asyncio.Queue), "decode_queue must be a asyncio.Queue instances."
        assert isinstance(input_queue, ShmQueue), "When inference is enabled, input_queue must be a ShmQueue instance."

        if not INFERENCE_ENABLED:
            raise ValueError("Inference must be enabled")


        decoder = get_decoder(decoder_name, device_type)
        Log.info(f"using {decoder.name}")
        time_base = (Fraction(1, 30)) * 1_000_000 
        loop = asyncio.get_event_loop()

        while True:
            try:
                encoded_packet_bytes, frame_id = await decode_queue.get()
                timestamp_us, frame_type, packet_data = H264_TO_H264_TCP.__unpack_packet(encoded_packet_bytes)

                packet = Packet(packet_data)
                packet.is_keyframe = True if frame_type == 1 else False
                packet.pts = round(timestamp_us / time_base)

                #start = time.perf_counter()
                decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet)) 
                #print(f"dec: {time.perf_counter() - start:.4f}s")

                if len(decoded_video_frames) <= 0:
                    continue
                
                decoded_video_frame:av.VideoFrame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                await loop.run_in_executor(None, lambda: input_queue.put(bgr_frame, frame_id))
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                    Log.exception(f"error at decode_video: {e}")
        

