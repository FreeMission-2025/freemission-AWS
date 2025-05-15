import asyncio
import subprocess
import socket
import struct
import time
from zlib import crc32
from typing import Any, Dict, Set
from utils.logger import Log
import platform
from constants import protocol_closed


START_MARKER = b'\x01\x02\x7F\xED'
END_MARKER = b'\x03\x04\x7F\xED'
HEADER_FORMAT = "!4s I 3s B B H I"  # Updated header format
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s B"       # | 4-byte marker | 3-byte frame_id | 1-byte chunk_index |
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

class BaseUDP(asyncio.DatagramProtocol):
    def __init__(self, inference_enabled=True):
        self.inference_enabled = inference_enabled
        self.transport = None
        self.frames_in_progress = {}
        self._received_chunks: Dict[int, Set[int]] = {}
        self.loop = asyncio.get_event_loop()
        self.timeout = 0.5
        self.is_stopped = False

    def reset(self):
        """Reset internal state to initial values."""
        self.frames_in_progress.clear()  # Clear frames in progress
        self._received_chunks.clear()  # Clear the received chunks map
        Log.info("BaseUDP state has been reset.")
    
    def stop(self):
        self.is_stopped = True

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport
        Log.info(f"UDP connection established")

        sock: socket.socket = transport.get_extra_info('socket')
        platforms = platform.system()
        if platforms == "Linux":
            original_rmem_max = subprocess.check_output(["sysctl", "net.core.rmem_max"]).decode().strip().split('=')[1]
            Log.info(f"Original rmem_max: {original_rmem_max} bytes")
            Log.info("Setting new rmem_max to 32 mb")
            subprocess.run(["sysctl", "-w", "net.core.rmem_max=33554432"], check=True)

        default_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        Log.info(f"Default SO_RCVBUF: {default_rcvbuf} bytes")

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)

        if platforms == "Linux":
            Log.info("Restoring default value of rmem_max")
            subprocess.run(["sysctl", "-w", f"net.core.rmem_max={original_rmem_max}"], check=True)

        new_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        Log.info(f"new SO_RCVBUF: {new_rcvbuf} bytes")

    def calculate_elapsed_time_ms(self, client_timestamp: int, server_timestamp: int) -> int:
        return (server_timestamp - client_timestamp) % 0x100000000  # 2^32

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        try:
            if self.is_stopped:
                return
            
            self.cleanup_old_frames(time.time())

            if len(data) < HEADER_SIZE + len(END_MARKER):
                raise ValueError("Packet too small")

            # Extract header and payload
            header = data[:HEADER_SIZE]
            payload = data[HEADER_SIZE:-len(END_MARKER)]
            end_marker = data[-len(END_MARKER):]

            # Validate end marker
            if end_marker != END_MARKER:
                raise ValueError("Invalid end marker")

            # Unpack the header using the updated HEADER_FORMAT
            start_marker, timestamp, frame_id, total_chunks, chunk_index, chunk_length, checksum = struct.unpack(HEADER_FORMAT, header)
            frame_id = int.from_bytes(frame_id, byteorder='big')

            # Validate start marker
            if start_marker != START_MARKER:
                raise ValueError("Invalid start marker")
            
            if chunk_length != len(payload):
                raise ValueError("Invalid payload length")

            # Validate checksum (to ensure integrity of the payload)
            if crc32(payload) != checksum:
                Log.warning(f"Checksum mismatch for {frame_id}, chunk {chunk_index}")

            server_time_ms = int(time.time() * 1000) % 0x100000000
            elapsed_time_sec = self.calculate_elapsed_time_ms(timestamp, server_time_ms) / 1000.0

            #print(f"took ({elapsed_time_sec:.3f} sec)")
            
            # Debugging: print out the unpacked header data
            '''
            print(f"Start Marker: {start_marker}")
            print(f"Timestamp: {timestamp}")
            print(f"Frame ID (int): {frame_id}")
            print(f"Total Chunks: {total_chunks}")
            print(f"Chunk Index: {chunk_index}")
            print(f"Chunk Length: {chunk_length}")
            print(f"Checksum: {checksum}")
            print(f"End marker: {end_marker}")
            '''

            ack = struct.pack(ACK_FORMAT, ACK_MARKER,frame_id.to_bytes(3, 'big'), chunk_index)
            self.transport.sendto(ack, addr)

            seen = self._received_chunks.setdefault(frame_id, set())
            if chunk_index in seen:
                return
            # first time: mark as seen
            seen.add(chunk_index)

            if frame_id not in self.frames_in_progress:
                self.frames_in_progress[frame_id] = {
                    'chunks': [None] * total_chunks,
                    'received': 0,
                    'start_time': time.time(),
                }

            frame_entry = self.frames_in_progress[frame_id]
            if frame_entry['chunks'][chunk_index] is None:
                frame_entry['chunks'][chunk_index] = payload
                frame_entry['received'] += 1

            if frame_entry['received'] == total_chunks:
                # All chunks received
                full_frame = b"".join(frame_entry['chunks'])
                # Cleanup
                del self.frames_in_progress[frame_id]

                self.handle_received_frame(full_frame, frame_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            Log.exception(f"Error in datagram_received: {e}")
    
    def handle_received_frame(self, full_frame: bytes, frame_id: int = -1):
        """Process the received frame and reassemble if all chunks are received"""
        raise NotImplementedError("handle_received_frame should be implemented by subclasses")

    def cleanup_old_frames(self, now):
        expired_ids = [fid for fid, entry in self.frames_in_progress.items() if now - entry['start_time'] > self.timeout]
        for fid in expired_ids:
            Log.warning(f"Frame {fid} timeout. Discarded")
            del self.frames_in_progress[fid]
            self._received_chunks.pop(fid, None)

    def error_received(self, exc: Exception):
        Log.exception(f"Error received: {exc}")

    def connection_lost(self, exc: Exception):
        Log.info(f"Closing connection: {exc}")
        self.reset()
        protocol_closed['value'] = True
        print(f"seting protocol closed to {protocol_closed['value']}")


