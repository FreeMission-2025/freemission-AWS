import platform
import os
import cv2
import contextlib
import time
import multiprocessing
from multiprocessing import shared_memory
import numpy as np

def capture_video(shared_mem_name: str, shape: tuple, dtype: np.dtype):
    system = platform.system()
    api = cv2.CAP_MSMF if system == 'Windows' else cv2.CAP_ANY

    cap = cv2.VideoCapture(0, apiPreference=api)
    if not cap.isOpened():
        raise Exception("Error: Could not open webcam.")
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Attach to the shared memory buffer
    shm = shared_memory.SharedMemory(name=shared_mem_name)
    frame_array = np.ndarray(shape, dtype=dtype, buffer=shm.buf)

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        # Copy frame into shared memory buffer
        frame_resized = cv2.resize(frame, (1280, 720))
        np.copyto(frame_array, frame_resized)

        time.sleep(0.01)

def encode_video(shared_mem_name: str, shape: tuple, dtype: np.dtype, encode_queue: multiprocessing.Queue):
    import av
    shm = shared_memory.SharedMemory(name=shared_mem_name)
    frame_array = np.ndarray(shape, dtype=dtype, buffer=shm.buf)

    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = 1280
    encoder.height = 720
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 3000000  
    encoder.framerate = 30 
    encoder.options = {'tune': 'zerolatency'} 

    try:
        while True:
            # Wait for the frame to be available in shared memory
            frame = frame_array.copy()
            if frame is None:
                time.sleep(0.02)
                continue

            img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')
            encoded_packet = encoder.encode(video_frame) 

            if len(encoded_packet) == 0:
                continue

            encoded_packet_bytes = bytes(encoded_packet[0])
            if not encode_queue.full():
                encode_queue.put_nowait(encoded_packet_bytes)
            else:
                print("Encode queue full")
    except Exception as e:
        print(f"Error: {e}")

def decode_video(encode_queue: multiprocessing.Queue, decode_queue: multiprocessing.Queue):
    import av
    decoder = av.CodecContext.create('h264', 'r')

    try:
        while True:
            if not encode_queue.empty():
                encoded_packet_bytes = encode_queue.get()
            else:
                time.sleep(0.02)
                continue

            packet = av.packet.Packet(encoded_packet_bytes)
            decoded_video_frames = decoder.decode(packet) 

            if len(decoded_video_frames) > 0:
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
                if not decode_queue.full():
                    decode_queue.put_nowait(decoded_frame)
                else:
                    print("Decode queue full")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    # Shared memory name
    shared_mem_name = 'video_shared_memory'

    # Frame dimensions (height, width, channels)
    frame_shape = (720, 1280, 3)
    dtype = np.uint8

    # Create shared memory
    shm = shared_memory.SharedMemory(create=True, name=shared_mem_name, size=np.prod(frame_shape) * dtype.itemsize)

    # Queues for encoding and decoding
    encode_queue = multiprocessing.Queue(60)
    decode_queue = multiprocessing.Queue(60)

    video_process = multiprocessing.Process(target=capture_video, args=(shared_mem_name, frame_shape, dtype))
    video_process.start()

    encode_process = multiprocessing.Process(target=encode_video, args=(shared_mem_name, frame_shape, dtype, encode_queue))
    encode_process.start()

    decode_process = multiprocessing.Process(target=decode_video, args=(encode_queue, decode_queue))
    decode_process.start()

    try:
        while True:
            if not decode_queue.empty():
                decoded_frame = decode_queue.get()
                frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)
                cv2.imshow("Live Feed", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup processes and shared memory
        video_process.terminate()
        video_process.join()
        encode_process.terminate()
        encode_process.join()
        decode_process.terminate()
        decode_process.join()
        shm.close()
        shm.unlink()
        cv2.destroyAllWindows()