import asyncio
import struct
import time
from zlib import crc32
from typing import Any
from utils.logger import Log

class BaseProtocol(asyncio.DatagramProtocol):
    def __init__(self, inference_enabled=True):
        self.inference_enabled = inference_enabled
        self.transport = None
        self.frames_in_progress = {}
        self.loop = asyncio.get_event_loop()
        self.timeout = 0.4

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport
        Log.info(f"UDP connection established")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        try:
            self.cleanup_old_frames(time.time())

            # Parse header
            frame_id, total_chunks, chunk_index, checksum = struct.unpack("!HBBI", data[:8])
            chunk_data = data[8:]

            computed_crc32 = crc32(chunk_data)
            if computed_crc32 != checksum:
                Log.warning(f"Checksum mismatch for {frame_id}, chunk {chunk_index}")

            if frame_id not in self.frames_in_progress:
                self.frames_in_progress[frame_id] = {
                    'chunks': [None] * total_chunks,
                    'received': 0,
                    'start_time': time.time(),
                }

            frame_entry = self.frames_in_progress[frame_id]
            if frame_entry['chunks'][chunk_index] is None:
                frame_entry['chunks'][chunk_index] = chunk_data
                frame_entry['received'] += 1

            if frame_entry['received'] == total_chunks:
                # All chunks received
                full_frame = b"".join(frame_entry['chunks'])
                # Cleanup
                del self.frames_in_progress[frame_id]

                self.handle_received_frame(full_frame)
        except asyncio.CancelledError:
            return
        except Exception as e:
            Log.exception(f"Error in datagram_received: {e}")
    
    def handle_received_frame(self, full_frame: bytes):
        """Process the received frame and reassemble if all chunks are received"""
        raise NotImplementedError("handle_received_frame should be implemented by subclasses")

    def cleanup_old_frames(self, now):
        expired_ids = [fid for fid, entry in self.frames_in_progress.items() if now - entry['start_time'] > self.timeout]
        for fid in expired_ids:
            Log.warning(f"Frame {fid} timeout. Discarded")
            del self.frames_in_progress[fid]

    def error_received(self, exc: Exception):
        Log.exception(f"Error received: {exc}")

    def connection_lost(self, exc: Exception):
        Log.info(f"Closing connection: {exc}")
