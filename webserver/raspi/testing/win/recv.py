import asyncio
import datetime
import av
import cv2

UDP_IP = "0.0.0.0"
UDP_PORT_RECEIVE = 8085

SAMPLE_DATA_INDEX_START = 0
SAMPLE_DATA_INDEX_END = 6
NAL_TYPE_INDICATOR_INDEX = 4
NAL_TYPE_MASK = 0x1F
DELTA_FRAME_ID = 1

# Initialize decoder with explicit H.264 Annex B handling
decoder = av.CodecContext.create('h264', 'r')

def is_keyframe(data: bytes) -> bool:
    """Check if the packet contains an IDR frame (keyframe)."""
    # Search for start codes (Annex B format)
    start_code_3 = b'\x00\x00\x01'
    start_code_4 = b'\x00\x00\x00\x01'
    
    pos = 0
    while pos < len(data):
        # Check for 4-byte start code
        if data[pos:pos+4] == start_code_4:
            pos += 4
        elif data[pos:pos+3] == start_code_3:
            pos += 3
        else:
            pos += 1
            continue
        
        if pos >= len(data):
            break
        
        nal_type = data[pos] & 0x1F  # Extract NAL type
        if nal_type == 5:  # IDR frame
            return True
    return False

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    global timestamp

    # === SETUP VIDEO WRITER ===
    filename = f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    output_container = av.open(filename, mode='w')
    output_stream = output_container.add_stream('h264', rate=30)
    output_stream.width = 1920
    output_stream.height = 1080
    output_stream.pix_fmt = 'yuv420p'

    try:
        while True:
            length_bytes = await reader.readexactly(4)
            data_length = int.from_bytes(length_bytes, 'big')
            data = await reader.readexactly(data_length)

            # Get frame type
            data_view = data[SAMPLE_DATA_INDEX_START:SAMPLE_DATA_INDEX_END]
            nal_type = data_view[NAL_TYPE_INDICATOR_INDEX] & NAL_TYPE_MASK
            decoder_type = 'delta' if nal_type == DELTA_FRAME_ID else 'key'

            pkt = av.packet.Packet(data)
            pkt.is_keyframe = decoder_type == 'key'

            frames = decoder.decode(pkt)
            for frame in frames:
                frame_array = frame.to_ndarray(format='yuv420p')
                frame_array = cv2.cvtColor(frame_array, cv2.COLOR_YUV2BGR_I420)
                cv2.imshow('Video Stream', frame_array)

                # Display break condition
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    cv2.destroyAllWindows()
                    output_container.close()
                    return

                # Encode and write to mp4
                for packet in output_stream.encode(frame):
                    output_container.mux(packet)

                timestamp += 33333  # ~30 FPS
    except asyncio.IncompleteReadError:
        print("Client disconnected.")
    except Exception as e:
        print(f"Error decoding video: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        cv2.destroyAllWindows()
        try:
            # Flush encoder
            for packet in output_stream.encode():
                output_container.mux(packet)
            output_container.close()
            print(f"Video saved to {filename}")
        except Exception as e:
            print(f"Error saving video: {e}")


timestamp = 0

async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', UDP_PORT_RECEIVE)
    addr = server.sockets[0].getsockname()
    print(f"Listening on {addr}")
    async with server:
        await server.serve_forever()

asyncio.run(main())