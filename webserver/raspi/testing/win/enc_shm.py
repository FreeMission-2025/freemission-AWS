from multiprocessing import shared_memory, Event, Process
import numpy as np
import cv2
import time

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
CHANNELS = 3  # for BGR

frame_shape = (FRAME_HEIGHT, FRAME_WIDTH, CHANNELS)
frame_size = np.prod(frame_shape) * np.dtype(np.uint8).itemsize  # Correct to bytes

def capture_video(shm_name, ready_event: Event):
    shm = shared_memory.SharedMemory(name=shm_name)
    frame_buffer = np.ndarray(frame_shape, dtype=np.uint8, buffer=shm.buf)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame_buffer[:] = frame  # write directly to shared memory
        ready_event.set()        # signal that new frame is ready

def viewer(shm_name, ready_event: Event):
    shm = shared_memory.SharedMemory(name=shm_name)
    frame_buffer = np.ndarray(frame_shape, dtype=np.uint8, buffer=shm.buf)

    try:
        while True:
            if ready_event.wait(timeout=1):
                frame = frame_buffer.copy()  # copy out before display
                cv2.imshow("SharedMemory Viewer", frame)
                ready_event.clear()

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        shm.close()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    shm = shared_memory.SharedMemory(create=True, size=int(frame_size))  # Cast to int
    event = Event()

    p1 = Process(target=capture_video, args=(shm.name, event))
    p2 = Process(target=viewer, args=(shm.name, event))

    p1.start()
    p2.start()

    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        pass
    finally:
        shm.close()
        shm.unlink()
