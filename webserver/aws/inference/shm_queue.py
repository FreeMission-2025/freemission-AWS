import ctypes
from multiprocessing import Lock, Semaphore, Value, shared_memory
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