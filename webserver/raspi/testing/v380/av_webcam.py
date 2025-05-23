from fractions import Fraction
import platform
import os

import cv2

# Configure DLL path for Windows
system = platform.system()
ffmpeg_bin = r"C:\ffmpeg\bin"
if system == 'Windows' and os.path.exists(ffmpeg_bin):
    os.add_dll_directory(ffmpeg_bin)

import av
# Open video input from DirectShow
input_container = av.open(
    format='dshow',
    file='video=V380 FHD Camera',
    options={
        'video_size': '1920x1080',
        'framerate': '30',
        'fflags': '+genpts'
    },
    mode='r'
)

video_stream = None
for stream in input_container.streams:
    if stream.type == 'video':
        video_stream = stream
        for attr in dir(video_stream.codec_context):
            try:
                value = getattr(video_stream.codec_context, attr)
                print(f"{attr}: {value}")
            except Exception as e:
                print(f"{attr}: <unreadable> ({e})")

        print("dwadddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd")
        for attr in dir(video_stream):
            try:
                value = getattr(video_stream, attr)
                print(f"{attr}: {value}")
            except Exception as e:
                print(f"{attr}: <unreadable> ({e})")
        break

if video_stream:
    print(f"Codec name: {video_stream.codec_context.name}")
    print(f"Codec long name: {video_stream.codec_context.codec.long_name}")
else:
    print("No video stream found.")

output_container = av.open('outputs.mp4', mode='w')
stream = output_container.add_stream('libx264', rate=30)
stream.width = 1920
stream.height = 1080
stream.pix_fmt = 'yuv420p'
stream.framerate = 30
stream.bit_rate = 5_000_000  # 3 Mbps
stream.time_base = Fraction(1,30)
frame_index = 0

print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

for frame in input_container.decode(video=0):
    for attr in dir(video_stream):
        try:
            value = getattr(video_stream, attr)
            print(f"{attr}: {value}")
        except Exception as e:
            print(f"{attr}: <unreadable> ({e})")
    break

    # Set frame pts (presentation timestamp)
    frame.pts = frame_index
    frame.time_base = Fraction(1,30)

    img = frame.to_ndarray(format='bgr24')
    
    # Show frame using OpenCV
    cv2.imshow('Camera', img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    for packet in stream.encode(frame):
        output_container.mux(packet)

    frame_index += 1

# Flush encoder
for packet in stream.encode():
    output_container.mux(packet)

output_container.close()
input_container.close()
cv2.destroyAllWindows()

'''
ffmpeg -f dshow -video_size 1280x720 -framerate 30 -i video="V380 FHD Camera" -c:v libx264 -b:v 3M -vf "setdar=16/9" -pix_fmt yuv420p outputs.mp4
ffmpeg -f dshow -video_size 1280x720 -framerate 30 -i video="V380 FHD Camera" -c:v copy output.mp4
ffmpeg -f v4l2 -input_format h264 -video_size 1280x720 -framerate 30 -fflags +genpts -i /dev/video0 -c copy -pix_fmt yuv420p outputs.mp4 
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
v4l2-ctl -d /dev/video0 --all
ffmpeg -f v4l2 -list_formats all -i /dev/video0
for d in /dev/video*; do echo $d; v4l2-ctl -d $d --list-formats-ext; done
'''