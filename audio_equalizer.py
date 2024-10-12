import time
import soundcard as sc
from queue import Empty

from multiprocessing import Process, Queue, Value

sample_rate = 96000
playback_seconds = 1000
# input_speaker_name = "Digital Audio (S/PDIF)"
input_speaker_name = "BenQ GW2765"
block_size = 1024*16
record_size = block_size * 4
num_samples = playback_seconds * sample_rate
num_iters = num_samples // record_size
volume = 0.2


def play_task(playing, audio_queue, sample_rate, block_size):
    # output_speaker_name = "BenQ GW2765"
    output_speaker_name = "Digital Audio (S/PDIF)"
    speakers = sc.all_speakers()
    speaker = next(s for s in speakers if output_speaker_name in s.name)
    with speaker.player(samplerate=sample_rate.value, blocksize=block_size.value) as sp:
        while playing.value:
            try:
                data = audio_queue.get_nowait()
                sp.play(data)
            except Empty:
                time.sleep(0.00001)


if __name__ == '__main__':
    mics = sc.all_microphones(include_loopback=True)

    loopback_mic = next(m for m in mics if input_speaker_name in m.name)

    audio_queue = Queue()
    playing = Value('b', True)
    sample_rate_shared = Value('i', sample_rate)
    block_size_shared = Value('i', block_size)

    play_process = Process(target=play_task,
                           args=(playing, audio_queue,
                                 sample_rate_shared,
                                 block_size_shared))
    
    with loopback_mic.recorder(samplerate=sample_rate, blocksize=block_size) as mic:
        try:
            play_process.start()
            for _ in range(num_iters):
                audio_queue.put(mic.record(record_size) * volume)
        finally:
            playing.value = False
            play_process.join()
