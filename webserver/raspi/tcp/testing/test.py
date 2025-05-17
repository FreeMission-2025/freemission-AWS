import asyncio

hasClient = {'value': False}

class FramedProtocol(asyncio.Protocol):
    START_MARKER = b'\x01\x02\x7F\xED'
    END_MARKER = b'\x03\x04\x7F\xED'

    def __init__(self):
        self.buffer = bytearray()
        self.transport = None

    def connection_made(self, transport):
        self.transport: asyncio.Transport = transport
        print("Connection established:", transport.get_extra_info('peername'))

        if hasClient['value']:
            self.transport.close()
            self.transport = None
        else:
            hasClient['value'] = True
        

    def data_received(self, data: bytes):
        self.buffer.extend(data)
        self._process_buffer()

    def _process_buffer(self):
        while True:
            start_idx = self.buffer.find(self.START_MARKER)
            if start_idx == -1:
                # Keep last few bytes in case they're a partial start marker
                if len(self.buffer) >= len(self.START_MARKER):
                    self.buffer = self.buffer[-(len(self.START_MARKER) - 1):]
                return

            end_idx = self.buffer.find(self.END_MARKER, start_idx + len(self.START_MARKER))
            if end_idx == -1:
                # Start found but end not yet; wait for more data
                if start_idx > 0:
                    # Discard garbage before the start
                    self.buffer = self.buffer[start_idx:]
                return

            # Full frame found
            frame = self.buffer[start_idx + len(self.START_MARKER):end_idx]
            self._handle_frame(frame)

            # Remove processed part
            self.buffer = self.buffer[end_idx + len(self.END_MARKER):]

    def _handle_frame(self, frame: bytes):
        print(f"Received complete frame: {frame}")
        # Echo back (optional)
        self.transport.write(self.START_MARKER + frame + self.END_MARKER)


async def main():
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    server = await loop.create_server(
        FramedProtocol,
        '127.0.0.1', 8888)

    async with server:
        await server.serve_forever()


asyncio.run(main())