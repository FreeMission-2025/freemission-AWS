
import asyncio
import ctypes
import multiprocessing
from multiprocessing import Lock, Semaphore, Value, Array
import os
from constants import INFERENCE_ENABLED, ServerContext, frame_queues, encode_queue, decode_queue, jpg_queue, EC2Port, encoder, decoder, ordered_queue, protocol_closed, frame_dispatch_reset, SOURCE_WIDTH, SOURCE_HEIGHT
from protocol import JPG_TO_JPG_PROTOCOL, JPG_TO_H264_PROTOCOL, H264_TO_JPG_PROTOCOL, H264_TO_H264_PROTOCOL, JPG_TO_JPG_TCP, JPG_TO_H264_TCP, H264_TO_JPG_TCP, H264_TO_H264_TCP
from consumers import JPG_TO_JPG_Consumer, JPG_TO_H264_Consumer, H264_TO_JPG_Consumer, H264_TO_H264_Consumer
from inference import ShmQueue, ObjectDetection, SyncObject
from utils.ordered_packet import OrderedPacketDispatcher
import socket

current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file) 
model_path = os.path.join(current_dir, "model", "v11_s_a.onnx")

if not os.path.exists(model_path):
    raise FileNotFoundError(f"Model file not found at: {model_path}")

ctx = ServerContext()
SHM_CAPACITY = 600

sync_input = SyncObject(
    frame_ids = Array(ctypes.c_int, SHM_CAPACITY),
    head      = Value (ctypes.c_int, 0),               
    tail      = Value (ctypes.c_int, 0),               
    stopping  = Value(ctypes.c_bool, False),
    s_full    = Semaphore(0),                
    s_empty   = Semaphore(SHM_CAPACITY),
    p_lock    = Lock(),     
    g_lock    = Lock()                              
)

sync_out = SyncObject(
    frame_ids = Array(ctypes.c_int, SHM_CAPACITY),
    head      = Value (ctypes.c_int, 0),               
    tail      = Value (ctypes.c_int, 0),               
    stopping  = Value(ctypes.c_bool, False),
    s_full    = Semaphore(0),                
    s_empty   = Semaphore(SHM_CAPACITY),
    p_lock    = Lock(),   
    g_lock    = Lock()                                                            
)

ctx.input_queue  = ShmQueue(shape=(SOURCE_HEIGHT, SOURCE_WIDTH, 3),sync=sync_input, capacity=SHM_CAPACITY)
ctx.output_queue = ShmQueue(shape=(SOURCE_HEIGHT, SOURCE_WIDTH, 3),sync=sync_out, capacity=SHM_CAPACITY)

def inference(**kwargs):
    onnx = ObjectDetection(**kwargs)
    onnx.run()

'''
    TCP
'''
class tcp_handle_jpg_to_jpg(): 
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues
        
        ctx.server = await loop.create_server(
            lambda: JPG_TO_JPG_TCP(protocol_input), host='0.0.0.0', port=EC2Port.TCP_PORT_JPG_TO_JPG.value)
        
        print(f"TCP listener (JPG to JPG) started on 0.0.0.0:{EC2Port.TCP_PORT_JPG_TO_JPG.value}")
        
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

class tcp_handle_jpg_to_h264(): 
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else encode_queue
        ctx.server = await loop.create_server(
            lambda: JPG_TO_H264_TCP(protocol_input), host='0.0.0.0', port=EC2Port.TCP_PORT_JPG_TO_H264.value)
        print(f"TCP listener (JPG to h264) started on 0.0.0.0:{EC2Port.TCP_PORT_JPG_TO_H264.value}")
        
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

        ctx.encode_task  = asyncio.create_task(consumer.encode(encoder.name, encoder.device_type))

class tcp_handle_h264_to_jpg():
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

        ctx.server = await loop.create_server(
            lambda: H264_TO_JPG_TCP(decode_queue), host='0.0.0.0', port=EC2Port.TCP_PORT_H264_TO_JPG.value)
        print(f"TCP listener (H264 to JPG) started on 0.0.0.0:{EC2Port.TCP_PORT_H264_TO_JPG.value}")

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
        
        ctx.decode_task = asyncio.create_task(H264_TO_JPG_TCP.decode(protocol_input, decode_queue, decoder.name, decoder.device_type))

class tcp_handle_h264_to_h264():
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

        ctx.server = await loop.create_server(
            lambda: H264_TO_H264_TCP(protocol_input, decode_queue),host='0.0.0.0', port=EC2Port.TCP_PORT_H264_TO_H264.value)
        
        print(f"TCP listener (H264 TO H264) started on 0.0.0.0:{EC2Port.TCP_PORT_H264_TO_H264.value}")

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
            ctx.decode_task = asyncio.create_task(H264_TO_H264_TCP.decode(decode_queue, protocol_input, decoder.name, decoder.device_type))
            ctx.encode_task = asyncio.create_task(consumer.encode(encoder.name, encoder.device_type))

'''
    UDP
'''

class handle_jpg_to_jpg(): 
    @staticmethod
    async def start():
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
            
        ctx.protocol = protocol
        
    
    @staticmethod
    async def reset():
        loop = asyncio.get_event_loop()
        if ctx.protocol:
            ctx.protocol.stop()
            await asyncio.sleep(0.2)
            ctx.transport.abort()
            
            while not protocol_closed['value']:
                print(f"prtocol_closed: {protocol_closed['value']}")
                await asyncio.sleep(0.5)

            ctx.protocol = None
            ctx.transport = None

        await asyncio.sleep(0.5)
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues
        ctx.transport, ctx.protocol = await loop.create_datagram_endpoint(
            lambda: JPG_TO_JPG_PROTOCOL(protocol_input, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_JPG_TO_JPG.value)
        )
        print(f"UDP listener (JPG to JPG) started on 0.0.0.0:{EC2Port.UDP_PORT_JPG_TO_JPG.value}")

class handle_jpg_to_h264(): 
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else encode_queue
        ctx.transport, protocol = await loop.create_datagram_endpoint(
            lambda: JPG_TO_H264_PROTOCOL(protocol_input, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_JPG_TO_H264.value)
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
            ctx.jpg_producer_task = asyncio.create_task(JPG_TO_H264_PROTOCOL._producer(jpg_queue, protocol_input))
            ctx.protocol = protocol
            ctx.ordering_task = asyncio.create_task(OrderedPacketDispatcher(ordered_queue, jpg_queue).run())
        else:
            ctx.protocol = protocol
            ctx.ordering_task = asyncio.create_task(OrderedPacketDispatcher(ordered_queue, encode_queue).run())

        ctx.encode_task  = asyncio.create_task(consumer.encode(encoder.name, encoder.device_type))

    @staticmethod
    async def reset():
        loop = asyncio.get_event_loop()
        if ctx.protocol:
            ctx.protocol.stop()
            await asyncio.sleep(0.2)
            ctx.transport.abort()
            
            while not protocol_closed['value']:
                print(f"prtocol_closed: {protocol_closed['value']}")
                await asyncio.sleep(0.5)

            ctx.protocol = None
            ctx.transport = None

            frame_dispatch_reset['value'] = True
            while frame_dispatch_reset['value']:
                await asyncio.sleep(0.5)

        await asyncio.sleep(0.5)
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else encode_queue
        ctx.transport, ctx.protocol = await loop.create_datagram_endpoint(
            lambda: JPG_TO_H264_PROTOCOL(protocol_input, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_JPG_TO_H264.value)
        )
        print(f"UDP listener (JPG to h264) started on 0.0.0.0:{EC2Port.UDP_PORT_JPG_TO_H264.value}")

        return True

class handle_h264_to_jpg():
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

        ctx.transport, protocol = await loop.create_datagram_endpoint(
            lambda: H264_TO_JPG_PROTOCOL(protocol_input, decode_queue, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_JPG.value)
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
        
        ctx.protocol = protocol
        ctx.decode_task = asyncio.create_task(protocol.decode(protocol_input, decode_queue, decoder.name, decoder.device_type))
        ctx.ordering_task = asyncio.create_task(OrderedPacketDispatcher(ordered_queue, decode_queue).run())
    
    @staticmethod
    async def reset():
        loop = asyncio.get_event_loop()
        if ctx.protocol:
            ctx.protocol.stop()
            await asyncio.sleep(0.2)
            ctx.transport.abort()
            
            while not protocol_closed['value']:
                print(f"prtocol_closed: {protocol_closed['value']}")
                await asyncio.sleep(0.5)

            ctx.protocol = None
            ctx.transport = None

            frame_dispatch_reset['value'] = True
            while frame_dispatch_reset['value']:
                await asyncio.sleep(0.5)

        await asyncio.sleep(0.5)
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues
        ctx.transport, ctx.protocol = await loop.create_datagram_endpoint(
            lambda: H264_TO_JPG_PROTOCOL(protocol_input, decode_queue, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_JPG.value)
        )
        print(f"UDP listener (Video JPG) started on 0.0.0.0:{EC2Port.UDP_PORT_H264_TO_JPG.value}")

        return True


class handle_h264_to_h264():
    @staticmethod
    async def start():
        loop = asyncio.get_event_loop()
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues

        ctx.transport, protocol = await loop.create_datagram_endpoint(
            lambda: H264_TO_H264_PROTOCOL(protocol_input, decode_queue, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_H264.value)
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
            ctx.decode_task = asyncio.create_task(protocol.decode(decode_queue, protocol_input, decoder.name, decoder.device_type))
            ctx.encode_task = asyncio.create_task(consumer.encode(encoder.name, encoder.device_type))
            ctx.protocol = protocol
            ctx.ordering_task = asyncio.create_task(OrderedPacketDispatcher(ordered_queue, decode_queue).run())
        else:
            ctx.protocol = protocol
            ctx.ordering_task = asyncio.create_task(OrderedPacketDispatcher(ordered_queue, frame_queues).run())

        # original encode task here

    @staticmethod
    async def reset():
        loop = asyncio.get_event_loop()
        if ctx.protocol:
            ctx.protocol.stop()
            await asyncio.sleep(0.2)
            ctx.transport.abort()
            
            while not protocol_closed['value']:
                print(f"prtocol_closed: {protocol_closed['value']}")
                await asyncio.sleep(0.5)

            ctx.protocol = None
            ctx.transport = None

            frame_dispatch_reset['value'] = True
            while frame_dispatch_reset['value']:
                await asyncio.sleep(0.5)
            print("cleared 3333")

        await asyncio.sleep(0.5)
        protocol_input = ctx.input_queue if INFERENCE_ENABLED else frame_queues
        ctx.transport, ctx.protocol = await loop.create_datagram_endpoint(
            lambda: H264_TO_H264_PROTOCOL(protocol_input, decode_queue, ordered_queue, INFERENCE_ENABLED), local_addr=('0.0.0.0', EC2Port.UDP_PORT_H264_TO_H264.value)
        )
        print(f"UDP listener (Video H264) started on 0.0.0.0:{EC2Port.UDP_PORT_H264_TO_H264.value}")

        return True
        
        

            