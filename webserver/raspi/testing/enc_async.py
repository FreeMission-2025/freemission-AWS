import platform
system = platform.system()

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

import os
# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)

import asyncio
import av
import cv2
import contextlib
import time

class VideoStream:
    def __init__(self, frame_queue:asyncio.Queue, src=0, desired_width=680,):
        api = cv2.CAP_MSMF if system =='Windows' else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(src, apiPreference=api)
        
        if not self.cap.isOpened():
            raise Exception("Error: Could not open webcam.")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.ret, self.frame = self.cap.read()
        self.frame_queue = frame_queue
        self.desired_width = desired_width
        self.stopped = False
    
    async def start(self):
        self.running = True
        loop = asyncio.get_running_loop()

        while self.running:
            ret, frame = await loop.run_in_executor(None, self.cap.read)
            if not ret:
                await asyncio.sleep(0.5)
                continue

            #frame = cv2.resize(frame, (self.desired_width, int(frame.shape[0] * self.desired_width / frame.shape[1])))
            if self.frame_queue.full():
                print("queue full")

            await self.frame_queue.put(frame)
            await asyncio.sleep(0)
            
    def stop(self):
        self.stopped = True
        self.cap.release()

async def capture_camera():
    # Initialize the encoder.
    encoder = av.CodecContext.create('libx264', 'w')
    encoder.width = 1280
    encoder.height = 720
    encoder.pix_fmt = 'yuv420p'
    encoder.bit_rate = 3000000  
    encoder.framerate = 30 
    encoder.options = {'tune': 'zerolatency'} 

    # Initialize the decoder.
    decoder = av.CodecContext.create('h264', 'r')

    # Start the video stream in a separate thread
    frame_queue = asyncio.Queue(maxsize=120)
    vs = VideoStream(frame_queue)
    
    stream_task = asyncio.create_task(vs.start())

    prev_time = time.time()
    frame_count = 0
    loop = asyncio.get_running_loop()

    try:
        while True:
            frame = await frame_queue.get()
            if frame is None:
                continue
            

            img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')

            encoded_packet = await loop.run_in_executor(None, lambda: encoder.encode(video_frame))

            # Sometimes the encode results in no frames encoded, so lets skip the frame.
            if len(encoded_packet) == 0:
                continue

            encoded_packet_bytes = bytes(encoded_packet[0])
            #print(len(encoded_packet_bytes))

            packet = av.packet.Packet(encoded_packet_bytes)

            # Step 2: Decode the packet.
            #decoded_packets = decoder.decode(packet)
            decoded_video_frames = await loop.run_in_executor(None, lambda: decoder.decode(packet))


            if len(decoded_video_frames) > 0:
                # Step 3: Convert the pixel format from the encoder color format to BGR for displaying.
                decoded_video_frame = decoded_video_frames[0]
                decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
                frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)
                #frame = decoded_video_frame.to_ndarray(format='bgr24')  # BRG is also supported...

                # Step 4. Display frame in window.
                cv2.imshow('Decoded Video', frame)

            current_time = time.time()
            frame_count += 1
            if current_time - prev_time >= 1:
                fps = frame_count / (current_time - prev_time)
                print(f"FPS: {fps:.2f}")
                prev_time = current_time
                frame_count = 0

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error eccoured at capture_camera: {e}")
    finally:
        vs.stop()
        cv2.destroyAllWindows()
        # Cancel the stream task and wait for it to finish
        stream_task.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        except Exception as e:
            print(f"Error occurred while canceling stream task: {e}")



if __name__ == '__main__':
    asyncio.run(capture_camera())
    