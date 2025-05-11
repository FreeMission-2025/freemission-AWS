import struct
from multiprocessing import Lock, Process, Semaphore, Value, shared_memory, Queue
import ctypes
import time

class QueueStoppedError(Exception):
    pass

class ShmQueue:
    def __init__(self, max_frame_size=15360, capacity=60):
        self.max_frame_size = max_frame_size
        self.header_size = 4  # 4 bytes for the length header
        self.slot_size = self.header_size + self.max_frame_size
        self.capacity = capacity

        # Create shared memory blocks and remember their names
        self.shms = []
        self.shm_names = []
        for _ in range(self.capacity):
            shm = shared_memory.SharedMemory(create=True, size=self.slot_size)
            self.shms.append(shm)
            self.shm_names.append(shm.name)
        self.buffers = [shm.buf for shm in self.shms]

        # Circular queue pointers (head, tail)
        self.head = Value(ctypes.c_int, 0)
        self.tail = Value(ctypes.c_int, 0)
        self.stopping = Value(ctypes.c_bool, False)

        # Semaphores and locks
        self.s_full = Semaphore(0)
        self.s_empty = Semaphore(self.capacity)
        self.p_lock = Lock()  # protects tail
        self.g_lock = Lock()  # protects head

    def __getstate__(self):
        # Only pickle what can be sent over multiprocessing pipes
        return {
            'max_frame_size': self.max_frame_size,
            'header_size':     self.header_size,
            'slot_size':       self.slot_size,
            'capacity':        self.capacity,
            'shm_names':       self.shm_names,
            'head':            self.head,
            'tail':            self.tail,
            'stopping':        self.stopping,
            's_full':          self.s_full,
            's_empty':         self.s_empty,
            'p_lock':          self.p_lock,
            'g_lock':          self.g_lock,
        }

    def __setstate__(self, state):
        # Restore constants
        self.max_frame_size = state['max_frame_size']
        self.header_size     = state['header_size']
        self.slot_size       = state['slot_size']
        self.capacity        = state['capacity']

        # Re-open each shared memory by name
        self.shm_names = state['shm_names']
        self.shms = [
            shared_memory.SharedMemory(create=False, name=name)
            for name in self.shm_names
        ]
        self.buffers = [shm.buf for shm in self.shms]

        # Restore synchronization primitives
        self.head     = state['head']
        self.tail     = state['tail']
        self.stopping = state['stopping']
        self.s_full   = state['s_full']
        self.s_empty  = state['s_empty']
        self.p_lock   = state['p_lock']
        self.g_lock   = state['g_lock']

    def stop(self):
        with self.stopping.get_lock():
            if self.stopping.value:
                return
            self.stopping.value = True
            # Unblock any waiting getters
            for _ in range(self.capacity):
                self.s_full.release()

    def put(self, data: bytes):
        if len(data) > self.max_frame_size:
            raise ValueError(f"Data size {len(data)} exceeds max_frame_size {self.max_frame_size}")

        self.s_empty.acquire()
        if self.stopping.value:
            # if we're stopping, put it back and bail out
            self.s_empty.release()
            return

        with self.p_lock:
            idx = self.tail.value
            self.tail.value = (idx + 1) % self.capacity

        buf = self.buffers[idx]
        # write length header, big‐endian uint32
        buf[0:self.header_size] = struct.pack('!I', len(data))
        # write payload
        buf[self.header_size:self.header_size+len(data)] = data

        self.s_full.release()

    def get(self) -> bytes:
        self.s_full.acquire()
        if self.stopping.value:
            # put tokens back so other getters/unblockers can proceed
            self.s_full.release()
            self.s_empty.release()
            raise QueueStoppedError()

        with self.g_lock:
            idx = self.head.value
            self.head.value = (idx + 1) % self.capacity

        buf = self.buffers[idx]
        # read length, then data
        length = struct.unpack('!I', bytes(buf[0:self.header_size]))[0]
        data = bytes(buf[self.header_size:self.header_size+length])

        self.s_empty.release()
        return data

    def qsize(self) -> int:
        with self.p_lock, self.g_lock:
            return (self.tail.value - self.head.value + self.capacity) % self.capacity

    def empty(self) -> bool:
        return self.qsize() == 0

    def full(self) -> bool:
        return self.qsize() == self.capacity

    def cleanup(self):
        for shm in self.shms:
            try:
                shm.close()
                shm.unlink()
            except FileNotFoundError:
                pass


def benchmark_put(queue, iteration, frame):
    start = time.perf_counter()
    for _ in range(iteration):
        queue.put(frame)
    duration = time.perf_counter() - start
    rate = iteration / duration
    print(f"iteration: {iteration}, Put() time: {duration:.4f}s, {rate:.2f} frames/s")

def benchmark_get(queue, iteration):
    start = time.perf_counter()
    for _ in range(iteration):
        frame = queue.get()  # Retrieves a frame (not used but it simulates processing)
    duration = time.perf_counter() - start
    rate = iteration / duration
    print(f"iteration: {iteration}, Get() time: {duration:.4f}s, {rate:.2f} frames/s")
    

def shm_benchmark():
    # params
    max_frame_size = 15360    # bytes
    capacity       = 1000
    iteration      = 30  # number of frames to push / pop
    frame_size     = 15240    # we'll benchmark with 1 KiB frames

    # 1 KiB dummy payload
    frame = bytes([0xAB]) * frame_size

    # create queue
    queue = ShmQueue(max_frame_size=max_frame_size, capacity=capacity)

    # Create producer (put operation) and consumer (get operation) processes
    producer_process = Process(target=benchmark_put, args=(queue, iteration, frame))
    consumer_process = Process(target=benchmark_get, args=(queue, iteration))

    # Start the processes
    print("Starting shm_benchmark")
    producer_process.start()
    consumer_process.start()

    # Wait for both processes to finish
    producer_process.join()
    consumer_process.join()

    # Cleanup
    queue.stop()
    queue.cleanup()
    print("\nBenchmark completed. Shared memory cleaned up.")

def mp_benchmark():
    # params
    max_frame_size = 15360    # bytes
    capacity       = 1000
    iteration      = 30  # number of frames to push / pop
    frame_size     = 15240    # we'll benchmark with 1 KiB frames

    # 1 KiB dummy payload
    frame = bytes([0xAB]) * frame_size

    # create queue
    queue = Queue(maxsize=capacity)

    # Create producer (put operation) and consumer (get operation) processes
    producer_process = Process(target=benchmark_put, args=(queue, iteration, frame))
    consumer_process = Process(target=benchmark_get, args=(queue, iteration))

    # Start the processes
    print("Starting mp_benchmark")
    producer_process.start()
    consumer_process.start()

    # Wait for both processes to finish
    producer_process.join()
    consumer_process.join()

    # Cleanup
    queue.close()
    queue.cancel_join_thread()
    print("\nBenchmark completed. Shared memory cleaned up.")

if __name__ == "__main__":
    shm_benchmark()   
    mp_benchmark()
''' 
def consumer(expected1, expected2, q: ShmQueue):
    try:
        d1 = q.get()
        d2 = q.get()
        assert d1 == expected1, f"Expected {expected1!r}, got {d1!r}"
        assert d2 == expected2, f"Expected {expected2!r}, got {d2!r}"
        print("Consumer: Test passed!")
    except QueueStoppedError:
        print("Consumer: Queue stopped early")


def main():
    # small sizes for demonstration
    queue = ShmQueue(max_frame_size=15, capacity=10)

    data1 = b'hello 343434  '
    data2 = b'worl 344444444444444444444d!'

    # Producer puts two items
    queue.put(data1)
    queue.put(data2)

    # Spawn a consumer process that unpickles the ShmQueue
    p = Process(target=consumer, args=(data1, data2, queue))
    p.start()
    p.join()

    # Signal shutdown and clean up
    queue.stop()
    queue.cleanup()

if __name__ == "__main__":
    main()

'''
