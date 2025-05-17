import asyncio
import struct
import numpy as np
import cv2
import time
import os
from typing import List
from inference import ShmQueue
from .base import BaseConsumer
from utils.logger import Log
from constants import FFMPEG_DIR, SHOW_FPS, INFERENCE_ENABLED

# Import ffmpeg
if os.path.exists(FFMPEG_DIR):
    os.add_dll_directory(FFMPEG_DIR)
import av
from av.codec.hwaccel import HWAccel, HWDeviceType
from utils.ffmpeg_helper import h264_nvenc, libx264_encoder

class JPG_TO_JPG_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue]):
        super().__init__(output_queue)
        self.frame_queue = frame_queue
        self.frame_count = 0
        self.prev_time = time.monotonic()

    async def process_handler(self, _out: tuple[np.ndarray, int]):
        np_array, _ = _out
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


class JPG_TO_H264_Consumer(BaseConsumer):
    def __init__(self, output_queue: ShmQueue, frame_queue: List[asyncio.Queue], encode_queue: asyncio.Queue):
        super().__init__(output_queue) 
        self.frame_queue = frame_queue
        self.encode_queue = encode_queue
        self.frame_count = 0
        self.prev_time = time.monotonic()

    async def process_handler(self, _out: tuple[np.ndarray, int]):
        if not self.encode_queue.full():
            self.encode_queue.put_nowait(_out)
    
    async def encode(self, codec_name: str, device_type: str | HWDeviceType = None):
        isHwSupported = False
        isEncoderExist = False
        try:
            codec = av.Codec(codec_name, 'w')  
            isEncoderExist = True

            configs = codec.hardware_configs
            if device_type is not None:
                if not configs:
                    raise ValueError(f"{codec_name} doesn't support {device_type}")
                
                if isinstance(device_type, HWDeviceType):
                    device_type = device_type.name

                for config in configs:
                    if config.device_type.name == device_type and config.is_supported:
                        isHwSupported = True
                        break
            
        except Exception as e:
            Log.exception(e, exc_info=False)

        if isHwSupported or (isEncoderExist and codec_name == 'h264_nvenc'):
            encoder = h264_nvenc()
        else:
            encoder = libx264_encoder()

        while True:
            try:
                frame, _= await self.encode_queue.get()

                # If not matlike, then inference is disabled
                if not isinstance(frame, cv2.typing.MatLike):
                    frame = np.frombuffer(frame, dtype=np.uint8)
                    frame_bgr = cv2.imdecode(frame, cv2.IMREAD_COLOR)
                    if frame_bgr is None:
                        continue
                else:
                    frame_bgr = frame

                img_yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV_I420)
                video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
                encoded_packet = await self.loop.run_in_executor(None, lambda: encoder.encode(video_frame))

                if len(encoded_packet) == 0:
                    continue

                timestamp_us = int(encoded_packet[0].pts * encoded_packet[0].time_base * 1_000_000)
                frame_type = 1 if encoded_packet[0].is_keyframe else 0

                # timestamp (8 byte) || frame_type (1 byte) || raw H.264  (N byte)
                packet_data = struct.pack(">QB", timestamp_us, frame_type) + bytes(encoded_packet[0])
                
                timestamped_frame = (time.time(), packet_data)
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



