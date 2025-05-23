import os
import subprocess
ffmpeg_bin = r"C:\ffmpeg\bin"
if os.path.exists(ffmpeg_bin):
    os.add_dll_directory(ffmpeg_bin)

import av
import cv2

width, height = 1280, 720

# FFmpeg command: encode webcam input as H.264 and output to stdout
ffmpeg_cmd = [
    'ffmpeg',
    '-f', 'dshow',
    '-video_size', f'{width}x{height}',
    '-framerate', '30',
    '-i', 'video=V380 FHD Camera',
    '-an',                        
    '-vcodec', 'libx264',
    '-tune', 'zerolatency',
    '-f', 'h264',
    'pipe:1'
]

# Start FFmpeg subprocess
proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


container = av.open(proc.stdout, format='h264')
# Get the video stream (should be one stream in raw h264)
video_stream = next(s for s in container.streams if s.type == 'video')

# Set decoder options explicitly (if needed)
codec_context = video_stream.codec_context
codec_context.width = width
codec_context.height = height

for attr in dir(codec_context):
    # filter out private/protected attrs
    if not attr.startswith('_'):
        try:
            value = getattr(codec_context, attr)
            # To avoid printing callable methods:
            if not callable(value):
                print(f"{attr}: {value}")
        except Exception as e:
            print(f"{attr}: <error: {e}>")

try:
    for packet in container.demux():
        raw_bytes = bytes(packet)
        #print(f'Packet (stream={packet.stream.type}, size={len(raw_bytes)}, pts={packet.pts}): {raw_bytes[:10].hex()}...')
        for frame in packet.decode():
            img = frame.to_ndarray(format='bgr24')
            cv2.imshow('H.264 Stream (FFmpeg + PyAV)', img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                raise KeyboardInterrupt
finally:
    proc.terminate()
    cv2.destroyAllWindows()
