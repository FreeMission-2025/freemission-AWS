from typing import List
from asyncio import Queue, Task

frame_queues: List[Queue] = []
"""List of asyncio frame queues, one for each connected client on video_stream endpoint"""

decode_queue: Queue = Queue()
decode_task: Task | None = None  # global or accessible variable
