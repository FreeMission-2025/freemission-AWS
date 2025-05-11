import ctypes
from multiprocessing import Lock, Process, Semaphore, Value, shared_memory, Queue
import time
import numpy as np

class QueueStoppedError(Exception):
    pass

class ShmQueue:
    def __init__(self, shape, dtype=np.uint8, capacity=60):
        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.capacity = capacity
        self.frame_size = int(np.prod(shape))

        # Shared memory blocks for each frame
        self.shms = [
            shared_memory.SharedMemory(create=True, size=self.frame_size * self.dtype.itemsize)
            for _ in range(capacity)
        ]

        self.views = [
            np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
            for shm in self.shms
        ]

        self.names = [shm.name for shm in self.shms]

        # Circular queue pointers (head, tail)
        self.head = Value(ctypes.c_int, 0)
        self.tail = Value(ctypes.c_int, 0)
        self.stopping = Value(ctypes.c_bool, False) 

        # Queue slot availability semaphores
        self.s_full = Semaphore(0)            # initially empty
        self.s_empty = Semaphore(capacity)    # initially all empty
        self.p_lock = Lock()
        self.g_lock = Lock()
        self.lock = Lock()

    def stop(self):
        with self.stopping.get_lock():
            if self.stopping.value == True:
                return
            self.stopping.value = True
            # Wake up any blocked consumers
            for _ in range(self.capacity):
                self.s_full.release()  # Ensure .get() unblocks

    def put(self, frame: np.ndarray):
        # Block until there is space in the queue
        self.s_empty.acquire()

        if self.stopping.value:
            self.s_empty.release()
            return
        
        with self.p_lock:
            idx = self.tail.value
            self.tail.value = (idx + 1) % self.capacity

        self.views[idx][...] = frame
        self.s_full.release()  # Signal that there is an item available for consumption

    def get(self) -> np.ndarray:
        # Block until there is an item in the queue
        self.s_full.acquire() 
        if self.stopping.value:
            self.s_full.release()
            self.s_empty.release()
            raise QueueStoppedError()

        with self.g_lock:
            idx = self.head.value
            self.head.value = (idx + 1) % self.capacity

        frame = self.views[idx].copy()
        self.s_empty.release()  # Signal that there is space available in the queue
        return frame
    
    def qsize(self) -> int:
        """Return the current number of frames in the queue."""
        # Must be synchronized to avoid race conditions
        with self.p_lock, self.g_lock:
            return (self.tail.value - self.head.value + self.capacity) % self.capacity

    def empty(self) -> bool:
        """Return True if the queue is empty."""
        return self.qsize() == 0

    def full(self) -> bool:
        """Return True if the queue is full."""
        return self.qsize() == self.capacity

    def cleanup(self):
        for shm in self.shms:
            shm.close()
            try:
                shm.unlink()
            except FileNotFoundError:
                pass

def benchmark_put(queue, num_frames, frame):
    start = time.perf_counter()
    for _ in range(num_frames):
        queue.put(frame)
    duration = time.perf_counter() - start
    rate = num_frames / duration
    print(f"num_frames: {num_frames}, Put() time: {duration:.4f}s, {rate:.2f} frames/s")

def benchmark_get(queue, num_frames):
    start = time.perf_counter()
    for _ in range(num_frames):
        frame = queue.get()  # Retrieves a frame (not used but it simulates processing)
    duration = time.perf_counter() - start
    rate = num_frames / duration
    print(f"num_frames: {num_frames}, Get() time: {duration:.4f}s, {rate:.2f} frames/s")
    
def shm_benchmark():
    frame_shape = (720, 1280, 3)  # Example frame size (720p RGB image)
    num_frames = 30  # Number of frames to benchmark
    frame = np.random.randint(0, 256, size=frame_shape, dtype=np.uint8)  # Random synthetic frame
    
    # Initialize the ShmQueue
    queue = ShmQueue(shape=frame_shape, capacity=600)

    # Create producer (put operation) and consumer (get operation) processes
    producer_process = Process(target=benchmark_put, args=(queue, num_frames, frame))
    consumer_process = Process(target=benchmark_get, args=(queue, num_frames))

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

def mp_benchmark():
    frame_shape = (720, 1280, 3)  # Example frame size (720p RGB image)
    num_frames = 30  # Number of frames to benchmark
    frame = np.random.randint(0, 256, size=frame_shape, dtype=np.uint8)  # Random synthetic frame
    
    # Initialize the ShmQueue
    queue = Queue(maxsize=600)

    # Create producer (put operation) and consumer (get operation) processes
    producer_process = Process(target=benchmark_put, args=(queue, num_frames, frame))
    consumer_process = Process(target=benchmark_get, args=(queue, num_frames))

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

if __name__ == "__main__":
    shm_benchmark()
    mp_benchmark()

## Correctness check
''' 
def consumer(frame1, frame2, queue):
        frame1_get = queue.get()
        frame2_get = queue.get()

        # Step 1: Check shape consistency
        assert frame1.shape == frame1_get.shape, "Shape mismatch for frame1!"
        assert frame2.shape == frame2_get.shape, "Shape mismatch for frame2!"

        # Step 2: Check data consistency (if the frames are identical)
        assert np.array_equal(frame1, frame1_get), "Data mismatch for frame1!"
        assert np.array_equal(frame2, frame2_get), "Data mismatch for frame2!"

def main():
    frame_shape = (720, 1280, 3)  # 720p RGB image
    queue = ShmQueue(shape=frame_shape, capacity=10)  # Capacity of 2 to handle just two frames

    frame1 = np.random.randint(6, 256, size=(720, 1280, 3), dtype=np.uint8)
    print("f1:")
    print(frame1[:1, :5]) 

    frame2 = np.random.randint(2, 256, size=(720, 1280, 3), dtype=np.uint8)
    print("f2:")
    print(frame2[:1, :5]) 

    queue.put(frame1.copy())
    queue.put(frame2.copy())


    consumer_process = Process(target=consumer, args=(frame1.copy(), frame2.copy(), queue,))
    consumer_process.start()
    consumer_process.join()
    queue.stop()
    queue.cleanup()

if __name__ == "__main__":
    main()
'''