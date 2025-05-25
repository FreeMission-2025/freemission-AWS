import struct
import ctypes
import time
import numpy as np
from multiprocessing import Lock, Process, Semaphore, Value, shared_memory

class QueueStoppedError(Exception):
    pass

class ShmFrameQueue:
    def __init__(self,
                 frame_shape=(720, 1280, 3),
                 dtype=np.uint8,
                 capacity: int = 60):
        # metadata
        self.frame_shape  = tuple(frame_shape)
        self.dtype        = np.dtype(dtype)
        self.frame_nbytes = int(np.prod(self.frame_shape) * self.dtype.itemsize)
        self.slot_size    = self.frame_nbytes
        self.capacity     = capacity

        # create shared memory + numpy view per slot
        self.shms       = []
        self.shm_names  = []
        self.slot_arrays = []
        for _ in range(capacity):
            shm = shared_memory.SharedMemory(create=True, size=self.slot_size)
            self.shms.append(shm)
            self.shm_names.append(shm.name)
            # directly map the buffer into an ndarray view
            arr = np.ndarray(self.frame_shape,
                             dtype=self.dtype,
                             buffer=shm.buf)
            self.slot_arrays.append(arr)

        # queue pointers & stop flag
        self.head     = Value(ctypes.c_int, 0)
        self.tail     = Value(ctypes.c_int, 0)
        self.stopping = Value(ctypes.c_bool, False)

        # sync primitives
        self.s_full  = Semaphore(0)
        self.s_empty = Semaphore(capacity)
        self.p_lock  = Lock()
        self.g_lock  = Lock()

    def __getstate__(self):
        # only pickle scalars, names, and sync objects
        return {
            'frame_shape':  self.frame_shape,
            'dtype':        self.dtype.str,
            'frame_nbytes': self.frame_nbytes,
            'slot_size':    self.slot_size,
            'capacity':     self.capacity,
            'shm_names':    self.shm_names,
            'head':         self.head,
            'tail':         self.tail,
            'stopping':     self.stopping,
            's_full':       self.s_full,
            's_empty':      self.s_empty,
            'p_lock':       self.p_lock,
            'g_lock':       self.g_lock,
        }

    def __setstate__(self, state):
        # restore metadata
        self.frame_shape  = tuple(state['frame_shape'])
        self.dtype        = np.dtype(state['dtype'])
        self.frame_nbytes = state['frame_nbytes']
        self.slot_size    = state['slot_size']
        self.capacity     = state['capacity']

        # re‐attach shared memory & rebuild numpy views
        self.shm_names   = state['shm_names']
        self.shms        = [
            shared_memory.SharedMemory(name=name, create=False)
            for name in self.shm_names
        ]
        self.slot_arrays = [
            np.ndarray(self.frame_shape, dtype=self.dtype, buffer=shm.buf)
            for shm in self.shms
        ]

        # restore sync primitives
        self.head     = state['head']
        self.tail     = state['tail']
        self.stopping = state['stopping']
        self.s_full   = state['s_full']
        self.s_empty  = state['s_empty']
        self.p_lock   = state['p_lock']
        self.g_lock   = state['g_lock']

    def stop(self):
        with self.stopping.get_lock():
            if not self.stopping.value:
                self.stopping.value = True
                for _ in range(self.capacity):
                    self.s_full.release()

    def put(self, frame: np.ndarray):
        self.s_empty.acquire()
        if self.stopping.value:
            self.s_empty.release()
            return

        with self.p_lock:
            idx = self.tail.value
            self.tail.value = (idx + 1) % self.capacity

        # in‐place copy into the shared‐memory numpy view
        self.slot_arrays[idx][...] = frame
        self.s_full.release()

    def get(self) -> np.ndarray:
        self.s_full.acquire()
        if self.stopping.value:
            self.s_full.release()
            self.s_empty.release()
            raise QueueStoppedError()

        with self.g_lock:
            idx = self.head.value
            self.head.value = (idx + 1) % self.capacity

        # return a fresh copy so the slot can be reused safely
        out = self.slot_arrays[idx].copy()
        self.s_empty.release()
        return out

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
    queue = ShmFrameQueue(frame_shape=frame_shape, capacity=600)

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


if __name__ == "__main__":
    shm_benchmark()

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
    queue = ShmFrameQueue(frame_shape=frame_shape, capacity=10)  # Capacity of 2 to handle just two frames

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