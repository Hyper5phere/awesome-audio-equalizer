import time
import soundcard as sc
from threading import Thread
from queue import Queue, Empty

output_speaker_name = "BenQ GW2765"

speakers = sc.all_speakers()

speaker = next(s for s in speakers if output_speaker_name in s.name)

sample_rate = 96000
playback_seconds = 10
input_speaker_name = "Digital Audio (S/PDIF)"
block_size = 1024*4
record_size = block_size * 10
num_samples = playback_seconds * sample_rate
num_iters = num_samples // record_size

mics = sc.all_microphones(include_loopback=True)

loopback_mic = next(m for m in mics if input_speaker_name in m.name)

audio_queue = Queue()
playing = True

def play_task():
    with speaker.player(samplerate=sample_rate, blocksize=block_size) as sp:
        while playing:
            try:
                data = audio_queue.get_nowait()
                sp.play(data)
            except Empty:
                time.sleep(0.001)

play_thread = Thread(target=play_task)
play_thread.start()

with loopback_mic.recorder(samplerate=sample_rate, blocksize=block_size) as mic:
    for _ in range(record_size):
        audio_queue.put(mic.record(record_size))

playing = False
play_thread.join()
