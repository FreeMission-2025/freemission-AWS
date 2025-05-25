import multiprocessing

# Explicitly set spawn method beause linux by default use fork 
# Fork makes socket, file descriptors, & other resources shared with child process which is so bad
# get the spawn context incase other module force modified to fork
mp = multiprocessing.get_context('spawn')

# Re-export selected safe constructs from the context
Lock = mp.Lock
Semaphore = mp.Semaphore
Value = mp.Value
Array = mp.Array

# If you need shared_memory too (note: shared_memory is not context-dependent)
from multiprocessing import shared_memory, Process

# Re-export sharedctypes types (these are not context-specific, just type hints)
from multiprocessing.sharedctypes import Synchronized, SynchronizedArray

# Optional: For more precise typing of the synchronization objects
from multiprocessing.synchronize import Lock as _Lock
from multiprocessing.synchronize import Semaphore as _Semaphore


__all__ = [
    "Lock",
    "Semaphore",
    "Value",
    "Array",
    "shared_memory",
    "Synchronized",
    "SynchronizedArray",
    "_Lock",
    "_Semaphore",
    "Process"
]
