import asyncio
import heapq
import time
from utils.logger import Log
from constants import frame_dispatch_reset, INFERENCE_ENABLED, OUTGOING_FORMAT, Format

class OrderedPacketDispatcher:
    def __init__(self, input: asyncio.Queue, output: asyncio.Queue | list[asyncio.Queue], max_fps=30, timeout=0.4, poll_interval=0.03):
        assert isinstance(input, asyncio.Queue), "input_queue must be a ShmQueue instance."
        
        self.input = input
        self.max_fps = max_fps
        self.timeout = timeout
        self.poll_interval = poll_interval

        self.buffer = []
        self.received_map = {}
        self.expected_frame_id = None
        self.last_dispatch_time = 0.0

        if INFERENCE_ENABLED:
            assert isinstance(output, asyncio.Queue), \
                "When inference is enabled, output must be a asyncio.Queue instance."
            self.output = output
        else:
            if OUTGOING_FORMAT.value == Format.H264.value:
                assert isinstance(output, list) and all(isinstance(q, asyncio.Queue) for q in output), \
                    "When inference is disabled and output is H264, input_queue must be a list of asyncio.Queue instances."
                self.frame_queue = output
            elif OUTGOING_FORMAT.value == Format.JPG.value:
                "When inference is disabled and output is H264, input_queue must be a asyncio.Queue instances."
                self.output = output



    def __reset(self):
        """Reset internal state to initial values."""
        self.buffer.clear()  # Clear the buffer (list)
        self.received_map.clear()  # Clear the received map (dictionary)
        self.expected_frame_id = None  # Reset expected frame ID
        self.last_dispatch_time = 0.0  # Reset last dispatch time
        Log.info("OrderedPacketDispatcher state has been reset.")

    async def run(self):
        first_frame_set = False

        while True:
            try:
                # Drain available inputs
                try:
                    if frame_dispatch_reset['value']:
                        self.__reset()
                        first_frame_set = False
                        frame_dispatch_reset['value'] = False
                        continue

                    while True:
                        if not self.input.empty():
                            frame_id, packet_data = self.input.get_nowait()
                            if frame_id not in self.received_map:
                                self.received_map[frame_id] = packet_data
                                heapq.heappush(self.buffer, (frame_id, packet_data))
                            await asyncio.sleep(0)
                        else:
                            break
                except asyncio.QueueEmpty:
                    pass

                # Initialize expected frame ID
                if not first_frame_set and self.buffer:
                    self.expected_frame_id = self.buffer[0][0]
                    first_frame_set = True

                # Drop outdated frames
                while self.buffer and self.buffer[0][0] < self.expected_frame_id:
                    outdated_id, _ = heapq.heappop(self.buffer)
                    self.received_map.pop(outdated_id, None)

                # Wait up to `timeout` for expected frame to arrive . waited = self.timeout + self.poll interval
                waited = 0.0
                found = False
                while waited < self.timeout:
                    if self.buffer and self.buffer[0][0] == self.expected_frame_id:
                        found = True
                        break

                    await asyncio.sleep(self.poll_interval)
                    waited += self.poll_interval

                    # Try to collect more frames
                    try:
                        while True:
                            if not self.input.empty():
                                frame_id, packet_data = self.input.get_nowait()
                                if frame_id not in self.received_map:
                                    self.received_map[frame_id] = packet_data
                                    heapq.heappush(self.buffer, (frame_id, packet_data))
                                await asyncio.sleep(0)
                            else:
                                break
                    except asyncio.QueueEmpty:
                        pass

                if found:
                    while self.buffer and self.buffer[0][0] == self.expected_frame_id:
                        frame_id, packet_data = heapq.heappop(self.buffer)
                        self.received_map.pop(frame_id, None)

                        if INFERENCE_ENABLED or OUTGOING_FORMAT.value == Format.JPG.value:
                            if not self.output.full():
                                self.output.put_nowait((packet_data, frame_id))
                        else:
                            timestamped_frame = (time.time(), packet_data)
                            for q in self.frame_queue:
                                if not q.full():
                                    q.put_nowait(timestamped_frame)

                        if self.expected_frame_id is not None:
                            self.expected_frame_id += 1
                    # Throttle output to max FPS . (disable for now)
                    '''                    
                    now = time.monotonic()
                    elapsed = now - self.last_dispatch_time
                    wait_time = max(0, (1 / self.max_fps) - elapsed)
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                    self.last_dispatch_time = time.monotonic()
                    '''

                else:
                    Log.warning(f"[Dispatcher] Timeout {waited} waiting for frame_id {self.expected_frame_id}, skipping.")

                    if self.expected_frame_id is not None:
                        if self.buffer:
                            self.expected_frame_id = self.buffer[0][0]

                await asyncio.sleep(0.002)
            except asyncio.CancelledError:
                break
            except Exception as e:
                Log.exception(f"[Dispatcher] Error: {e}")

