import os
import sys

# Add the directory containing FFmpeg DLLs
ffmpeg_bin = r"C:\ffmpeg\bin"
os.add_dll_directory(ffmpeg_bin)

import av

def list_available_decoders():
    print("Available video decoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'r')  # 'r' for reading (decoder)
            if codec.type == 'video':
                print(f"  {name}: {codec.long_name}")
        except:
            continue  # Skip if not a decoder or invalid

    print("\nAvailable audio decoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'r')
            if codec.type == 'audio':
                print(f"  {name}: {codec.long_name}")
        except:
            continue

def list_available_encoders():
    print("Available video encoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'w')  # 'w' for writing (encoder)
            if codec.type == 'video':
                print(f"  {name}: {codec.long_name}")
        except:
            continue  # Skip if not an encoder or invalid

if __name__ == "__main__":
    list_available_decoders()


''' 
import av

print("Available video decoders:\n")

for name in av.codecs_available:
    try:
        codec = av.codec.Codec(name, 'r')  # 'r' for decoder
        if codec.type == 'video':
            print(f"- {codec.name} ({codec.long_name})")
    except Exception:
        continue  # Ignore codecs that can't be opened as decoders

'''