from re import Pattern
import re
import subprocess
from typing import Optional
import cv2
import socket
import numpy as np
import os
import asyncio
# ffmpeg -hwaccel cuda -hwaccel_output_format cuda -f dshow -video_size 1920x1080 -framerate 30 -i video="USB2.0 FHD UVC WebCam" -pix_fmt yuv420p -c:v h264_nvenc -b:v 3M -an -fflags nobuffer -r 30 -t 00:00:10 -tune ull output.mp4
# ffmpeg -f dshow -video_size 1920x1080 -framerate 30 -i video="USB2.0 FHD UVC WebCam" -pix_fmt yuv420p -c:v libx264 -b:v 3M -an -fflags nobuffer -r 30 -t 00:00:10 -tune zerolatency output.mp4

# Configuration
UDP_IP = "127.0.0.1" 
UDP_PORT = 8085 
MAX_UDP_PACKET_SIZE = 65507  # Maximum UDP payload size
CAMERA_INDEX = 0  # Default camera index (0 for Raspberry Pi's default camera)

async def stream_video() -> Optional[bytes]:
    # Create the UDP transport
    reader, writer = await asyncio.open_connection(UDP_IP, UDP_PORT)

    
    ffmpeg_executable_location = os.path.join("C:", "ffmpeg", "bin", "ffmpeg.exe")
    kvm_device_name = 'USB2.0 FHD UVC WebCam'
    ffmpeg_command = [
        ffmpeg_executable_location,
        '-f', 'dshow',
        '-i', 'video=' + kvm_device_name,
        '-s', '1280x720',
        '-c:v', 'libx264',
        '-tune', 'zerolatency',
        '-r', '30',
        '-b:v', '3M',
        '-an',
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'high',
        '-level', '4',
        '-f', 'h264',
        '-'
    ]

    try:
        encoder_process_interface = await asyncio.create_subprocess_exec(
            *ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0)
    except FileNotFoundError:
        print("file not found")
        return
    except Exception as error:
        print(f"An unexpected error occurred: {error}")
        return
    
    complete_frame_data: bytes = b""

    # Define the regex pattern.
    nal_start_code_pattern: Pattern[bytes] = re.compile(b'(?:\x00\x00\x00\x01)')

    while True:
        try:
            # Read 300 KB (307200 bytes) of data, this will read at most 300KB, if less data
            # is available it will return only those available data, and will not wait
            # for complete 300KB. This number is based on trail and error
            # the maximum IDR frame size was around 280KB.
            new_encoded_data: bytes = await encoder_process_interface.stdout.read(607200)
        except Exception as error:
            print(f"new_encoded_data error: {error}")
            break

        if not new_encoded_data:
            print("There is no data from FFMPEG process, exiting the stream.")
            break

        # Find all non-overlapping matches.
        nal_matches_info: list = list(nal_start_code_pattern.finditer(new_encoded_data))

        no_of_nal_units: int = len(nal_matches_info)

        # If there were no matches, it means the current chunk of data has intermediary
        # Bytes which continues from previous data, hence they should simply be added to the
        # Existing nal data and skip the remaining code.
        if not nal_matches_info:
            complete_frame_data += new_encoded_data
            continue

        for match_index, match in enumerate(nal_matches_info):
            nal_type: int = new_encoded_data[match.end()] & 0x1F

            # If the first match in the list of matches occurs somewhere not in the first index
            # Then first few bytes (before the start index of the first match) would correspond
            # To the data from the previous nal unit, hence we need to add them to the
            # Existing nal data and then send to the client and then clear the buffer.
            if match_index == 0 and match.start() != 0:
                complete_frame_data += new_encoded_data[: match.start()]

            if complete_frame_data:
                # We send only if the current nal is Non-Idr, since other data such as SPS, PPS,
                # SEI, IDR would actually come as separate chunks, we need to combine them before
                # sending. The implementation takes care of combining them, but happens only if a
                # Non-Idr frame comes After the Key Frame (which is a combination of SPS, PPS,
                # SEI, IDR).
                if nal_type == 1:
                    try:
                        writer.write(len(complete_frame_data).to_bytes(4, 'big') + complete_frame_data)
                        frame_size = len(complete_frame_data)
                        await writer.drain()
                        print(f"Sent frame: {frame_size} bytes")
                        
                    except Exception as error:
                        try:
                            encoder_process_interface.terminate()
                            print("Terminated.")
                        except Exception:
                            print("Couldn't terminate the process.")
                        return

                    # Yield control back to the event loop to prevent buffer overflow and ensure
                    # consistent frame rate.
                    await asyncio.sleep(0)
                    complete_frame_data = b''

            # If this is the last item in the list of matches, then we add all the data
            # From the start of its index till the end.
            if match_index == no_of_nal_units - 1:
                complete_frame_data += new_encoded_data[match.start():]
            else:
                # If this is not the last item in the list of matches, then we add all the data
                # From the start of the index, till (but not including) the start of the next
                # Match.
                next_nal_index = match_index + 1
                next_nal_start = nal_matches_info[next_nal_index].start()
                complete_frame_data += new_encoded_data[match.start():next_nal_start]

    try:
        writer.close()
        await writer.wait_closed()
        encoder_process_interface.terminate()
        print("Terminated.")
    except Exception:
        print("Couldn't terminate the process.")

asyncio.run(stream_video())

