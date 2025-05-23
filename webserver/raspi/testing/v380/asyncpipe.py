import asyncio
import numpy as np
import cv2

width, height = 1280, 720
frame_size = width * height * 3  # bgr24 = 3 bytes per pixel

async def read_exactly(stream: asyncio.StreamReader , n):
    data = b''
    while len(data) < n:
        chunk = await stream.read(n - len(data))
        if not chunk:
            # EOF or stream closed
            break
        data += chunk
    return data

async def read_frames(queue):
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'dshow',
        '-video_size', f'{width}x{height}',
        '-framerate', '30',
        '-i', 'video=V380 FHD Camera',
        '-pix_fmt', 'bgr24',
        '-f', 'rawvideo',
        'pipe:1'
    ]

    print("Starting ffmpeg subprocess...")
    proc = await asyncio.create_subprocess_exec(
        *ffmpeg_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        while True:
            raw_frame = await read_exactly(proc.stdout, frame_size)
            if len(raw_frame) < frame_size:
                print("Incomplete frame read, breaking...")
                break
            await queue.put(raw_frame)
    finally:
        proc.terminate()
        # Read and print any remaining stderr for debugging
        stderr = await proc.stderr.read()
        if stderr:
            print("FFmpeg stderr:", stderr.decode(errors='ignore'))
        print("FFmpeg subprocess terminated.")
    
    # Signal the consumer to exit
    await queue.put(None)

async def show_frames(queue):
    while True:
        raw_frame = await queue.get()
        if raw_frame is None:
            print("Received exit signal, stopping...")
            break
        frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))
        cv2.imshow('V380 Camera (async)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        queue.task_done()
    cv2.destroyAllWindows()

async def main():
    queue = asyncio.Queue(maxsize=60)
    reader = asyncio.create_task(read_frames(queue))
    viewer = asyncio.create_task(show_frames(queue))
    await asyncio.gather(reader, viewer)

if __name__ == "__main__":
    asyncio.run(main())

'''
  Stream #0:0: Video: mjpeg (Baseline) (MJPG / 0x47504A4D), yuvj420p(pc, bt470bg/bt709/unknown), 1280x720 [SAR 16:9 DAR 256:81], 30 fps, 30 tbr, 10000k tbn
'''