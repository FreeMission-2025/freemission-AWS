class AsyncFrameSequencer:
    def __init__(self, tolerance=0.3):
        self.buffer = {}
        self.expected = 0
        self.tolerance = tolerance
        self.new_frame_event = asyncio.Event()
        self.lock = asyncio.Lock()

    async def add_frame(self, frame_id: int, frame_bytes: bytes):
        async with self.lock:
            self.buffer[frame_id] = (time.time(), frame_bytes)
            self.new_frame_event.set()

    async def get_next_ready(self):
        while True:
            async with self.lock:
                if self.expected in self.buffer:
                    _, frame = self.buffer.pop(self.expected)
                    self.expected += 1
                    return frame
                else:
                    self.new_frame_event.clear()

            try:
                await asyncio.wait_for(self.new_frame_event.wait(), timeout=self.tolerance)
            except asyncio.TimeoutError:
                #await self.skip_old()
                # If still missing expected frame after timeout, skip it
                async with self.lock:
                    self.expected += 1  # skip only one frame

    async def skip_old(self):
        async with self.lock:
            now = time.time()
            expired = [fid for fid, (ts, _) in self.buffer.items() if now - ts > self.tolerance]
            for fid in expired:
                if fid < self.expected:
                    continue
                del self.buffer[fid]
                if fid == self.expected:
                    self.expected += 1

class AsyncFrameSequencer:
    def __init__(self, tolerance=0.3):
        self.buffer = {}
        self.expected = 0
        self.tolerance = tolerance
        self.new_frame_event = asyncio.Event()
        self.lock = asyncio.Lock()

    async def add_frame(self, frame_id: int, frame_bytes: bytes):
        async with self.lock:
            self.buffer[frame_id] = (time.time(), frame_bytes)
            self.new_frame_event.set()

    async def get_next_ready(self):
        while True:
            async with self.lock:
                if self.expected in self.buffer:
                    _, frame = self.buffer.pop(self.expected)
                    self.expected += 1
                    return frame
                else:
                    self.new_frame_event.clear()

            try:
                await asyncio.wait_for(self.new_frame_event.wait(), timeout=self.tolerance)
            except asyncio.TimeoutError:
                async with self.lock:
                    # Timeout: look for next available frame_id > expected
                    available_ids = sorted(fid for fid in self.buffer.keys() if fid > self.expected)
                    if available_ids:
                        self.expected = available_ids[0]
                        _, frame = self.buffer.pop(self.expected)
                        self.expected += 1
                        return frame
                    else:
                        # Nothing usable, just keep waiting
                        continue

import asyncio
import time
from collections import defaultdict

class AsyncFrameSequencer:
    def __init__(self, tolerance=0.3):
        self.buffer = {}
        self.expected = 0
        self.tolerance = tolerance
        self.new_frame_event = asyncio.Event()
        self.lock = asyncio.Lock()

    async def add_frame(self, frame_id: int, frame_bytes: bytes):
        async with self.lock:
            self.buffer[frame_id] = (time.time(), frame_bytes)
            self.new_frame_event.set()

    async def get_next_ready(self):
        while True:
            async with self.lock:
                if self.expected in self.buffer:
                    _, frame = self.buffer.pop(self.expected)
                    self.expected += 1
                    return frame
                else:
                    self.new_frame_event.clear()

            try:
                await asyncio.wait_for(self.new_frame_event.wait(), timeout=self.tolerance)
            except asyncio.TimeoutError:
                await self.skip_old()

    async def skip_old(self):
        async with self.lock:
            now = time.time()
            expired = [fid for fid, (ts, _) in self.buffer.items() if now - ts > self.tolerance]
            for fid in expired:
                if fid < self.expected:
                    continue
                del self.buffer[fid]
                if fid == self.expected:
                    self.expected += 1