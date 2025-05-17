# test_async_client.py
import asyncio
import time

START = b'\x01\x02\x7F\xED'
END = b'\x03\x04\x7F\xED'

async def send_framed_message(writer, reader, message: bytes, label=""):
    frame = START + message + END
    print(f"Sending ({label}): {frame}")
    writer.write(frame)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received ({label}): {data}")

async def main():
    reader, writer = await asyncio.open_connection('127.0.0.1', 8888)

    # ✅ Basic messages
    await send_framed_message(writer, reader, b'async-1', label='basic-1')
    await send_framed_message(writer, reader, b'async-2', label='basic-2')

    # ✅ Multiple frames in one send
    bulk = START + b'X' + END + START + b'Y' + END
    print(f"Sending (bulk): {bulk}")
    writer.write(bulk)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received (bulk): {data}")

    # ✅ Delayed message split
    print("Sending (delayed split): start...")
    writer.write(START)
    await writer.drain()
    await asyncio.sleep(0.1)
    writer.write(b'delayed' + END)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received (delayed split): {data}")

    # ✅ Garbage before start
    garbage = b'XXXX' + START + b'clean' + END
    print(f"Sending (garbage before start): {garbage}")
    writer.write(garbage)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received (garbage before start): {data}")

    # ✅ START inside payload
    internal_marker_payload = START + b'_inside'
    await send_framed_message(writer, reader, internal_marker_payload, label='start-inside')

    # ✅ END before START
    out_of_order = END + START + b'valid' + END
    print(f"Sending (end-before-start): {out_of_order}")
    writer.write(out_of_order)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received (end-before-start): {data}")

    # ✅ Large payload
    large_data = b'A' * 10000
    await send_framed_message(writer, reader, large_data, label='large')

    # ✅ Repeated markers without frames
    noise = (START + END) * 5
    print(f"Sending (empty frames): {noise}")
    writer.write(noise)
    await writer.drain()
    data = await reader.read(1024)
    print(f"Received (empty frames): {data}")

    # ✅ Abrupt close mid-frame
    print("Sending (partial then abrupt close)...")
    writer.write(START + b'partial-but-no-end')
    await writer.drain()
    writer.close()
    await writer.wait_closed()
    print("Connection closed abruptly after partial send.")

asyncio.run(main())
