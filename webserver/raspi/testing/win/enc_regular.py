import os
import sys

# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)

import av
import cv2

def start(): 
    # Set up video capture.
    print("Opening web cam...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise Exception("Could not open video device")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)


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

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        img_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
        video_frame = av.VideoFrame.from_ndarray(img_yuv, format='yuv420p')

        encoded_packet = encoder.encode(video_frame)  # The correct terminology is "encoded_packet".

        # Sometimes the encode results in no frames encoded, so lets skip the frame.
        if len(encoded_packet) == 0:
            continue

        #for frame in encoded_packet:  # No need to use a for loop - there is always going to be only one encoded packet.
        encoded_packet_bytes = bytes(encoded_packet[0])
        print(len(encoded_packet_bytes))

        # Step 1: Create the packet from the "bytes".
        
        packet = av.packet.Packet(encoded_packet_bytes)

        # Step 2: Decode the packet.
        #decoded_packets = decoder.decode(packet)
        decoded_video_frames = decoder.decode(packet)  # After decoding, the terminology is "decoded_frames"

        if len(decoded_video_frames) > 0:
            # Step 3: Convert the pixel format from the encoder color format to BGR for displaying.
            decoded_video_frame = decoded_video_frames[0]
            decoded_frame = decoded_video_frame.to_ndarray(format='yuv420p')
            frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)
            #frame = decoded_video_frame.to_ndarray(format='bgr24')  # BRG is also supported...

            # Step 4. Display frame in window.
            cv2.imshow('Decoded Video', frame)

            
        if cv2.waitKey(100) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start()