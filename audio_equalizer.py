import time
import numpy as np
import soundcard as sc
from queue import Empty
from scipy.signal import butter, lfilter

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

freq_bands = [
    (40, 76),
    (77, 109),
    (110, 155),
    (156, 219),
    (220, 310),
    (311, 439),
    (440, 621),
    (622, 879),
    (880, 1199),
    (1200, 1799),
    (1800, 2499),
    (2500, 3499),
    (3500, 4999),
    (5000, 6999),
    (7000, 9999),
    (10000, 13999),
    (14000, 17999),
    (18000, 20000)
]

# band_gains = (0,) * len(freq_bands)
band_gains = (10, 8, 6, 4, 3, 2, 1, 0, 1, 2, 3, 4, 5, 6, 6, 6, 6, 6)


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


def design_filters(bands, order=2):
    filters = []
    for lowcut, highcut in bands:
        nyq = 0.5 * sample_rate
        low = lowcut / nyq
        high = highcut / nyq
        filters.append(butter(order, [low, high], btype='bandpass'))
    return filters


def equalizer(data, band_gains, filters):
    band_list = []
    for gain, (b, a) in zip(band_gains, filters):
        band_list.append(lfilter(b, a, data, axis=0) * (10 ** (gain/20)))
    signal = np.sum(band_list, axis=0)
    # Normalize to prevent clipping
    max_val = np.max(np.abs(signal))
    if max_val > 1:
        signal /= max_val
    return signal


if __name__ == '__main__':
    assert len(band_gains) == len(freq_bands), "Gain list length must equal the number of equalizer frequency bands!"
    filters = design_filters(freq_bands)
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
                recorded = mic.record(record_size)
                volume_adjusted = recorded * volume
                equalized = equalizer(volume_adjusted, band_gains, filters)
                audio_queue.put(equalized)
        finally:
            playing.value = False
            play_process.join()
