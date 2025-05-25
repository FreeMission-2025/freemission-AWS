import asyncio
hasClient = {'value': False}

class FramedProtocol(asyncio.Protocol):
    START_MARKER = b'\x01\x02\x7F\xED'
    END_MARKER = b'\x03\x04\x7F\xED'
    BUFFER_SIZE = 64 * 1024 * 1024  # 64MB buffer

    def __init__(self):
        self.buffer = bytearray(self.BUFFER_SIZE)
        self.write_offset = 0  # amount of valid data in buffer
        self.transport = None

    def connection_made(self, transport):
        self.transport: asyncio.Transport = transport
        print("Connection established:", transport.get_extra_info('peername'))

        if hasClient['value']:
            self.transport.abort()
        else:
            hasClient['value'] = True

    def data_received(self, data: bytes):
        data_len = len(data)
        if self.write_offset + data_len > self.BUFFER_SIZE:
            print("Buffer overflow! Resetting buffer.")
            self.write_offset = 0  # reset buffer if overflow - customize this behavior if needed

        # Copy incoming data into preallocated buffer
        self.buffer[self.write_offset:self.write_offset + data_len] = data
        self.write_offset += data_len

        self._process_buffer()

    def _process_buffer(self):
        cursor = 0
        while cursor < self.write_offset:
            start_idx = self.buffer.find(self.START_MARKER, cursor, self.write_offset)
            if start_idx == -1:
                break
            end_idx = self.buffer.find(self.END_MARKER, start_idx + len(self.START_MARKER), self.write_offset)
            if end_idx == -1:
                break

            frame_start = start_idx + len(self.START_MARKER)
            frame_end = end_idx
            frame = self.buffer[frame_start:frame_end]
            self._handle_frame(frame)

            cursor = end_idx + len(self.END_MARKER)

        # Shift unprocessed bytes to start of buffer
        remaining = self.write_offset - cursor
        if remaining > 0:
            self.buffer[0:remaining] = self.buffer[cursor:self.write_offset]
        self.write_offset = remaining

    def _handle_frame(self, frame: bytes):
        print(f"Received complete frame: {frame}")
        # Echo back if you want
        self.transport.write(self.START_MARKER + frame + self.END_MARKER)
    
    def connection_lost(self, exc):
        print('The client closed the connection')
        hasClient['value'] = False
        self.transport = None

async def main():
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        FramedProtocol,
        '127.0.0.1', 8888)

    async with server:
        await server.serve_forever()


asyncio.run(main())
