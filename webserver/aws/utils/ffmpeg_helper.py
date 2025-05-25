import asyncio
import cv2
import os
import numpy as np
import time
from typing import List
from inference import ShmQueue
from utils.logger import Log
from constants import FFMPEG_DIR, SHOW_FPS, SOURCE_WIDTH, SOURCE_HEIGHT

# Import ffmpeg
if os.path.exists(FFMPEG_DIR):
    os.add_dll_directory(FFMPEG_DIR)
from av.codec.hwaccel import HWAccel, HWDeviceType
import av

class EncodersProperties():
    HwAccel: HWAccel | None
    width: int
    height: int
    pix_fmt: str
    bit_rate: int
    frame_rate: int
    enc_options: dict

def h264_nvenc():
    hwaccel = HWAccel(device_type='cuda', allow_software_fallback=False)
    encoder = av.CodecContext.create('h264_nvenc', 'w', hwaccel)
    encoder.width = SOURCE_WIDTH
    encoder.height = SOURCE_HEIGHT
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 2000000  
    encoder.framerate = 30 
    encoder.profile =  'main'
    encoder.options = {
        'preset': 'll',            # fast (low quality), or try 'p4' for more balance
        'tune': 'll',
        'rc': 'vbr',
        'cq': '28',                # target quality if needed (lower = better quality; try 23-28)
        'spatial_aq': '0',         # Spatial adaptive quantization (helps quality) . Improve quality in area with high detail
        'temporal_aq': '0',        # enable temporal AQ. Benefical for non moving background area
        'device': '0',             # gpu device index
        'bf': '0',                 # Disable B-frames for lower latency. higher value = lower size 
        'g': '240'             # gop
    }
    Log.info(f"Using HwAccel cuda and encoders h264_nvenc. HwAccel is supported: {encoder.is_hwaccel}")
    return encoder

def libx264_encoder():
    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = SOURCE_WIDTH
    encoder.height = SOURCE_HEIGHT
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 2000000  
    encoder.framerate = 25 
    encoder.profile = 'Main'
    encoder.options = {'tune': 'zerolatency'} 
    Log.info(f"Using libxh264_encoder")
    return encoder

def get_decoder(decoder_name: str, device_type: str | None):
    try:
        hwaccel = None
        if device_type is not None:
            hwaccel = HWAccel(device_type, allow_software_fallback=False)

        decoder = av.CodecContext.create(decoder_name, 'r', hwaccel)
        #decoder.frame_rate = 25
        decoder.rate = 25
        decoder.profile = 'Main'


        Log.info(f"Using decoders {decoder_name}. HwAccel is supported: {decoder.is_hwaccel}")
        return decoder
    
    except Exception as e:
        Log.exception(e, False)
        Log.info(f"Using software h264 decoder")
        decoder = av.CodecContext.create('h264', 'r')
        return decoder

def is_keyframe(data: bytes) -> bool:
    i = 0
    while i < len(data) - 4:
        if data[i:i+4] == b'\x00\x00\x00\x01':
            nal_start = i + 4
        elif data[i:i+3] == b'\x00\x00\x01':
            nal_start = i + 3
        else:
            i += 1
            continue

        if nal_start >= len(data):
            break

        nal_unit_type = data[nal_start] & 0x1F
        if nal_unit_type == 5:
            return True
        i = nal_start + 1  # move forward after this NAL
    return False



