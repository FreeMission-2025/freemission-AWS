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
HEADER_FORMAT = "!4s I 3s I I"  # Updated header format
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

ACK_MARKER    = b'\x05\x06\x7F\xED'
ACK_FORMAT    = "!4s 3s"       # | 4-byte marker | 3-byte frame_id 
ACK_SIZE      = struct.calcsize(ACK_FORMAT)

hasClient = {'value': False}

class BaseTCP (asyncio.Protocol):
    START_MARKER = b'\x01\x02\x7F\xED'
    END_MARKER = b'\x03\x04\x7F\xED'
    BUFFER_SIZE = 64 * 1024 * 1024  # 64MB buffer

    def __init__(self):
        self.buffer = bytearray(self.BUFFER_SIZE)
        self.write_offset = 0  # amount of valid data in buffer
        self.transport = None
        self.frames_in_progress = {}
        self._received_chunks: Dict[int, Set[int]] = {}
        self.loop = asyncio.get_event_loop()
        self.timeout = 0.5
        self.is_stopped = False

    def stop(self):
        self.is_stopped = True

    def connection_made(self, transport):
        self.transport: asyncio.Transport = transport
        print("Connection established:", transport.get_extra_info('peername'))

        if hasClient['value']:
            self.transport.abort()
        else:
            hasClient['value'] = True
            sock: socket.socket = transport.get_extra_info('socket')

            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            tcp_nodelay = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
            print(f"TCP_NODELAY after setting: {tcp_nodelay}")

            default_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            default_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            Log.info(f"Default SO_RCVBUF: {default_rcvbuf} bytes")
            Log.info(f"Default SO_RCVBUF: {default_sndbuf} bytes")

            platforms = platform.system()
            original_rmem_max = 0
            original_wmem_max = 0

            if platforms == "Linux":
                original_rmem_max = subprocess.check_output(["sysctl", "net.core.rmem_max"]).decode().strip().split('=')[1]
                Log.info(f"Original rmem_max: {original_rmem_max} bytes")
                Log.info("Setting new rmem_max to 32 mb")
                subprocess.run(["sysctl", "-w", "net.core.rmem_max=33554432"], check=True)

                original_wmem_max = subprocess.check_output(["sysctl", "net.core.wmem_max"]).decode().strip().split('=')[1]
                Log.info(f"Original wmem_max: {original_wmem_max} bytes")
                Log.info("Setting new wmem_max to 32 mb")
                subprocess.run(["sysctl", "-w", "net.core.wmem_max=33554432"], check=True)

            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024 * 1024)

            if platforms == "Linux":
                if original_rmem_max != 0:
                    Log.info("Restoring default value of rmem_max")
                    subprocess.run(["sysctl", "-w", f"net.core.rmem_max={original_rmem_max}"], check=True)
                if original_wmem_max != 0:
                    Log.info("Restoring default value of wmem_max")
                    subprocess.run(["sysctl", "-w", f"net.core.wmem_max={original_wmem_max}"], check=True)

            new_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            new_sndbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            Log.info(f"new SO_RCVBUF: {new_rcvbuf} bytes")
            Log.info(f"new new_sndbuf: {new_sndbuf} bytes")


    def data_received(self, data: bytes):
        try:
            if self.is_stopped:
                return
            
            data_len = len(data)
            if self.write_offset + data_len > self.BUFFER_SIZE:
                print("Buffer overflow! Resetting buffer.")
                self.write_offset = 0  # reset buffer if overflow - customize this behavior if needed

            # Copy incoming data into preallocated buffer
            self.buffer[self.write_offset:self.write_offset + data_len] = data
            self.write_offset += data_len

            self._process_buffer()
        except Exception as e:
            Log.exception(f"Error in data_received: {e}")

    def _process_buffer(self):
        cursor = 0
        while cursor < self.write_offset:
            start_idx = self.buffer.find(self.START_MARKER, cursor, self.write_offset)
            if start_idx == -1:
                break
            end_idx = self.buffer.find(self.END_MARKER, start_idx + len(self.START_MARKER), self.write_offset)
            if end_idx == -1:
                break

            data = self.buffer[start_idx:end_idx + len(self.END_MARKER)]
            self._handle_packet(data)

            cursor = end_idx + len(self.END_MARKER)

        # Shift unprocessed bytes to start of buffer
        remaining = self.write_offset - cursor
        if remaining > 0:
            self.buffer[0:remaining] = self.buffer[cursor:self.write_offset]
        self.write_offset = remaining

    def calculate_elapsed_time_ms(self, client_timestamp: int, server_timestamp: int) -> int:
        return (server_timestamp - client_timestamp) % 0x100000000  # 2^32
    
    def _handle_packet(self, data: bytes):
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
        start_marker, timestamp, frame_id, chunk_length, checksum = struct.unpack(HEADER_FORMAT, header)
        frame_id = int.from_bytes(frame_id, byteorder='big')

        # Validate start marker
        if start_marker != START_MARKER:
            raise ValueError("Invalid start marker")
        
        if chunk_length != len(payload):
            raise ValueError("Invalid payload length")

        # Validate checksum (to ensure integrity of the payload)
        if crc32(payload) != checksum:
            Log.warning(f"Checksum mismatch for {frame_id}")

        #server_time_ms = int(time.time() * 1000) % 0x100000000
        #elapsed_time_sec = self.calculate_elapsed_time_ms(timestamp, server_time_ms) / 1000.0

        ack = struct.pack(ACK_FORMAT, ACK_MARKER,frame_id.to_bytes(3, 'big'))
        self.transport.write(ack)

        self.handle_received_frame(full_frame=payload, frame_id=frame_id)

    def handle_received_frame(self, full_frame: bytes, frame_id: int = -1):
        """Process the received frame and reassemble if all chunks are received"""
        raise NotImplementedError("handle_received_frame should be implemented by subclasses")

    def error_received(self, exc: Exception):
        Log.exception(f"Error received: {exc}")

    def connection_lost(self, exc):
        print('The client closed the connection')
        hasClient['value'] = False
        self.transport = None
