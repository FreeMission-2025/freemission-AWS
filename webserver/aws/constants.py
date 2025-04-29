from enum import Enum
from typing import List
from asyncio import Queue, Task

frame_queues: List[Queue] = []
"""List of asyncio frame queues, one for each connected client on video_stream endpoint"""

decode_queue: Queue = Queue()
decode_task: Task | None = None 

encode_queue: Queue = Queue()
encode_task: Task | None = None 

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
