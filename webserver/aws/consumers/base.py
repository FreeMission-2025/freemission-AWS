import asyncio
import numpy as np
from typing import List
from inference import ShmQueue, QueueStoppedError
from utils.logger import Log

class BaseConsumer:
    def __init__(self, output_queue: ShmQueue):
        self.output_queue = output_queue
        self.loop = asyncio.get_event_loop()

    async def handler(self):
        while True:
            try:
                np_array = await self.loop.run_in_executor(None, self.output_queue.get)

                if np_array is None:
                    continue

                await self.process_handler(np_array)

            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except QueueStoppedError:
                break
            except Exception as e:
                Log.exception(f"Error in handler: {e}")
    
    async def process_handler(self, np_array: np.ndarray):
        """Process frame logic to be overridden by subclasses"""
        raise NotImplementedError("process_frame should be implemented by subclasses")
