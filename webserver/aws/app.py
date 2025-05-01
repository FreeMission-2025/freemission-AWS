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
from utils.logger import Log

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
from constants import INCOMING_FORMAT, OUTGOING_FORMAT 
from constants import frame_queues
from handler import handle_jpg_to_jpg, handle_jpg_to_h264, handle_h264_to_jpg, handle_h264_to_h264, ctx

@app.after_start
async def start():
    handlers = {
        ('JPG', 'JPG'): handle_jpg_to_jpg,
        ('JPG', 'H264'): handle_jpg_to_h264,
        ('H264', 'JPG'): handle_h264_to_jpg,
        ('H264', 'H264'): handle_h264_to_h264,
    }

    handler = handlers.get((INCOMING_FORMAT.value, OUTGOING_FORMAT.value))
    if handler:
        await handler()
    else:
        raise NotImplementedError("Unsupported format combination")

@app.on_stop
async def cleanup_server():
    await asyncio.sleep(0.2)
    await ctx.cleanup()

''' 
    ServerSentEvents: Video Stream Endpoints (h264 codec)
'''
@get("/h264_stream")
async def h264_stream(request: Request) -> AsyncIterable[ServerSentEvent]:
    frame_queue = asyncio.Queue()
    frame_queues.append(frame_queue)

    try:
        while True:
            if await request.is_disconnected():
                Log.info("The request is disconnected!")
                break
            try:
                timestamp, frame_bytes = await frame_queue.get()
                age = time.time() - timestamp
                encoded_frame = base64.b64encode(frame_bytes).decode('utf-8')

                if age > 0.2:
                    Log.warning(f"Skipped old frame ({age:.3f}s old)")
                    continue
                yield ServerSentEvent({"message": encoded_frame})

                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                Log.exception(f"Error in frame generator: {e}")
    finally:
        if frame_queue in frame_queues:
            frame_queues.remove(frame_queue)

'''
    ServerSentEvents: Video Stream Endpoints (JPG)
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
                    Log.info("The request is disconnected!")
                    break

                try:
                    timestamp, frame_bytes = await frame_queue.get()
                    age = time.time() - timestamp
                    if age > 0.2:
                        Log.warning(f"Skipped old frame ({age:.3f}s old)")
                        continue
                    
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n\r\n"
                    )
                    await asyncio.sleep(0.005)
                except asyncio.CancelledError:
                    break
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    Log.exception(f"Error in frame generator: {e}")
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

'''
    Websockets: Video Stream Endpoints (H264)
'''
@ws("/ws_h264_stream")
async def echo(websocket: WebSocket):
    await websocket.accept()

    frame_queue = asyncio.Queue()
    frame_queues.append(frame_queue)

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == 'READY':
                Log.info("READY TO RECEIVE")
                break
            await asyncio.sleep(0.02)
        while True:
            try:
                timestamp, frame_bytes = await frame_queue.get()
                age = time.time() - timestamp

                if age > 0.2:
                    Log.warning(f"Skipped old frame ({age:.3f}s old)")
                    continue

                await websocket.send_bytes(frame_bytes)
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                Log.exception(f"Error in frame generator: {e}")
    except WebSocketDisconnectError:
        return
    finally:
        if frame_queue in frame_queues:
            frame_queues.remove(frame_queue)

'''
    Static HTML
'''
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
