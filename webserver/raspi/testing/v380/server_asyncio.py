import asyncio
import os
import socket

# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
if os.path.exists(ffmpeg_bin):
    os.add_dll_directory(ffmpeg_bin)

import av
import cv2

async def handle_echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    sock:socket.socket = writer.get_extra_info('socket')
    
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tcp_nodelay = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        print(f"TCP_NODELAY after setting: {tcp_nodelay}")

        # Set send and receive buffer sizes on both client and server
        bufsize = 32 * 1024 * 1024  # 32MB

        default_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"Default SO_RCVBUF: {default_rcvbuf}")
        print(f"Default SO_SNDBUF: {default_sndbuf}")

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, bufsize)

        new_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        print(f"New SO_RCVBUF: {new_rcvbuf}")
        print(f"New SO_SNDBUF: {new_sndbuf}")

    decoder = av.CodecContext.create('h264', 'r')
    while True:
        try:
            # STEP 1: Read exactly 4 bytes (length prefix)
            length_prefix = await reader.readexactly(4)
            data_len = int.from_bytes(length_prefix, byteorder='big')
            
            # STEP 2: Read the actual payload
            data = await reader.readexactly(data_len)
            if data == b'':
                break

            print(f"Received packet of length: {data_len} bytes")

            
            packet = av.Packet(data)
            try:
                decoded_video_frames = decoder.decode(packet)
            except Exception as e:
                print(f"Decoder error: {e}, skipping packet")
                continue

            if len(decoded_video_frames) <= 0:
                continue
            
            for pkt in decoded_video_frames:
                decoded_frame = pkt.to_ndarray()
                bgr_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_YUV2BGR_I420)

                cv2.imshow('Camera', bgr_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        except asyncio.CancelledError:
            break
        except ConnectionAbortedError:
            break
        except ConnectionError:
            break
    
    try:
        writer.close()
        await writer.wait_closed()
    except ConnectionAbortedError:
        return
    except ConnectionError:
        return

async def main():
    server = await asyncio.start_server(
        handle_echo, '0.0.0.0', 8082)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'Serving on {addrs}')

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())