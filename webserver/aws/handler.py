
import asyncio
import multiprocessing
import os

from constants import INFERENCE_ENABLED, ServerContext, frame_queues, encode_queue, decode_queue, EC2Port
from protocol import JPG_TO_JPG_PROTOCOL, JPG_TO_H264_PROTOCOL, H264_TO_JPG_PROTOCOL, H264_TO_H264_PROTOCOL
from consumers import JPG_TO_JPG_Consumer, JPG_TO_H264_Consumer, H264_TO_JPG_Consumer, H264_TO_H264_Consumer
from inference import ShmQueue

if INFERENCE_ENABLED:
    try:
        from inference import ObjectDetection
    except ImportError:
        raise ValueError("onnxruntime must be installed if running inference")

current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file) 
model_path = os.path.join(current_dir, "model", "v11_s_a.onnx")

if not os.path.exists(model_path):
    raise FileNotFoundError(f"Model file not found at: {model_path}")

ctx = ServerContext()
ctx.input_queue  = ShmQueue(shape=(720,1280,3), capacity=120)
ctx.output_queue = ShmQueue(shape=(720,1280,3), capacity=120)

def inference(**kwargs):
    onnx = ObjectDetection(**kwargs)
    onnx.run()

async def handle_jpg_to_jpg(): 
    loop = asyncio.get_event_loop()
    protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues
    ctx.transport, protocol = await loop.create_datagram_endpoint(
        lambda: JPG_TO_JPG_PROTOCOL(protocol_input, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_JPG_TO_JPG.value)
    )
    print(f"UDP listener (JPG to JPG) started on 0.0.0.0:{EC2Port.UDP_PORT_JPG_TO_JPG.value}")
    
    if INFERENCE_ENABLED:
        kwargs = {
            "model_path": model_path,
            "input_queue": ctx.input_queue,
            "output_queue": ctx.output_queue,
        }
        ctx.infer_process = multiprocessing.Process(target=inference, kwargs=kwargs)
        ctx.infer_process.start()

        consumer = JPG_TO_JPG_Consumer(ctx.output_queue, frame_queues)
        ctx.consumer_task = asyncio.create_task(consumer.handler())

async def handle_jpg_to_h264(): 
    loop = asyncio.get_event_loop()
    protocol_input = ctx.input_queue if INFERENCE_ENABLED else encode_queue
    ctx.transport, protocol = await loop.create_datagram_endpoint(
        lambda: JPG_TO_H264_PROTOCOL(protocol_input, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_JPG_TO_H264.value)
    )
    print(f"UDP listener (JPG to h264) started on 0.0.0.0:{EC2Port.UDP_PORT_JPG_TO_H264.value}")
    

    consumer = JPG_TO_H264_Consumer(ctx.output_queue,frame_queues,encode_queue)
    if INFERENCE_ENABLED:
        kwargs = {
            "model_path": model_path,
            "input_queue": ctx.input_queue,
            "output_queue": ctx.output_queue,
        }
        ctx.infer_process = multiprocessing.Process(target=inference, kwargs=kwargs)
        ctx.infer_process.start()
        ctx.consumer_task = asyncio.create_task(consumer.handler())

    ctx.encode_task  = asyncio.create_task(consumer.encode())

async def handle_h264_to_jpg():
    loop = asyncio.get_event_loop()
    protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

    ctx.transport, protocol = await loop.create_datagram_endpoint(
        lambda: H264_TO_JPG_PROTOCOL(protocol_input, decode_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_JPG.value)
    )
    print(f"UDP listener (Video JPG) started on 0.0.0.0:{EC2Port.UDP_PORT_H264_TO_JPG.value}")

    if INFERENCE_ENABLED:
        kwargs = {
            "model_path": model_path,
            "input_queue": ctx.input_queue,
            "output_queue": ctx.output_queue,
        }
        ctx.infer_process = multiprocessing.Process(target=inference, kwargs=kwargs)
        ctx.infer_process.start()

        consumer = H264_TO_JPG_Consumer(ctx.output_queue, frame_queues)
        ctx.consumer_task = asyncio.create_task(consumer.handler())
    
    ctx.decode_task = asyncio.create_task(protocol.decode())

async def handle_h264_to_h264():
    loop = asyncio.get_event_loop()
    protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

    ctx.transport, protocol = await loop.create_datagram_endpoint(
        lambda: H264_TO_H264_PROTOCOL(protocol_input, decode_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_H264.value)
    )
    print(f"UDP listener (Video H264) started on 0.0.0.0:{EC2Port.UDP_PORT_H264_TO_H264.value}")

    consumer = H264_TO_H264_Consumer(ctx.output_queue, frame_queues, encode_queue)
    if INFERENCE_ENABLED:
        kwargs = {
            "model_path": model_path,
            "input_queue": ctx.input_queue,
            "output_queue": ctx.output_queue,
        }
        ctx.infer_process = multiprocessing.Process(target=inference, kwargs=kwargs)
        ctx.infer_process.start()

        ctx.consumer_task = asyncio.create_task(consumer.handler())
        ctx.decode_task = asyncio.create_task(protocol.decode())

    ctx.encode_task = asyncio.create_task(consumer.encode())
