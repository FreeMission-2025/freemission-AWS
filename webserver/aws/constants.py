from enum import Enum
from multiprocessing import Process
from typing import List
from asyncio import DatagramTransport, Queue, Task
from inference import ShmQueue

frame_queues: List[Queue] = []
"""List of asyncio frame queues, one for each connected client on video_stream endpoint"""

decode_queue: Queue = Queue()
decode_task: Task | None = None 

encode_queue: Queue = Queue()
encode_task: Task | None = None 
consumer_task: Task | None = None

input_queue:  ShmQueue | None  = None
output_queue: ShmQueue  | None = None
infer_process: Process | None = None

transport: DatagramTransport | None = None

# Config
class EC2Port(Enum):
    UDP_PORT_JPG_TO_JPG   = int(8085)
    UDP_PORT_JPG_TO_H264  = int(8085)
    UDP_PORT_H264_TO_JPG  = int(8086)
    UDP_PORT_H264_TO_H264 = int(8086)
    # {Incoming-format}_TO_{Outgoing-format}
    # For same incoming protocol == Same ip because code for raspi_socket is same

class Format(Enum):
    JPG = "JPG"
    H264 = "H264"

INCOMING_FORMAT  = Format.JPG  # Valid: JPG or H264
OUTGOING_FORMAT  = Format.JPG  # Valid: JPG or H264
INFERENCE_ENABLED = bool(True)
