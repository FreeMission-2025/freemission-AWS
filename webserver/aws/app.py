import asyncio
import base64
from collections.abc import AsyncIterable
from datetime import datetime
import time
from blacksheep import Application, Request, Response, StreamedContent, get, WebSocket, WebSocketDisconnectError, ws
from blacksheep.server.compression import GzipMiddleware
from blacksheep.server.sse import ServerSentEvent
from blacksheep.contents import HTMLContent

import os
app = Application(show_error_details=True)
app.use_cors(
    allow_methods="*",
    allow_origins="*",
    allow_headers="*",
)
app.middlewares.append(GzipMiddleware(min_size=100))

@get("/")
def home():
    return f"Hello, World! {datetime.now().isoformat()}"

'''
    Receive Video From Raspberry PI
'''
from constants import frame_queues, decode_queue
from JPG_udp import JpgUDPProtocol
from H264_udp import H264_JPG_UDPProtocol, DecodeVideo, H264_VideoProtocol

EC2_UDP_PORT_JPG = 8085
EC2_UDP_PORT_VIDEO_TO_JPG = 8086
EC2_UDP_PORT_VIDEO_CODEC = 8087

# listen for UDP packets from raspi (JPG)
''' 
@app.after_start
async def start_udp_server_jpg():
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: JpgUDPProtocol(frame_queues), local_addr=('0.0.0.0', EC2_UDP_PORT_JPG)
    )
    print(f"UDP listener (JPG) started on 0.0.0.0:{EC2_UDP_PORT_JPG}")
'''

# listen for UDP packets from raspi (Video to JPG)
'''
@app.after_start
async def start_udp_server_video():
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: H264_JPG_UDPProtocol(decode_queue), local_addr=('0.0.0.0', EC2_UDP_PORT_VIDEO_TO_JPG)
    )
    print(f"UDP listener (Video JPG) started on 0.0.0.0:{EC2_UDP_PORT_VIDEO_TO_JPG}")

@app.after_start
async def create_decode_task():
    global decode_task
    video_decoder = DecodeVideo(decode_queue, frame_queues)
    decode_task = asyncio.create_task(video_decoder.decode())

@app.on_stop
async def shutdown_tasks():
    global decode_task
    if decode_task is not None:
        print("Shutting down decode task...")
        decode_task.cancel()
        try:
            await decode_task
        except asyncio.CancelledError:
            print("Decode task was cancelled cleanly.")
'''
            
# listen for UDP packets from raspi (Video Encoded)
@app.after_start
async def start_udp_server_video_h264():
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: H264_VideoProtocol(frame_queue=frame_queues), local_addr=('0.0.0.0', EC2_UDP_PORT_VIDEO_CODEC)
    )
    print(f"UDP listener (Video H264) started on 0.0.0.0:{EC2_UDP_PORT_VIDEO_CODEC}")

''' 
    Video Stream Endpoints (h264 codec)
'''
@get("/h264_stream")
async def h264_stream(request: Request) -> AsyncIterable[ServerSentEvent]:
    frame_queue = asyncio.Queue()
    frame_queues.append(frame_queue)

    try:
        while True:
            if await request.is_disconnected():
                print("The request is disconnected!")
                break
            try:
                timestamp, frame_bytes = await frame_queue.get()
                age = time.time() - timestamp
                encoded_frame = base64.b64encode(frame_bytes).decode('utf-8')

                if age > 0.2:
                    print(f"Skipped old frame ({age:.3f}s old)")
                    continue
                yield ServerSentEvent({"message": encoded_frame})

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in frame generator: {e}")
            await asyncio.sleep(0.005)
    finally:
        if frame_queue in frame_queues:
            frame_queues.remove(frame_queue)

'''
    Video Stream Endpoints (JPG)
'''
@get("/jpg_stream")
async def jpg_stream(request: Request):
    # Create a queue for the new client and add it to the list of queues
    frame_queue = asyncio.Queue()
    frame_queues.append(frame_queue)

    async def frame_generator():
        try:
            while True:
                if await request.is_disconnected():
                    print("The request is disconnected!")
                    break

                try:
                    timestamp, frame_bytes = await frame_queue.get()
                    age = time.time() - timestamp
                    if age > 0.2:
                        print(f"Skipped old frame ({age:.3f}s old)")
                        continue
                    
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n\r\n"
                    )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"Error in frame generator: {e}")
                await asyncio.sleep(0.005)
        finally:
            if frame_queue in frame_queues:
                frame_queues.remove(frame_queue)

    return Response(
        200,
        content=StreamedContent(
            content_type=b"multipart/x-mixed-replace; boundary=frame",
            data_provider=frame_generator 
        )
    )


@ws("/ws_h264_stream")
async def echo(websocket: WebSocket):
    await websocket.accept()

    frame_queue = asyncio.Queue()
    frame_queues.append(frame_queue)

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == 'READY':
                print("READYYYY")
                break
            await asyncio.sleep(0.02)
        while True:
            try:
                timestamp, frame_bytes = await frame_queue.get()
                age = time.time() - timestamp

                if age > 0.2:
                    print(f"Skipped old frame ({age:.3f}s old)")
                    continue

                await websocket.send_bytes(frame_bytes)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in frame generator: {e}")
            await asyncio.sleep(0.005)
    except WebSocketDisconnectError:
        return
    finally:
        if frame_queue in frame_queues:
            frame_queues.remove(frame_queue)

@get("/sse.html")
async def serve_html(request: Request):
    file_path = "webserver/aws/static/sse.html"
    
    # Check if the file exists
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            html_content = file.read()
        
        # Convert the string to bytes
        
        # Return the HTML content with correct Content-Type header
        return Response(status=200, content=HTMLContent(html_content))
    else:
        return Response("File not found", status=404)
    
@get("/h264.html")
async def serve_html(request: Request):
    file_path = "webserver/aws/static/h264.html"
    
    # Check if the file exists
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            html_content = file.read()
        
        # Convert the string to bytes
        
        # Return the HTML content with correct Content-Type header
        return Response(status=200, content=HTMLContent(html_content))
    else:
        return Response("File not found", status=404)
    
@get("/mjpeg.html")
async def serve_html(request: Request):
    file_path = "webserver/aws/static/mjpeg.html"
    
    # Check if the file exists
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            html_content = file.read()
        
        # Convert the string to bytes
        
        # Return the HTML content with correct Content-Type header
        return Response(status=200, content=HTMLContent(html_content))
    else:
        return Response("File not found", status=404)
