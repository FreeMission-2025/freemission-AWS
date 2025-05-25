import platform
system = platform.system()

def install_loop():
    try:
        if system == 'Linux':
            import uvloop
            uvloop.install()
        elif system == 'Windows':
            import winloop
            winloop.install()
    except ModuleNotFoundError:
        pass
    except Exception as e:
        print(f"Error when installing loop: {e}")

install_loop()
import os
# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)

import cv2
import contextlib
import time
import multiprocessing
import asyncio

async def capture_video(frame_queue:multiprocessing.Queue):
    install_loop()
    loop = asyncio.get_running_loop()

    system = platform.system()
    api = cv2.CAP_MSMF if system =='Windows' else cv2.CAP_ANY

    cap = cv2.VideoCapture(0, apiPreference=api)
    if not cap.isOpened():
            raise Exception("Error: Could not open webcam.")
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    while True:
        try: 
            ret, frame = await loop.run_in_executor(None, cap.read)
            if not ret:
                await asyncio.sleep(0.1)
                continue

            if not frame_queue.full():
                frame_queue.put_nowait(frame.copy())
            else:
                print("full")
        except Exception as e:
            print(f"error: {e}")

async def encode_video(frame_queue: multiprocessing.Queue, encode_queue: multiprocessing.Queue):
    install_loop()
    loop = asyncio.get_running_loop()

    import av
    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = 1280
    encoder.height = 720
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 3000000  
    encoder.framerate = 30 
    encoder.options = {'tune': 'zerolatency'} 

    try:
        while True:
            if not frame_queue.empty():
                frame = frame_queue.get()
            else:
                await asyncio.sleep(0.02)
                continue

            img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
            encoded_packet = encoder.encode(video_frame) 

            if len(encoded_packet) == 0:
                continue

            #for frame in encoded_packet:  # No need to use a for loop - there is always going to be only one encoded packet.
            encoded_packet_bytes = bytes(encoded_packet[0])
            if not encode_queue.full():
                encode_queue.put_nowait(encoded_packet_bytes)
            else:
                print("full")
    except Exception as e:
        print(f"error: {e}")

async def decode_video(encode_queue: multiprocessing.Queue, decode_queue: multiprocessing.Queue):
    install_loop()
    loop = asyncio.get_running_loop()

    import av
    decoder = av.CodecContext.create('h264', 'r')

    try:
        while True:
            if not encode_queue.empty():
                encoded_packet_bytes = encode_queue.get()
            else:
                await asyncio.sleep(0.02)
                continue

            packet = av.packet.Packet(encoded_packet_bytes)

            decoded_video_frames = decoder.decode(packet)  # After decoding, the terminology is "decoded_frames"

            if len(decoded_video_frames) > 0:
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
                if not decode_queue.full():
                    decode_queue.put_nowait(decoded_frame)
                else:
                    print("full")

    except Exception as e:
        print(f"error: {e}")

def async_capture(frame_queue):
    asyncio.run(capture_video(frame_queue))

def async_encode(frame_queue,encode_queue):
    asyncio.run(encode_video(frame_queue,encode_queue))

def async_decode(encode_queue,decode_queue):
    asyncio.run(decode_video(encode_queue,decode_queue))
    

async def main():
    multiprocessing.set_start_method('spawn')  # Good practice on Windows

    frame_queue  = multiprocessing.Queue(60)
    encode_queue = multiprocessing.Queue(60)
    decode_queue = multiprocessing.Queue(60)

    video_process = multiprocessing.Process(target=async_capture, args=(frame_queue,))
    video_process.start()

    encode_process = multiprocessing.Process(target=async_encode, args=(frame_queue,encode_queue))
    encode_process.start()

    decode_process = multiprocessing.Process(target=async_decode, args=(encode_queue,decode_queue))
    decode_process.start()

    prev_time = time.time()
    frame_count = 0
    
    try:
        while True:
            if not decode_queue.empty():
                decoded_frame = decode_queue.get()
                frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                current_time = time.time()
                frame_count += 1
                if current_time - prev_time >= 1:
                    fps = frame_count / (current_time - prev_time)
                    print(f"FPS: {fps:.2f}")
                    prev_time = current_time
                    frame_count = 0

                cv2.imshow("Live Feed", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        video_process.terminate()
        video_process.join()
        encode_process.terminate()
        encode_process.join()
        decode_process.terminate()
        decode_process.join()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    asyncio.run(main())
