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
        
        with self.p_lock:
            idx = self.tail.value
            self.tail.value = (idx + 1) % self.capacity

        shm = self.shms[idx]
        buf = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
        np.copyto(buf, frame)
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
            
        shm = self.shms[idx]
        frame = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf).copy()
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
def consumer( queue):
    frame1_get = queue.get()
    frame2_get = queue.get()

    print(f"f1: {frame1_get.ravel()[:5]}")
    print(f"f2: {frame2_get.ravel()[:5]}")

def main():
    frame_shape = (720, 1280, 3)  # 720p RGB image
    queue = ShmQueue(shape=frame_shape, capacity=10)  # Capacity of 2 to handle just two frames
    consumer_process = Process(target=consumer, args=(queue,))
    consumer_process.start()

    frame1 = np.random.randint(6, 256, size=(720, 1280, 3), dtype=np.uint8)
    print("f1:")
    print(frame1.ravel()[:5]) 
    queue.put(frame1.copy())

    frame2 = np.random.randint(2, 256, size=(720, 1280, 3), dtype=np.uint8)
    print("f2:")
    print(frame2.ravel()[:5]) 

    queue.put(frame2.copy())


    consumer_process.join()
    queue.stop()
    queue.cleanup()

if __name__ == "__main__":
    main()
'''

'''
    @staticmethod
    def from_existing(names, shape, dtype, head, tail, stopping, s_full, s_empty, p_lock, g_lock):
        dtype = np.dtype(dtype)
        shms = [shared_memory.SharedMemory(name=name) for name in names]
        views = [
            np.ndarray(shape, dtype=dtype, buffer=shm.buf)
            for shm in shms
        ]

        q = ShmQueue.__new__(ShmQueue)
        q.shape = shape
        q.dtype = dtype
        q.capacity = len(names)
        q.frame_size = int(np.prod(shape))
        q.shms = shms
        q.views = views
        q.names = names
        q.head = head
        q.tail = tail
        q.stopping = stopping
        q.s_full = s_full
        q.s_empty = s_empty
        q.p_lock = p_lock
        q.g_lock = g_lock
        return q

    def __getstate__(self):
    # Serialize only the information needed to reconstruct in another process
    return {
        'names': self.names,
        'shape': self.shape,
        'dtype': self.dtype,
        'head': self.head,
        'tail': self.tail,
        'stopping': self.stopping,
        's_full': self.s_full,
        's_empty': self.s_empty,
        'p_lock': self.p_lock,
        'g_lock': self.g_lock,
    }

    def __setstate__(self, state):
        self.shape = state['shape']
        self.dtype = np.dtype(state['dtype'])
        self.names = state['names']
        self.capacity = len(self.names)
        self.frame_size = int(np.prod(self.shape))

        self.shms = [shared_memory.SharedMemory(name=name) for name in self.names]
        self.views = [
            np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
            for shm in self.shms
        ]

        self.head = state['head']
        self.tail = state['tail']
        self.stopping = state['stopping']
        self.s_full = state['s_full']
        self.s_empty = state['s_empty']
        self.p_lock = state['p_lock']
        self.g_lock = state['g_lock']


'''