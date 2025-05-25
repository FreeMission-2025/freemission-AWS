import ctypes
from dataclasses import dataclass
from utils.multi_process import shared_memory, Synchronized, SynchronizedArray
from utils.multi_process import _Lock, _Semaphore
import numpy as np

@dataclass
class SyncObject:
    frame_ids : SynchronizedArray
    head      : Synchronized
    tail      : Synchronized
    stopping  : Synchronized
    s_full    : _Semaphore
    s_empty   : _Semaphore
    p_lock    : _Lock
    g_lock    : _Lock


class QueueStoppedError(Exception):
    pass

class ShmQueue:
    def __init__(self, shape, sync: SyncObject, dtype=np.uint8, capacity=120):
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

        self.frame_ids = sync.frame_ids 

        # Circular queue pointers (head, tail)
        self.head = sync.head
        self.tail = sync.tail
        self.stopping = sync.stopping

        # Queue slot availability semaphores
        self.s_full  = sync.s_full 
        self.s_empty = sync.s_empty
        self.p_lock  = sync.p_lock
        self.g_lock  = sync.g_lock

    def stop(self):
        with self.stopping.get_lock():
            if self.stopping.value == True:
                return
            self.stopping.value = True
            # Wake up any blocked consumers
            for _ in range(self.capacity):
                self.s_full.release()  # Ensure .get() unblocks

    def put(self, frame: np.ndarray, frame_id: int):
        # Block until there is space in the queue
        self.s_empty.acquire()
        
        with self.p_lock:
            idx = self.tail.value
            self.tail.value = (idx + 1) % self.capacity

        shm = self.shms[idx]
        buf = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
        np.copyto(buf, frame)

        self.frame_ids[idx] = frame_id
        self.s_full.release()  # Signal that there is an item available for consumption


    def get(self) -> tuple[np.ndarray, int]:
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
        frame_id = int(self.frame_ids[idx])
        self.s_empty.release()  # Signal that there is space available in the queue
        return frame, frame_id
    
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
    
    def close(self):
        """Should be called once by parent & child process"""
        for shm in self.shms:
            shm.close()

    def cleanup(self):
        """Should be called only by parrent process"""
        for shm in self.shms:
            shm.close()
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
        