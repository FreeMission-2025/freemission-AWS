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

decoder = av.CodecContext.create('h264', 'r')
timestamp = 0


class VideoUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.output_container = None
        self.output_stream = None
        self.initialize_output()

    def initialize_output(self):
        filename = f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.output_container = av.open(filename, mode='w')
        self.output_stream = self.output_container.add_stream('h264', rate=30)
        self.output_stream.width = 1920
        self.output_stream.height = 1080
        self.output_stream.pix_fmt = 'yuv420p'
        self.filename = filename

    def datagram_received(self, data, addr):
        global timestamp
        try:
            if len(data) < SAMPLE_DATA_INDEX_END:
                print(f"Received too small packet from {addr}")
                return

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

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    cv2.destroyAllWindows()
                    self.close()
                    return

                for packet in self.output_stream.encode(frame):
                    self.output_container.mux(packet)

                timestamp += 33333

        except Exception as e:
            print(f"Error decoding video from {addr}: {e}")

    def close(self):
        try:
            for packet in self.output_stream.encode():
                self.output_container.mux(packet)
            self.output_container.close()
            print(f"Video saved to {self.filename}")
        except Exception as e:
            print(f"Error saving video: {e}")
        finally:
            cv2.destroyAllWindows()
            asyncio.get_event_loop().stop()


async def main():
    print(f"Listening for UDP packets on {UDP_IP}:{UDP_PORT_RECEIVE}")
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: VideoUDPProtocol(),
        local_addr=(UDP_IP, UDP_PORT_RECEIVE)
    )
    futures = loop.create_future()
    try:
        # Keep the event loop running forever
        await futures
    finally:
        transport.close()


asyncio.run(main())
