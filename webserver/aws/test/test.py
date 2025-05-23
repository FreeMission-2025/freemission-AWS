import asyncio
import heapq
import time
import pytest

from utils.ordered_packet import OrderedPacketDispatcher
import utils.ordered_packet as disp_module
import constants
from constants import frame_dispatch_reset, Format

@pytest.fixture(autouse=True)
def reset_globals(monkeypatch):
    # Reset global flags before each test
    frame_dispatch_reset['value'] = False
    # Default: enable inference to accept single output queue
    monkeypatch.setattr(constants, 'INFERENCE_ENABLED', True)
    monkeypatch.setattr(disp_module, 'INFERENCE_ENABLED', True)
    # Formats default to H264 (only relevant when inference disabled)
    monkeypatch.setattr(constants, 'INCOMING_FORMAT', Format.H264)
    monkeypatch.setattr(constants, 'OUTGOING_FORMAT', Format.H264)
    monkeypatch.setattr(disp_module, 'INCOMING_FORMAT', Format.H264)
    monkeypatch.setattr(disp_module, 'OUTGOING_FORMAT', Format.H264)
    yield

async def run_dispatcher(dispatcher, duration=0.1):
    task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(duration)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_ordered_delivery():
    async def inner():
        input_q = asyncio.Queue()
        output_q = asyncio.Queue()
        disp = OrderedPacketDispatcher(input_q, output_q, timeout=0.01, poll_interval=0.005)

        await input_q.put((4, b'data4'))
        await input_q.put((2, b'data2'))
        await input_q.put((1, b'data1'))
        await input_q.put((3, b'data3'))

        await run_dispatcher(disp, duration=0.05)

        results = []
        while not output_q.empty():
            packet_data, frame_id = output_q.get_nowait()
            results.append((frame_id, packet_data))

        assert results == [(1, b'data1'), (2, b'data2'), (3, b'data3'), (4, b'data4')]

    asyncio.run(inner())


def test_timeout_skip_missing():
    async def inner():
        input_q = asyncio.Queue()
        output_q = asyncio.Queue()
        disp = OrderedPacketDispatcher(input_q, output_q, timeout=0.01, poll_interval=0.005)

        await input_q.put((2, b'data2'))

        await run_dispatcher(disp, duration=0.05)

        assert not output_q.empty()
        packet_data, frame_id = output_q.get_nowait()
        assert frame_id == 2 and packet_data == b'data2'

    asyncio.run(inner())


def test_reset_behavior():
    async def inner():
        input_q = asyncio.Queue()
        output_q = asyncio.Queue()
        disp = OrderedPacketDispatcher(input_q, output_q, timeout=0.05, poll_interval=0.01)

        # Trigger reset before pushing any frames
        frame_dispatch_reset['value'] = True
        await asyncio.sleep(0)

        # Push frame 1 after reset
        await input_q.put((1, b'data1'))

        await run_dispatcher(disp, duration=0.05)

        # Frame should be dispatched normally under inference
        assert not output_q.empty()
        packet_data, frame_id = output_q.get_nowait()
        assert frame_id == 1 and packet_data == b'data1'

    asyncio.run(inner())


def test_multiple_output_queues_list():
    async def inner():
        # Temporarily disable inference and set H264->H264 to trigger list-queue branch
        disp_module.INFERENCE_ENABLED = False
        constants.INFERENCE_ENABLED = False
        constants.INCOMING_FORMAT = Format.H264
        constants.OUTGOING_FORMAT = Format.H264

        input_q = asyncio.Queue()
        q1 = asyncio.Queue()
        q2 = asyncio.Queue()
        disp = OrderedPacketDispatcher(input_q, [q1, q2], timeout=0.01, poll_interval=0.005)

        await input_q.put((1, b'data1'))
        await run_dispatcher(disp, duration=0.05)

        for q in (q1, q2):
            assert not q.empty()
            timestamp, packet = q.get_nowait()
            assert packet == b'data1'
            assert isinstance(timestamp, float)

    asyncio.run(inner())